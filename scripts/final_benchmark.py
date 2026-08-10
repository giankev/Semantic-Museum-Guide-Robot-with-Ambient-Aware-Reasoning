#!/usr/bin/env python3
"""Aggregate existing museum diagnostics into report-ready benchmark data."""

import argparse
import csv
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = REPO_ROOT / ".navigation_diagnostics"
BENCHMARKS = REPO_ROOT / "benchmarks"
RAW = BENCHMARKS / "raw"
SUMMARY = BENCHMARKS / "summary"
PLOTS = BENCHMARKS / "plots"

DESTINATIONS = (
    "central_gallery",
    "north_gallery",
    "south_west_gallery",
    "south_east_gallery",
)
BASE_FIELDS = (
    "run_id",
    "timestamp_utc",
    "git_commit",
    "benchmark",
    "scenario",
    "variant",
    "status",
)
CSV_FIELDS = {
    "engagement": (
        "case_id",
        "scenario",
        "expected_engaged",
        "observed_engaged",
        "expected_terminal_state",
        "observed_terminal_state",
        "correct",
        "false_engagement",
        "activation_latency_s",
        "notes",
    ),
    "navigation": BASE_FIELDS + (
        "destination",
        "trial",
        "configuration",
        "success",
        "navigation_time_s",
        "physical_path_length_m",
        "gazebo_target_error_m",
        "amcl_target_error_m",
        "recoveries",
        "terminal_cmd_vel_zero",
        "source_path",
    ),
    "social_navigation": BASE_FIELDS + (
        "destination",
        "trial",
        "configuration",
        "trial_group",
        "person_trajectory",
        "success",
        "navigation_time_s",
        "physical_path_length_m",
        "minimum_person_distance_m",
        "minimum_front_person_distance_m",
        "maximum_person_speed_mps",
        "final_goal_error_m",
        "recoveries",
        "no_progress_failures",
        "terminal_cmd_vel_zero",
        "source_path",
    ),
    "reasoning": BASE_FIELDS + (
        "case_id",
        "constraints",
        "ambient_updates",
        "expected_room",
        "predicted_room",
        "expected_rejection",
        "predicted_rejection",
        "decision_correct",
        "rejection_correct",
        "route_policy_correct",
        "repeatability_correct",
    ),
    "language": BASE_FIELDS + (
        "case_id",
        "language",
        "input_text",
        "expected_intent",
        "predicted_intent",
        "expected_constraints",
        "predicted_constraints",
        "expected_room",
        "predicted_room",
        "resolved_correct",
        "intent_correct",
        "constraints_correct",
        "reasoning_correct",
        "route_policy_correct",
        "direct_or_invalid_rejected",
    ),
    "session_memory": BASE_FIELDS + (
        "case_id",
        "category",
        "expected_status",
        "observed_status",
        "expected_room",
        "predicted_room",
        "expected_rejection",
        "predicted_rejection",
        "expected_route",
        "predicted_route",
        "memory_write_correct",
        "decision_correct",
        "route_policy_correct",
        "repeatability_correct",
    ),
    "escort": BASE_FIELDS + (
        "trial",
        "configuration",
        "expected_sequence",
        "observed_sequence",
        "transition_correct",
        "nav_cancel_correct",
        "resume_correct",
        "duplicate_goal",
        "terminal_cmd_vel_zero",
        "final_outcome",
        "source_path",
    ),
    "end_to_end": BASE_FIELDS + (
        "trial",
        "configuration",
        "stt_success",
        "stt_latency_s",
        "transcript",
        "intent_correct",
        "constraints_correct",
        "selected_room",
        "route",
        "escort_arrived",
        "nav_success",
        "gazebo_target_error_m",
        "amcl_target_error_m",
        "dwb_active",
        "proxemic_force_active",
        "terminal_cmd_vel_zero",
        "overall_success",
        "source_path",
    ),
}


def ensure_directories():
    for directory in (RAW, SUMMARY, PLOTS):
        directory.mkdir(parents=True, exist_ok=True)


def git_value(*args):
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def current_commit():
    return git_value("rev-parse", "HEAD")


def current_branch():
    return git_value("branch", "--show-current")


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def timestamp_from_name(name):
    for token in name.split("_"):
        try:
            value = datetime.strptime(token, "%Y%m%dT%H%M%SZ")
        except ValueError:
            continue
        return value.replace(tzinfo=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    return None


def relative(path):
    return str(path.relative_to(REPO_ROOT))


def load_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def encode(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "1" if value else "0"
    return value


def write_csv(name, rows):
    ensure_directories()
    path = RAW / f"{name}.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=CSV_FIELDS[name], lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: encode(row.get(field)) for field in writer.fieldnames})
    return path


def read_csv(name):
    path = RAW / f"{name}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def number(value):
    if value in (None, "", "NA"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def boolean(value):
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True", "passed", "success"):
        return True
    if value in (0, "0", "false", "False", "failed", "failure"):
        return False
    return None


def mean(values):
    valid = [value for value in values if value is not None]
    return statistics.fmean(valid) if valid else None


def std(values):
    valid = [value for value in values if value is not None]
    return statistics.stdev(valid) if len(valid) > 1 else None


def final_navigation_batch():
    required_checks = {
        "all_nav2_goals_succeeded",
        "gazebo_target_error",
        "localized_target_error",
        "terminal_command_zero",
        "fresh_localization_tf",
    }
    batches = []
    if not DIAGNOSTICS.exists():
        return None, []
    for directory in DIAGNOSTICS.iterdir():
        if not directory.is_dir():
            continue
        reports = []
        for path in sorted(directory.glob("*_gallery_*.json")):
            data = load_json(path)
            if data is None or not {"destination", "waypoints", "final"} <= set(data):
                continue
            reports.append((path, data))
        destinations = {data.get("destination") for _, data in reports}
        compatible = bool(reports) and destinations == set(DESTINATIONS)
        for _, data in reports:
            checks = data.get("checks", {})
            compatible = compatible and data.get("status") == "passed"
            compatible = compatible and all(checks.get(key) is True for key in required_checks)
            compatible = compatible and data.get("final", {}).get("physical_distance_m") is not None
        if compatible:
            batches.append((directory.name, reports))
    return max(batches, default=(None, []), key=lambda item: item[0])


def import_navigation():
    batch_name, reports = final_navigation_batch()
    rows = []
    for path, report in reports:
        destination = report["destination"]
        suffix = path.stem.rsplit("_", 1)[-1]
        trial = int(suffix) if suffix.isdigit() else None
        durations = [
            item.get("duration_sim_sec")
            for item in report.get("waypoints", [])
            if isinstance(item.get("duration_sim_sec"), (int, float))
        ]
        final = report.get("final", {})
        rows.append(
            {
                "run_id": f"navigation-{batch_name}-{destination}-{trial}",
                "timestamp_utc": timestamp_from_name(batch_name),
                "git_commit": "NA",
                "benchmark": "navigation",
                "scenario": destination,
                "variant": "baseline_dwb",
                "status": report.get("status"),
                "destination": destination,
                "trial": trial,
                "configuration": "supplied_museum_final_baseline",
                "success": report.get("status") == "passed",
                "navigation_time_s": sum(durations) if durations else None,
                "physical_path_length_m": final.get("physical_distance_m"),
                "gazebo_target_error_m": final.get("gazebo_target_error_m"),
                "amcl_target_error_m": final.get("localized_target_error_m"),
                "recoveries": None,
                "terminal_cmd_vel_zero": report.get("checks", {}).get(
                    "terminal_command_zero"
                ),
                "source_path": relative(path),
            }
        )
    return rows


def social_reports():
    reports = []
    if not DIAGNOSTICS.exists():
        return reports
    for path in DIAGNOSTICS.rglob("*.json"):
        if "colcon" in path.parts:
            continue
        data = load_json(path)
        if data is None:
            continue
        if data.get("variant") in {
            "baseline", "isotropic", "anisotropic"
        } and (
            "minimum_person_distance_m" in data
            and data.get("person_trajectory") is not None
        ):
            reports.append((path, data))
    return reports


def import_social():
    variants_expected = ("baseline", "isotropic", "anisotropic")
    grouped = {}
    for path, report in social_reports():
        variants = grouped.setdefault(
            path.parent, {variant: [] for variant in variants_expected}
        )
        variants[report["variant"]].append((path, report))
    rows = []
    for parent, variants in sorted(grouped.items(), key=lambda item: str(item[0])):
        ordered = [
            sorted(variants[variant], key=lambda item: str(item[0]))
            for variant in variants_expected
        ]
        for index, triplet in enumerate(zip(*ordered), start=1):
            trial_group = f"{parent.name}-triplet-{index}"
            trajectories = {
                json.dumps(item[1].get("person_trajectory"), sort_keys=True)
                for item in triplet
            }
            if len(trajectories) != 1:
                continue
            for path, report in triplet:
                variant = report["variant"]
                navigation = report.get("navigation_result", {})
                rows.append(
                    {
                        "run_id": f"social-{trial_group}-{variant}",
                        "timestamp_utc": timestamp_from_name(parent.name),
                        "git_commit": "NA",
                        "benchmark": "social_navigation",
                        "scenario": "north_gallery",
                        "variant": variant,
                        "status": report.get("status"),
                        "destination": "north_gallery",
                        "trial": index,
                        "configuration": (
                            "nav2_supplied_demo"
                            if variant == "baseline"
                            else (
                                "nav2_supplied_social_force"
                                if variant == "isotropic"
                                else "nav2_supplied_anisotropic"
                            )
                        ),
                        "trial_group": trial_group,
                        "person_trajectory": report.get("person_trajectory"),
                        "success": report.get("status") == "passed",
                        "navigation_time_s": report.get(
                            "navigation_simulated_time_sec"
                        ),
                        "physical_path_length_m": report.get(
                            "physical_path_length_m"
                        ),
                        "minimum_person_distance_m": report.get(
                            "minimum_person_distance_m"
                        ),
                        "minimum_front_person_distance_m": report.get(
                            "minimum_front_person_distance_m"
                        ),
                        "maximum_person_speed_mps": report.get(
                            "maximum_observed_person_speed_mps"
                        ),
                        "final_goal_error_m": navigation.get(
                            "gazebo_target_error_m"
                        ),
                        "recoveries": report.get("maximum_recoveries"),
                        "no_progress_failures": report.get(
                            "no_progress_failures"
                        ),
                        "terminal_cmd_vel_zero": report.get(
                            "terminal_cmd_vel", {}
                        ).get("zero"),
                        "source_path": relative(path),
                    }
                )
    return rows


def final_reports():
    reports = []
    if not DIAGNOSTICS.exists():
        return reports
    for path in DIAGNOSTICS.glob("final_*/final_report.json"):
        data = load_json(path)
        if data is not None and data.get("status") == "passed":
            reports.append((path, data))
    return sorted(reports, key=lambda item: str(item[0]))


def terminal_zero(report):
    command = report.get("terminal_cmd_vel", {})
    values = [value for value in command.values() if isinstance(value, (int, float))]
    return bool(values) and all(abs(value) <= 1.0e-6 for value in values)


def import_escort_and_end_to_end():
    escort_rows = []
    end_rows = []
    expected = ["escorting", "waiting", "escorting", "arrived"]
    for trial, (path, report) in enumerate(final_reports(), start=1):
        sequence = report.get("escort_sequence", [])
        navigation_sequence = report.get("navigation_sequence", [])
        uuids = report.get("goal_uuids", [])
        escort_rows.append(
            {
                "run_id": f"escort-lag-resume-{trial}",
                "timestamp_utc": timestamp_from_name(path.parent.name),
                "git_commit": "NA",
                "benchmark": "escort",
                "scenario": "lag_resume",
                "variant": "scripted_visitor",
                "status": "passed" if sequence == expected else "failed",
                "trial": trial,
                "configuration": "supplied_museum_final_social_force",
                "expected_sequence": expected,
                "observed_sequence": sequence,
                "transition_correct": sequence == expected,
                "nav_cancel_correct": (
                    "intentionally_canceled_for_escort_wait"
                    in navigation_sequence
                ),
                "resume_correct": navigation_sequence
                == [
                    "accepted",
                    "intentionally_canceled_for_escort_wait",
                    "accepted",
                    "succeeded",
                ],
                "duplicate_goal": len(uuids) != len(set(uuids)),
                "terminal_cmd_vel_zero": terminal_zero(report),
                "final_outcome": sequence[-1] if sequence else None,
                "source_path": relative(path),
            }
        )

        request = report.get("structured_request", {})
        stt = report.get("wav_to_transcript", {})
        stt_status = stt.get("status", {})
        assertions = report.get("assertions", {})
        end_rows.append(
            {
                "run_id": f"end-to-end-{trial}",
                "timestamp_utc": timestamp_from_name(path.parent.name),
                "git_commit": "NA",
                "benchmark": "end_to_end",
                "scenario": "audio_impressionism_north_gallery",
                "variant": "groq_whisper_social_force",
                "status": report.get("status"),
                "trial": trial,
                "configuration": "supplied_museum_final_social_force",
                "stt_success": stt_status.get("status") == "success",
                "stt_latency_s": stt_status.get("latency_seconds"),
                "transcript": stt.get("transcript"),
                "intent_correct": request.get("intent")
                == "recommend_and_prepare_navigation",
                "constraints_correct": request.get("constraints")
                == {"style": "impressionism"},
                "selected_room": report.get("reasoning_result", {}).get(
                    "selected_room"
                ),
                "route": report.get("route_request", {}).get("route"),
                "escort_arrived": bool(sequence) and sequence[-1] == "arrived",
                "nav_success": assertions.get("13_nav2_succeeded"),
                "gazebo_target_error_m": report.get(
                    "gazebo_target_error_m"
                ),
                "amcl_target_error_m": report.get("amcl_target_error_m"),
                "dwb_active": assertions.get("16_dwb_active"),
                "proxemic_force_active": assertions.get(
                    "17_proxemic_force_active"
                ),
                "terminal_cmd_vel_zero": assertions.get(
                    "20_terminal_cmd_vel_zero"
                ),
                "overall_success": report.get("status") == "passed"
                and all(assertions.values()),
                "source_path": relative(path),
            }
        )
    return escort_rows, end_rows


def command_import_existing(_args):
    navigation = import_navigation()
    social = import_social()
    escort, end_to_end = import_escort_and_end_to_end()
    paths = [
        write_csv("navigation", navigation),
        write_csv("social_navigation", social),
        write_csv("escort", escort),
        write_csv("end_to_end", end_to_end),
    ]
    print(
        "Imported existing diagnostics: "
        f"navigation={len(navigation)}, social={len(social)}, "
        f"escort={len(escort)}, end_to_end={len(end_to_end)}"
    )
    for path in paths:
        print(relative(path))


def load_script(name):
    path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"benchmark_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_json_script(name):
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / name)],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def rejection_reasons(decision):
    reasons = set()
    if isinstance(decision, dict):
        for rejected in decision.get("rejected_rooms", []):
            reasons.update(rejected.get("reasons", []))
    return sorted(reasons)


def offline_reasoning(commit, timestamp):
    module = load_script("benchmark_scene_graph_reasoning.py")
    output = run_json_script("benchmark_scene_graph_reasoning.py")
    results = {item["name"]: item for item in output["cases"]}
    repeatability = output["summary"]["deterministic_repeatability"]
    rows = []
    for definition in module.CASES:
        case_id, constraints, updates, expected_room, expected_rejection = definition
        result = results[case_id]
        decision = result["decision"]
        passed = all(
            (
                result["decision_correct"],
                result["rejection_correct"],
                result["integration_correct"],
                repeatability,
            )
        )
        rows.append(
            {
                "run_id": f"reasoning-{case_id}",
                "timestamp_utc": timestamp,
                "git_commit": commit,
                "benchmark": "reasoning",
                "scenario": case_id,
                "variant": "bounded_deterministic_functional",
                "status": "passed" if passed else "failed",
                "case_id": case_id,
                "constraints": constraints,
                "ambient_updates": updates,
                "expected_room": expected_room,
                "predicted_room": decision.get("selected_room"),
                "expected_rejection": expected_rejection,
                "predicted_rejection": rejection_reasons(decision),
                "decision_correct": result["decision_correct"],
                "rejection_correct": result["rejection_correct"],
                "route_policy_correct": result["integration_correct"],
                "repeatability_correct": repeatability,
            }
        )
    return rows


def language_code(case_id):
    if case_id.startswith("it_"):
        return "it"
    if case_id.startswith("en_"):
        return "en"
    return "other"


def offline_language(commit, timestamp):
    module = load_script("benchmark_language_scene_graph.py")
    output = run_json_script("benchmark_language_scene_graph.py")
    results = {item["name"]: item for item in output["cases"]}
    rows = []
    for definition in module.CASES:
        case_id = definition["name"]
        result = results[case_id]
        parsed = module.parse_deterministic(definition["text"])
        resolved = definition["intent"] is not None
        decision = result.get("decision")
        passed = (
            result["parser_correct"]
            and result["intent_correct"]
            and result["constraints_correct"]
            and result["invalid_rejected"]
            and result["decision_correct"]
            and result["route_policy_correct"]
        )
        rows.append(
            {
                "run_id": f"language-{case_id}",
                "timestamp_utc": timestamp,
                "git_commit": commit,
                "benchmark": "language",
                "scenario": case_id,
                "variant": "bounded_functional_language",
                "status": "passed" if passed else "failed",
                "case_id": case_id,
                "language": language_code(case_id),
                "input_text": definition["text"],
                "expected_intent": definition["intent"],
                "predicted_intent": parsed.get("intent") if parsed else None,
                "expected_constraints": definition["constraints"],
                "predicted_constraints": (
                    parsed.get("constraints") if parsed else None
                ),
                "expected_room": definition["room"],
                "predicted_room": (
                    decision.get("selected_room") if decision else None
                ),
                "resolved_correct": result["parser_correct"],
                "intent_correct": result["intent_correct"],
                "constraints_correct": result["constraints_correct"],
                "reasoning_correct": (
                    result["decision_correct"] if resolved else None
                ),
                "route_policy_correct": (
                    result["route_policy_correct"] if resolved else None
                ),
                "direct_or_invalid_rejected": (
                    result["invalid_rejected"] if not resolved else None
                ),
            }
        )
    return rows


def offline_session_memory(commit, timestamp):
    output = run_json_script("benchmark_session_memory.py")
    repeatability = output["summary"]["deterministic_repeatability"]
    rows = []
    for item in output["cases"]:
        rows.append(
            {
                "run_id": f"session-memory-{item['case_id']}",
                "timestamp_utc": timestamp,
                "git_commit": commit,
                "benchmark": "session_memory",
                "scenario": item["case_id"],
                "variant": "bounded_session_memory_functional",
                "status": "passed" if item["passed"] else "failed",
                **item,
                "repeatability_correct": repeatability,
            }
        )
    return rows


def offline_engagement():
    package_src = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
    sys.path.insert(0, str(package_src))
    from museum_assistant.engagement import EngagementModel

    cases = (
        ("E1", "empty", False, "NO_PERSON", [(0, False, False, None)]),
        ("E2", "visual_only", False, "PASSING", [(0, True, True, None), (3, True, True, None)]),
        ("E3", "lidar_only", False, "NO_PERSON", [(0, False, False, 1.5), (3, False, False, 1.5)]),
        ("E4", "passing", False, "NO_PERSON", [(0, True, True, 1.5), (0.5, False, False, None)]),
        ("E5", "far_person", False, "PASSING", [(0, True, True, 2.2), (3, True, True, 2.2)]),
        ("E6", "stationary_near", True, "ENGAGED", [(0, True, True, 1.5), (1, True, True, 1.5), (2.5, True, True, 1.5)]),
        ("E7", "engaged_then_leave", True, "NO_PERSON", [(0, True, True, 1.5), (1, True, True, 1.5), (2.5, True, True, 1.5), (2.6, False, False, None), (4.2, False, False, None)]),
    )
    rows = []
    for case_id, scenario, expected, terminal, sequence in cases:
        model, observed, latency = EngagementModel(), False, None
        for now, visual, central, distance in sequence:
            result = model.update(now=now, visual_person=visual,
                                  central=central, distance_m=distance)
            if result.state.value == "ENGAGED" and not observed:
                observed, latency = True, now
        correct = observed == expected and result.state.value == terminal
        rows.append({
            "case_id": case_id, "scenario": scenario,
            "expected_engaged": expected, "observed_engaged": observed,
            "expected_terminal_state": terminal,
            "observed_terminal_state": result.state.value,
            "correct": correct, "false_engagement": observed and not expected,
            "activation_latency_s": latency,
            "notes": "deterministic sensor-fusion sequence",
        })
    return rows


def command_offline(_args):
    commit = current_commit()
    timestamp = now_utc()
    reasoning = offline_reasoning(commit, timestamp)
    language = offline_language(commit, timestamp)
    session_memory = offline_session_memory(commit, timestamp)
    engagement = offline_engagement()
    write_csv("reasoning", reasoning)
    write_csv("language", language)
    write_csv("session_memory", session_memory)
    write_csv("engagement", engagement)
    reasoning_pass = sum(row["status"] == "passed" for row in reasoning)
    language_pass = sum(row["status"] == "passed" for row in language)
    memory_pass = sum(row["status"] == "passed" for row in session_memory)
    engagement_pass = sum(row["correct"] for row in engagement)
    print(f"Reasoning: {reasoning_pass}/{len(reasoning)}")
    print(f"Language: {language_pass}/{len(language)}")
    print(f"Session memory: {memory_pass}/{len(session_memory)}")
    print(f"Engagement: {engagement_pass}/{len(engagement)}")
    if (reasoning_pass, language_pass, memory_pass, engagement_pass) != (25, 27, 8, 7):
        raise SystemExit("Offline benchmark totals differ from the validated baseline.")


def metric(values):
    return {"mean": mean(values), "std": std(values)}


def navigation_summary(rows):
    output = {}
    for destination in DESTINATIONS:
        selected = [row for row in rows if row["destination"] == destination]
        success = [boolean(row["success"]) for row in selected]
        recoveries = [number(row["recoveries"]) for row in selected]
        output[destination] = {
            "N": len(selected),
            "success_rate": mean([float(value) for value in success if value is not None]),
            "navigation_time_s": metric(
                [number(row["navigation_time_s"]) for row in selected]
            ),
            "physical_path_length_m": metric(
                [number(row["physical_path_length_m"]) for row in selected]
            ),
            "gazebo_target_error_m": metric(
                [number(row["gazebo_target_error_m"]) for row in selected]
            ),
            "amcl_target_error_m": metric(
                [number(row["amcl_target_error_m"]) for row in selected]
            ),
            "total_recoveries": (
                sum(value for value in recoveries if value is not None)
                if any(value is not None for value in recoveries)
                else None
            ),
        }
    return output


def social_summary(rows):
    variants = ("baseline", "isotropic", "anisotropic")
    output = {"triplet_N": 0, **{variant: {} for variant in variants}}
    trial_groups = {
        row["trial_group"] for row in rows if row["trial_group"]
    }
    complete_triplets = [
        group
        for group in trial_groups
        if {
            row["variant"]
            for row in rows
            if row["trial_group"] == group
        } == set(variants)
    ]
    output["triplet_N"] = len(complete_triplets)
    for variant in variants:
        selected = [
            row
            for row in rows
            if row["variant"] == variant
            and row["trial_group"] in complete_triplets
        ]
        success = [boolean(row["success"]) for row in selected]
        output[variant] = {
            "N": len(selected),
            "success_rate": mean(
                [float(value) for value in success if value is not None]
            ),
            "minimum_person_distance_m": metric(
                [number(row["minimum_person_distance_m"]) for row in selected]
            ),
            "minimum_front_person_distance_m": metric(
                [
                    number(row["minimum_front_person_distance_m"])
                    for row in selected
                ]
            ),
            "navigation_time_s": metric(
                [number(row["navigation_time_s"]) for row in selected]
            ),
            "physical_path_length_m": metric(
                [number(row["physical_path_length_m"]) for row in selected]
            ),
        }
    by_variant = {
        variant: {
            row["trial_group"]: row
            for row in rows
            if row["variant"] == variant
        }
        for variant in variants
    }
    comparisons = (
        ("isotropic_minus_baseline", "baseline", "isotropic"),
        ("anisotropic_minus_isotropic", "isotropic", "anisotropic"),
        ("anisotropic_minus_baseline", "baseline", "anisotropic"),
    )
    output["paired_deltas"] = {}
    for label, reference, candidate in comparisons:
        total_deltas = []
        total_percentages = []
        front_deltas = []
        front_percentages = []
        for group in complete_triplets:
            for field, deltas, percentages in (
                (
                    "minimum_person_distance_m",
                    total_deltas,
                    total_percentages,
                ),
                (
                    "minimum_front_person_distance_m",
                    front_deltas,
                    front_percentages,
                ),
            ):
                before = number(by_variant[reference][group][field])
                after = number(by_variant[candidate][group][field])
                if before is None or after is None:
                    continue
                deltas.append(after - before)
                if before != 0:
                    percentages.append(100.0 * (after - before) / before)
        output["paired_deltas"][label] = {
            "minimum_person_distance_delta_m": mean(total_deltas),
            "minimum_person_distance_improvement_pct": mean(
                total_percentages
            ),
            "minimum_front_person_distance_delta_m": mean(front_deltas),
            "minimum_front_person_distance_improvement_pct": mean(
                front_percentages
            ),
        }
    return output


def accuracy(rows, field, predicate=None):
    selected = rows if predicate is None else [row for row in rows if predicate(row)]
    values = [boolean(row[field]) for row in selected]
    valid = [value for value in values if value is not None]
    return {
        "correct": sum(valid),
        "N": len(valid),
        "accuracy": mean([float(value) for value in valid]),
    }


def reasoning_summary(rows):
    no_match = lambda row: bool(row["expected_rejection"])
    return {
        "label": "bounded deterministic functional benchmark",
        "total_cases": len(rows),
        "decision": accuracy(rows, "decision_correct"),
        "no_match": accuracy(rows, "decision_correct", no_match),
        "rejection_reason": accuracy(rows, "rejection_correct", no_match),
        "route_policy": accuracy(rows, "route_policy_correct"),
        "deterministic_repeatability": accuracy(
            rows, "repeatability_correct"
        ),
    }


def language_summary(rows):
    resolved = lambda row: bool(row["expected_intent"])
    invalid = lambda row: not bool(row["expected_intent"])
    return {
        "label": "bounded functional language benchmark",
        "total_phrases": len(rows),
        "parser_resolution": accuracy(rows, "resolved_correct"),
        "intent": accuracy(rows, "intent_correct", resolved),
        "constraint_extraction": accuracy(
            rows, "constraints_correct", resolved
        ),
        "direct_invalid_rejection": accuracy(
            rows, "direct_or_invalid_rejected", invalid
        ),
        "end_to_end_reasoning": accuracy(
            rows, "reasoning_correct", resolved
        ),
        "route_policy": accuracy(rows, "route_policy_correct", resolved),
    }


def session_memory_summary(rows):
    category = lambda *names: lambda row: row["category"] in names
    summary = {
        "label": "bounded session-memory functional benchmark",
        "total_cases": len(rows),
        "memory_write": accuracy(
            rows, "memory_write_correct",
            category("memory_write", "explicit_override"),
        ),
        "follow_up": accuracy(
            rows, "decision_correct", category("follow_up", "explicit_override")
        ),
        "session_isolation": accuracy(
            rows, "decision_correct", category("session_isolation")
        ),
        "explicit_override": accuracy(
            rows, "decision_correct", category("explicit_override")
        ),
        "ambient_revalidation": accuracy(
            rows, "decision_correct", category("ambient_revalidation")
        ),
        "route_policy": accuracy(rows, "route_policy_correct"),
        "deterministic_repeatability": accuracy(
            rows, "repeatability_correct"
        ),
    }
    for name in (
        "follow_up", "session_isolation", "ambient_revalidation", "route_policy"
    ):
        summary[f"{name}_accuracy"] = summary[name]["accuracy"]
    return summary


def engagement_summary(rows):
    correct = sum(boolean(row["correct"]) is True for row in rows)
    positive = [row for row in rows if boolean(row["expected_engaged"]) is True]
    return {
        "total_cases": len(rows),
        "correct_cases": correct,
        "bounded_engagement_state_accuracy": correct / len(rows) if rows else None,
        "false_engagement_count": sum(
            boolean(row["false_engagement"]) is True for row in rows
        ),
        "positive_cases": len(positive),
        "mean_activation_latency_s": mean(
            [number(row["activation_latency_s"]) for row in positive]
        ),
    }


def build_summary():
    tables = {name: read_csv(name) for name in CSV_FIELDS}
    escort_counts = {
        scenario: sum(
            row["status"] == "passed"
            for row in tables["escort"]
            if row["scenario"] == scenario
        )
        for scenario in ("normal", "lag_resume", "lost")
    }
    end_success = sum(
        boolean(row["overall_success"]) is True for row in tables["end_to_end"]
    )
    return {
        "generated_at": now_utc(),
        "git_commit": current_commit(),
        "git_branch": current_branch(),
        "ros_distro": "humble (project target)",
        "museum_world": "supplied_museum",
        "navigation_controller": "dwb_core::DWBLocalPlanner",
        "social_critic": "museum_social_critic::ProxemicForceCritic",
        "number_of_runs_per_benchmark": {
            name: len(rows) for name, rows in tables.items()
        },
        "navigation": navigation_summary(tables["navigation"]),
        "social_navigation": social_summary(tables["social_navigation"]),
        "reasoning": reasoning_summary(tables["reasoning"]),
        "language": language_summary(tables["language"]),
        "session_memory": session_memory_summary(tables["session_memory"]),
        "engagement": engagement_summary(tables["engagement"]),
        "escort": {"valid_runs": escort_counts},
        "end_to_end": {
            "N": len(tables["end_to_end"]),
            "successful_runs": end_success,
            "success_rate": (
                end_success / len(tables["end_to_end"])
                if tables["end_to_end"]
                else None
            ),
        },
        "limitations": [
            "Simulation-only evaluation.",
            "People are scripted/non-reactive.",
            "Physical paired comparisons currently have a small N.",
            "Escort uses visitor ground truth and simulated observation.",
            "Live STT evidence uses the external Groq cloud provider.",
            "No real-user subjective study was conducted.",
        ],
    }


def flatten_summary(summary):
    rows = []
    for destination, values in summary["navigation"].items():
        rows.append(
            {
                "benchmark": "navigation",
                "scenario": destination,
                "variant": "baseline_dwb",
                "metric": "success_rate",
                "value": values["success_rate"],
                "unit": "ratio",
                "N": values["N"],
            }
        )
        for metric_name in (
            "navigation_time_s",
            "physical_path_length_m",
            "gazebo_target_error_m",
            "amcl_target_error_m",
        ):
            metric_value = values[metric_name]
            unit = "s" if metric_name.endswith("_s") else "m"
            for statistic in ("mean", "std"):
                rows.append(
                    {
                        "benchmark": "navigation",
                        "scenario": destination,
                        "variant": "baseline_dwb",
                        "metric": f"{metric_name}_{statistic}",
                        "value": metric_value[statistic],
                        "unit": unit,
                        "N": values["N"],
                    }
                )
    for benchmark in ("reasoning", "language", "session_memory"):
        for metric_name, values in summary[benchmark].items():
            if not isinstance(values, dict) or "accuracy" not in values:
                continue
            rows.append(
                {
                    "benchmark": benchmark,
                    "scenario": "all",
                    "variant": summary[benchmark]["label"],
                    "metric": f"{metric_name}_accuracy",
                    "value": values["accuracy"],
                    "unit": "ratio",
                    "N": values["N"],
                }
            )
    engagement = summary["engagement"]
    rows.append({
        "benchmark": "engagement", "scenario": "all",
        "variant": "bounded deterministic sensor fusion",
        "metric": "bounded_engagement_state_accuracy",
        "value": engagement["bounded_engagement_state_accuracy"],
        "unit": "ratio", "N": engagement["total_cases"],
    })
    social = summary["social_navigation"]
    for variant in ("baseline", "isotropic", "anisotropic"):
        values = social[variant]
        for metric_name in (
            "minimum_person_distance_m",
            "minimum_front_person_distance_m",
            "navigation_time_s",
            "physical_path_length_m",
        ):
            for statistic in ("mean", "std"):
                rows.append(
                    {
                        "benchmark": "social_navigation",
                        "scenario": "north_gallery",
                        "variant": variant,
                        "metric": f"{metric_name}_{statistic}",
                        "value": values[metric_name][statistic],
                        "unit": "s" if metric_name.endswith("_s") else "m",
                        "N": values["N"],
                    }
                )
    return rows


def command_summarize(_args):
    ensure_directories()
    summary = build_summary()
    json_path = SUMMARY / "benchmark_summary.json"
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    csv_path = SUMMARY / "benchmark_summary.csv"
    fields = ("benchmark", "scenario", "variant", "metric", "value", "unit", "N")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        for row in flatten_summary(summary):
            writer.writerow({field: encode(row.get(field)) for field in fields})
    print(relative(json_path))
    print(relative(csv_path))


def plot_empty(axis, title, message):
    axis.set_title(title)
    axis.text(0.5, 0.5, message, ha="center", va="center", transform=axis.transAxes)
    axis.set_xticks([])
    axis.set_yticks([])


def command_plot(_args):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "Plotting requires the tooling-only dependency matplotlib. "
            "Install it in a virtual environment; do not modify the robot image."
        ) from exc

    ensure_directories()
    navigation = read_csv("navigation")
    social = read_csv("social_navigation")
    reasoning = read_csv("reasoning")
    language = read_csv("language")
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 180,
            "font.size": 9,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.alpha": 0.25,
        }
    )

    def navigation_plot(field, ylabel, filename, title):
        means = []
        errors = []
        counts = []
        for destination in DESTINATIONS:
            values = [
                number(row[field])
                for row in navigation
                if row["destination"] == destination
            ]
            values = [value for value in values if value is not None]
            means.append(mean(values) or 0.0)
            errors.append(std(values) or 0.0)
            counts.append(len(values))
        fig, axis = plt.subplots(figsize=(7.2, 4.2))
        labels = [item.replace("_gallery", "").replace("_", "\n") for item in DESTINATIONS]
        bars = axis.bar(labels, means, yerr=errors, capsize=4, color="#4472C4")
        axis.set_ylabel(ylabel)
        axis.set_title(title)
        for bar, count in zip(bars, counts):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"N={count}",
                ha="center",
                va="bottom",
            )
        fig.tight_layout()
        fig.savefig(PLOTS / filename)
        plt.close(fig)

    navigation_plot(
        "gazebo_target_error_m",
        "Final Gazebo error (m)",
        "navigation_final_error.png",
        "Supplied-museum navigation final error",
    )
    navigation_plot(
        "navigation_time_s",
        "Simulated navigation time (s)",
        "navigation_time.png",
        "Supplied-museum navigation time",
    )

    variants = ("baseline", "isotropic", "anisotropic")
    trial_groups = sorted(
        {
            row["trial_group"]
            for row in social
            if row["trial_group"]
            and {
                item["variant"]
                for item in social
                if item["trial_group"] == row["trial_group"]
            } == set(variants)
        }
    )
    fig, axis = plt.subplots(figsize=(6.5, 4.2))
    if not trial_groups:
        plot_empty(axis, "Social clearance", "No compatible triplets (N=0)")
    else:
        values_by_variant = {
            variant: {
                row["trial_group"]: number(
                    row["minimum_front_person_distance_m"]
                )
                for row in social
                if row["variant"] == variant
            }
            for variant in variants
        }
        for group in trial_groups:
            values = [values_by_variant[item].get(group) for item in variants]
            if any(value is None for value in values):
                continue
            axis.plot(
                range(3),
                values,
                marker="o",
                color="#777777",
                alpha=0.75,
            )
        means = [
            mean(
                [
                    values_by_variant[variant].get(group)
                    for group in trial_groups
                ]
            )
            for variant in variants
        ]
        axis.plot(
            range(3), means, marker="D", linewidth=2.2, color="#C00000",
            label="mean",
        )
        axis.set_xticks(
            range(3), ["DWB baseline", "Isotropic", "Anisotropic"]
        )
        axis.set_ylabel("Minimum front-person distance (m)")
        axis.set_title(f"Paired anisotropic clearance (N={len(trial_groups)})")
        axis.legend()
    fig.tight_layout()
    fig.savefig(PLOTS / "social_clearance.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(8.5, 4.0))
    colors = ("#A5A5A5", "#ED7D31", "#4472C4")
    for axis, field, ylabel in (
        (axes[0], "navigation_time_s", "Time (s)"),
        (axes[1], "physical_path_length_m", "Path length (m)"),
    ):
        values = [
            mean(
                [
                    number(row[field])
                    for row in social
                    if row["variant"] == variant
                    and number(row[field]) is not None
                ]
            )
            for variant in variants
        ]
        if all(value is None for value in values):
            plot_empty(axis, ylabel, "No paired data (N=0)")
        else:
            axis.bar(variants, [value or 0.0 for value in values], color=colors)
            axis.set_ylabel(ylabel)
            axis.set_title(f"N={len(trial_groups)} triplets")
    fig.suptitle("Social-navigation task efficiency")
    fig.tight_layout()
    fig.savefig(PLOTS / "social_time_path.png")
    plt.close(fig)

    metrics = [
        (
            "Reasoning\ndecision",
            accuracy(reasoning, "decision_correct")["accuracy"],
            len(reasoning),
        ),
        (
            "Language\nintent",
            accuracy(
                language,
                "intent_correct",
                lambda row: bool(row["expected_intent"]),
            )["accuracy"],
            sum(bool(row["expected_intent"]) for row in language),
        ),
        (
            "Language\nconstraints",
            accuracy(
                language,
                "constraints_correct",
                lambda row: bool(row["expected_intent"]),
            )["accuracy"],
            sum(bool(row["expected_intent"]) for row in language),
        ),
    ]
    fig, axis = plt.subplots(figsize=(6.6, 4.2))
    bars = axis.bar(
        [item[0] for item in metrics],
        [item[1] or 0.0 for item in metrics],
        color=("#4472C4", "#70AD47", "#70AD47"),
    )
    axis.set_ylim(0, 1.08)
    axis.set_ylabel("Accuracy")
    axis.set_title("Bounded functional benchmark accuracy")
    for bar, (_, value, count) in zip(bars, metrics):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{(value or 0.0):.1%}\nN={count}",
            ha="center",
            va="bottom",
        )
    fig.tight_layout()
    fig.savefig(PLOTS / "reasoning_language_accuracy.png")
    plt.close(fig)

    for path in sorted(PLOTS.glob("*.png")):
        print(relative(path))


def command_status(_args):
    navigation = read_csv("navigation")
    social = read_csv("social_navigation")
    escort = read_csv("escort")
    end_to_end = read_csv("end_to_end")
    session_memory = read_csv("session_memory")
    engagement = read_csv("engagement")
    memory_pass = sum(row["status"] == "passed" for row in session_memory)
    print(f"Session memory:\n  offline cases: {memory_pass}/8")
    engagement_pass = sum(row["correct"] == "1" for row in engagement)
    print(f"Engagement:\n  offline cases: {engagement_pass}/{len(engagement)}")
    print("Navigation:")
    for destination in DESTINATIONS:
        count = sum(
            row["destination"] == destination and row["status"] == "passed"
            for row in navigation
        )
        print(f"  {destination}: {count}/3")
    complete_triplets = {
        group
        for group in {
            row["trial_group"] for row in social if row["trial_group"]
        }
        if {
            row["variant"]
            for row in social
            if row["trial_group"] == group and row["status"] == "passed"
        } == {"baseline", "isotropic", "anisotropic"}
    }
    print("Social navigation:")
    print(
        f"  complete triplets: {len(complete_triplets)}/5 "
        "(minimum campaign: 3)"
    )
    print("Escort:")
    for scenario in ("normal", "lag_resume", "lost"):
        count = sum(
            row["scenario"] == scenario and row["status"] == "passed"
            for row in escort
        )
        print(f"  {scenario}: {count}/1")
    print("End-to-end:")
    complete = sum(row["status"] == "passed" for row in end_to_end)
    print(f"  complete runs: {complete}/3")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("import-existing", "offline", "summarize", "plot", "status"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    commands = {
        "import-existing": command_import_existing,
        "offline": command_offline,
        "summarize": command_summarize,
        "plot": command_plot,
        "status": command_status,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
