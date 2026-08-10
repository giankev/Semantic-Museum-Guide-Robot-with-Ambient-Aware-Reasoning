"""Small OpenCV-DNN COCO person detector."""

from dataclasses import dataclass
import cv2
import numpy as np

INPUT_SIZE = 416


@dataclass(frozen=True)
class PersonDetection:
    detected: bool = False
    confidence: float = 0.0
    bbox_x: int = 0
    bbox_y: int = 0
    bbox_width: int = 0
    bbox_height: int = 0
    center_x_normalized: float = 0.0
    center_y_normalized: float = 0.0
    area_fraction: float = 0.0


def preprocess_image(image: np.ndarray) -> np.ndarray:
    resized = cv2.resize(image, (INPUT_SIZE, INPUT_SIZE)).astype(np.float32)
    mean = np.array([103.53, 116.28, 123.675], dtype=np.float32)
    std = np.array([57.375, 57.12, 58.395], dtype=np.float32)
    return cv2.dnn.blobFromImage((resized - mean) / std)


def select_person_candidate(detections, image_shape, threshold, central_fraction):
    """Filter COCO class 0 and prefer the largest sufficiently central box."""
    height, width = image_shape
    people = [item for item in detections if item[0] == 0 and item[1] >= threshold]
    if not people:
        return PersonDetection()

    def rank(item):
        x1, _, x2, _ = item[2]
        center = (x1 + x2) / (2 * INPUT_SIZE)
        central = abs(center - 0.5) <= central_fraction / 2
        area = (item[2][2] - x1) * (item[2][3] - item[2][1])
        return central, area if central else -abs(center - 0.5)

    class_id, confidence, (x1, y1, x2, y2) = max(people, key=rank)
    del class_id
    x1, x2 = x1 * width / INPUT_SIZE, x2 * width / INPUT_SIZE
    y1, y2 = y1 * height / INPUT_SIZE, y2 * height / INPUT_SIZE
    box_width, box_height = max(0.0, x2 - x1), max(0.0, y2 - y1)
    return PersonDetection(
        True, float(confidence), int(x1), int(y1), int(box_width), int(box_height),
        (x1 + x2) / (2 * width), (y1 + y2) / (2 * height),
        box_width * box_height / (width * height),
    )


class PersonDetector:
    """Run the 3.8 MB OpenCV Zoo NanoDet model on CPU."""

    def __init__(self, model_path, confidence_threshold=0.35, central_fraction=0.7):
        self.net = cv2.dnn.readNet(str(model_path))
        self.threshold = confidence_threshold
        self.central_fraction = central_fraction
        self.project = np.arange(8)

    def detect(self, image: np.ndarray) -> PersonDetection:
        if image is None or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Expected a non-empty BGR image.")
        self.net.setInput(preprocess_image(image))
        outputs = self.net.forward(self.net.getUnconnectedOutLayersNames())
        return select_person_candidate(
            self._decode(outputs), image.shape[:2], self.threshold,
            self.central_fraction,
        )

    def _decode(self, outputs):
        boxes, scores = [], []
        for stride, class_scores, bbox in zip((8, 16, 32, 64), outputs[::2], outputs[1::2]):
            class_scores, bbox = class_scores.squeeze(), bbox.squeeze()
            side = INPUT_SIZE // stride
            yy, xx = np.mgrid[:side, :side]
            anchors = np.column_stack(((xx.ravel() + 0.5) * stride - 0.5,
                                       (yy.ravel() + 0.5) * stride - 0.5))
            probability = np.exp(bbox.reshape(-1, 8))
            distance = probability / probability.sum(axis=1, keepdims=True)
            distance = (distance @ self.project).reshape(-1, 4) * stride
            level = np.column_stack((anchors[:, 0] - distance[:, 0],
                                     anchors[:, 1] - distance[:, 1],
                                     anchors[:, 0] + distance[:, 2],
                                     anchors[:, 1] + distance[:, 3]))
            boxes.extend(np.clip(level, 0, INPUT_SIZE).tolist())
            scores.extend(class_scores[:, 0].tolist())
        xywh = [[x1, y1, x2 - x1, y2 - y1] for x1, y1, x2, y2 in boxes]
        indices = cv2.dnn.NMSBoxes(xywh, scores, self.threshold, 0.6)
        return [(0, scores[i], tuple(boxes[i])) for i in np.array(indices).reshape(-1)]
