from museum_assistant.semantic_navigation import (
    navigation_pose_from_decision,
)


def executable_decision():
    return {
        "request_id": "req_003",
        "session_id": "session_1",
        "status": "success",
        "intent": "recommend_and_prepare_navigation",
        "selected_room": "impressionism_hall",
        "skill": "navigate_to",
        "nav_pose": {"x": 5.0, "y": 1.5, "yaw": 1.57},
    }


def test_successful_navigation_intent_is_executable():
    assert navigation_pose_from_decision(executable_decision()) == (
        5.0,
        1.5,
        1.57,
    )


def test_plain_recommendation_is_not_executable():
    decision = executable_decision()
    decision["intent"] = "recommend"

    assert navigation_pose_from_decision(decision) is None


def test_no_match_is_not_executable():
    decision = executable_decision()
    decision["status"] = "no_match"

    assert navigation_pose_from_decision(decision) is None


def test_ask_clarification_is_not_executable():
    decision = executable_decision()
    decision["skill"] = "ask_clarification"

    assert navigation_pose_from_decision(decision) is None


def test_missing_or_malformed_nav_pose_is_not_executable():
    invalid_poses = (
        None,
        {},
        {"x": 5.0, "y": 1.5},
        {"x": "5.0", "y": 1.5, "yaw": 1.57},
        {"x": True, "y": 1.5, "yaw": 1.57},
        {"x": float("inf"), "y": 1.5, "yaw": 1.57},
    )

    for nav_pose in invalid_poses:
        decision = executable_decision()
        decision["nav_pose"] = nav_pose
        assert navigation_pose_from_decision(decision) is None
