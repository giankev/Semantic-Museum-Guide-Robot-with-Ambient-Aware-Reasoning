import numpy as np

from museum_assistant.person_detector import (
    PersonDetection,
    preprocess_image,
    select_person_candidate,
)


def test_preprocessing_produces_expected_blob():
    blob = preprocess_image(np.zeros((480, 640, 3), dtype=np.uint8))
    assert blob.shape == (1, 3, 416, 416)
    assert blob.dtype == np.float32
    assert np.isfinite(blob).all()


def test_empty_non_person_and_below_threshold_are_filtered():
    assert select_person_candidate([], (480, 640), 0.35, 0.7) == PersonDetection()
    detections = [(1, 0.9, (100, 10, 300, 400)),
                  (0, 0.34, (100, 10, 300, 400))]
    assert select_person_candidate(
        detections, (480, 640), 0.35, 0.7
    ) == PersonDetection()


def test_largest_sufficiently_central_person_is_selected():
    detections = [
        (0, 0.95, (0, 10, 80, 400)),
        (0, 0.7, (120, 20, 300, 390)),
        (0, 0.8, (170, 40, 250, 300)),
    ]
    result = select_person_candidate(detections, (480, 640), 0.35, 0.7)
    assert result.detected
    assert result.confidence == 0.7
    assert 0.49 < result.center_x_normalized < 0.51
    assert result.bbox_width > 0
    assert result.area_fraction > 0.0


def test_most_central_candidate_is_used_when_all_are_lateral():
    detections = [(0, 0.9, (0, 0, 20, 300)),
                  (0, 0.8, (330, 0, 400, 300))]
    result = select_person_candidate(detections, (416, 416), 0.35, 0.2)
    assert result.confidence == 0.8
