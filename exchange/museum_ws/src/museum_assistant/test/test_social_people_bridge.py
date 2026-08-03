from museum_assistant.social_people_bridge import compatibility_people_fields


def convert(pedestrians):
    return compatibility_people_fields(
        frame_id="map",
        stamp_sec=12,
        stamp_nanosec=34,
        pedestrians=pedestrians,
    )


def test_identifier_maps_to_name():
    result = convert([("visitor_1", 1.0, 2.0, 0.3, 0.4)])

    assert result.people[0].name == "visitor_1"
    assert result.people[0].reliability == 1.0


def test_position_xy_is_preserved():
    result = convert([("guide_1", 2.2, -0.35, 0.0, 0.0)])

    assert (result.people[0].x, result.people[0].y) == (2.2, -0.35)


def test_velocity_xy_is_preserved():
    result = convert([("visitor_1", 0.0, 0.0, 0.25, -0.1)])

    assert (result.people[0].vx, result.people[0].vy) == (0.25, -0.1)


def test_header_fields_are_preserved():
    result = convert([])

    assert result.frame_id == "map"
    assert (result.stamp_sec, result.stamp_nanosec) == (12, 34)


def test_empty_collection_stays_empty():
    assert convert([]).people == ()


def test_multiple_pedestrians_keep_order_and_values():
    result = convert(
        [
            ("visitor_1", 0.25, -0.45, 0.1, 0.2),
            ("staff_1", 8.2, 0.45, 0.0, 0.0),
        ]
    )

    assert [person.name for person in result.people] == [
        "visitor_1",
        "staff_1",
    ]
    assert (result.people[1].x, result.people[1].y) == (8.2, 0.45)
