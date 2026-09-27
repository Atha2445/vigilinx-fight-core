# """
# detector.py

# Step 3 checkpoint: YOLOv8n object detection, gated by motion.py so
# detection only runs on frames that actually have movement in them.

# This is where you should first SEE the CPU savings from the motion
# gate - watch your CPU usage (Task Manager) and notice it spikes only
# when the gate is open, not on every single frame.

# First run will auto-download yolov8n.pt (~6MB) - needs internet once.

# Usage:
#     python core/detector.py
# """

# import sys
# import time
# import cv2
# from ultralytics import YOLO

# from motion import compute_motion_score, is_motion_significant, MOTION_THRESHOLD

# # Classes we actually care about for this project (COCO class names).
# # Filtering here means we ignore irrelevant detections (chairs, cups, etc.)
# # even though the model technically detects 80 classes.
# RELEVANT_CLASSES = {"person", "dog", "car", "truck", "motorcycle", "bus"}


# class ObjectDetector:
#     def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.4):
#         print("Loading YOLOv8n model (first run downloads it)...")
#         self.model = YOLO(model_path)
#         self.confidence = confidence
#         # build a name->id lookup so we can filter fast
#         self.class_names = self.model.names  # {id: name}

#     def detect(self, frame):
#         """
#         Runs detection on a single frame. Returns a list of dicts:
#         [{"class": "person", "confidence": 0.87, "bbox": (x1,y1,x2,y2)}, ...]
#         Only includes classes in RELEVANT_CLASSES.
#         """
#         results = self.model(frame, verbose=False, conf=self.confidence)[0]
#         detections = []
#         for box in results.boxes:
#             cls_id = int(box.cls[0])
#             cls_name = self.class_names[cls_id]
#             if cls_name not in RELEVANT_CLASSES:
#                 continue
#             x1, y1, x2, y2 = box.xyxy[0].tolist()
#             detections.append({
#                 "class": cls_name,
#                 "confidence": float(box.conf[0]),
#                 "bbox": (int(x1), int(y1), int(x2), int(y2)),
#             })
#         return detections


# def draw_detections(frame, detections):
#     for det in detections:
#         x1, y1, x2, y2 = det["bbox"]
#         label = f'{det["class"]} {det["confidence"]:.2f}'
#         cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)
#         cv2.putText(frame, label, (x1, max(y1 - 8, 12)),
#                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 2)
#     return frame


# def main():
#     source = sys.argv[1] if len(sys.argv) > 1 else 0
#     if isinstance(source, str) and source.isdigit():
#         source = int(source)

#     cap = cv2.VideoCapture(source)
#     if not cap.isOpened():
#         raise RuntimeError(f"Could not open video source: {source}")

#     detector = ObjectDetector()

#     ok, prev_frame = cap.read()
#     if not ok:
#         raise RuntimeError("Could not read first frame.")
#     prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

#     print("Detector running (gated by motion). Press 'q' to quit.\n")

#     frames_processed = 0
#     frames_skipped = 0

#     while True:
#         ok, frame = cap.read()
#         if not ok:
#             break

#         curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         score = compute_motion_score(prev_gray, curr_gray)
#         gate_open = is_motion_significant(score)
#         prev_gray = curr_gray

#         if gate_open:
#             t0 = time.time()
#             detections = detector.detect(frame)
#             elapsed_ms = (time.time() - t0) * 1000
#             frames_processed += 1
#             frame = draw_detections(frame, detections)
#             if detections:
#                 names = ", ".join(f'{d["class"]}({d["confidence"]:.2f})' for d in detections)
#                 print(f"[{elapsed_ms:.0f}ms] motion={score:.3f} -> detected: {names}")
#         else:
#             frames_skipped += 1

#         # overlay stats so you can see the gate saving work in real time
#         cv2.putText(
#             frame, f"processed:{frames_processed}  skipped:{frames_skipped}",
#             (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
#         )
#         cv2.imshow("fight - detector checkpoint", frame)

#         if cv2.waitKey(1) & 0xFF == ord("q"):
#             break

#     cap.release()
#     cv2.destroyAllWindows()
#     print(f"\nDone. Frames processed: {frames_processed}, skipped: {frames_skipped}")


# if __name__ == "__main__":
#     main()

"""
detector.py

Step 3 checkpoint: YOLOv8n object detection, gated by motion.py so
detection only runs on frames that actually have movement in them.

This is where you should first SEE the CPU savings from the motion
gate - watch your CPU usage (Task Manager) and notice it spikes only
when the gate is open, not on every single frame.

First run will auto-download yolov8n.pt (~6MB) - needs internet once.

Usage:
    python core/detector.py
"""

import sys
import time
import cv2
from ultralytics import YOLO

from motion import compute_motion_score, is_motion_significant, MOTION_THRESHOLD

# Classes we actually care about for this project (COCO class names).
# Filtering here means we ignore irrelevant detections (chairs, cups, etc.)
# even though the model technically detects 80 classes.
#
# Animal classes included for animal-attack detection: dog, cat, horse,
# sheep, cow, elephant, bear - these are all standard COCO classes YOLOv8n
# already knows, no extra training/model needed.
RELEVANT_CLASSES = {
    "person", "dog", "cat", "horse", "sheep", "cow", "elephant", "bear",
    "car", "truck", "motorcycle", "bus","tiger","lion"
}

# Subset used specifically for animal-attack rule matching (alerts/animal_attack.py)
ANIMAL_CLASSES = {"dog", "cat", "horse", "sheep", "cow", "elephant", "bear","tiger","lion"}


class ObjectDetector:
    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.4):
        print("Loading YOLOv8n model (first run downloads it)...")
        self.model = YOLO(model_path)
        self.confidence = confidence
        # build a name->id lookup so we can filter fast
        self.class_names = self.model.names  # {id: name}

    def detect(self, frame):
        """
        Runs detection on a single frame. Returns a list of dicts:
        [{"class": "person", "confidence": 0.87, "bbox": (x1,y1,x2,y2)}, ...]
        Only includes classes in RELEVANT_CLASSES.
        """
        results = self.model(frame, verbose=False, conf=self.confidence)[0]
        detections = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            cls_name = self.class_names[cls_id]
            if cls_name not in RELEVANT_CLASSES:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detections.append({
                "class": cls_name,
                "confidence": float(box.conf[0]),
                "bbox": (int(x1), int(y1), int(x2), int(y2)),
            })
        return detections


def draw_detections(frame, detections):
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f'{det["class"]} {det["confidence"]:.2f}'
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)
        cv2.putText(frame, label, (x1, max(y1 - 8, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 2)
    return frame


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    detector = ObjectDetector()

    ok, prev_frame = cap.read()
    if not ok:
        raise RuntimeError("Could not read first frame.")
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

    print("Detector running (gated by motion). Press 'q' to quit.\n")

    frames_processed = 0
    frames_skipped = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        score = compute_motion_score(prev_gray, curr_gray)
        gate_open = is_motion_significant(score)
        prev_gray = curr_gray

        if gate_open:
            t0 = time.time()
            detections = detector.detect(frame)
            elapsed_ms = (time.time() - t0) * 1000
            frames_processed += 1
            frame = draw_detections(frame, detections)
            if detections:
                names = ", ".join(f'{d["class"]}({d["confidence"]:.2f})' for d in detections)
                print(f"[{elapsed_ms:.0f}ms] motion={score:.3f} -> detected: {names}")
        else:
            frames_skipped += 1

        # overlay stats so you can see the gate saving work in real time
        cv2.putText(
            frame, f"processed:{frames_processed}  skipped:{frames_skipped}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
        )
        cv2.imshow("fight - detector checkpoint", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print(f"\nDone. Frames processed: {frames_processed}, skipped: {frames_skipped}")


if __name__ == "__main__":
    main()