import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "scripts" / "export_supplied_museum_topdown.py"
OUTPUT_DIR = REPO_ROOT / ".museum_layout_audit"


def test_static_layout_export_output_contract():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(OUTPUT_DIR)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    png_path = OUTPUT_DIR / "topdown.png"
    report_path = OUTPUT_DIR / "layout_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert png_path.stat().st_size > 10_000
    assert report["audit_scope"] == "static collision geometry only"
    assert report["height_slice_world_m"] == {"z_min": 0.15, "z_max": 1.2}
    assert report["geometry_bounds_world_m"]["width_m"] > 100.0
    assert report["geometry_statistics"]["triangles"] > 6_000
    assert set(report["landmarks_world_xy_m"]) == {
        "tiago_spawn", "visitor_marker", "guide_marker", "staff_marker"
    }
    assert report["candidate_connected_navigable_regions"]
    assert len(report["approximate_narrowest_passages"]) == 2
    assert report["recommended_demo_crop_world_m"] == {
        "x_min": -8.0, "x_max": 42.0, "y_min": -8.0, "y_max": 22.0
    }
    assert report["physically_distinct_room_or_gallery_estimate"]["cautious_range"]
    assert "Runtime:" in result.stdout
