"""YOLO inference wrapper for real-time hand gesture detection."""
from typing import List, Optional
from dataclasses import dataclass
import numpy as np
from ultralytics import YOLO

from backend.config import CONFIDENCE_THRESHOLD


@dataclass
class Prediction:
    class_name: str
    class_id: int
    confidence: float
    bbox: list  # [x1, y1, x2, y2]


CLASS_NAMES = {0: "Rock", 1: "Paper", 2: "Scissors"}
CLASS_COLORS = {
    "Rock": (255, 0, 0),     # Blue
    "Paper": (0, 255, 0),    # Green
    "Scissors": (0, 0, 255), # Red
}


class YOLOInference:
    def __init__(self, model_path: str):
        self.model = YOLO(model_path)
        self.conf_threshold = CONFIDENCE_THRESHOLD

    def predict(self, frame: np.ndarray) -> List[Prediction]:
        results = self.model(frame, verbose=False)[0]
        predictions = []

        if results.boxes is not None:
            for box in results.boxes:
                conf = float(box.conf[0])
                if conf < self.conf_threshold:
                    continue
                cls_id = int(box.cls[0])
                xyxy = box.xyxy[0].tolist()
                predictions.append(Prediction(
                    class_name=CLASS_NAMES[cls_id],
                    class_id=cls_id,
                    confidence=conf,
                    bbox=xyxy,
                ))

        predictions.sort(key=lambda p: p.confidence, reverse=True)
        return predictions

    def get_best_move(self, frame: np.ndarray) -> Optional[Prediction]:
        preds = self.predict(frame)
        if not preds:
            return None

        # Ambiguity: two hands with different classes, similar confidence
        if len(preds) >= 2 and preds[0].class_id != preds[1].class_id:
            conf_ratio = preds[1].confidence / max(preds[0].confidence, 0.01)
            if conf_ratio > 0.85:
                return None

        return preds[0]


def annotate_frame(frame: np.ndarray, predictions: List[Prediction]) -> np.ndarray:
    """Draw bounding boxes and labels on frame."""
    import cv2

    for pred in predictions:
        x1, y1, x2, y2 = map(int, pred.bbox)
        color = CLASS_COLORS.get(pred.class_name, (255, 255, 255))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{pred.class_name} {pred.confidence:.2f}"
        cv2.putText(frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame
