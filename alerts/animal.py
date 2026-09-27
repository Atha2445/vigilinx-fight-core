# # """
# # alerts/animal_attack.py

# # Same cascade pattern as assault.py: cheap rule-based candidate flagging
# # (person-to-animal proximity + motion), confirmed by the local VLM.

# # Covers dog, cat, horse, sheep, cow, elephant, bear - any COCO animal
# # class detector.py is configured to detect (see ANIMAL_CLASSES there).

# # Usage:
# #     python alerts/animal_attack.py [source] [tilt_deg]
# #     python alerts/animal_attack.py 0 10   -> EYE_LEVEL
# #     python alerts/animal_attack.py 0 25   -> ANGLED_LOW
# #     python alerts/animal_attack.py 0 50   -> ANGLED_HIGH
# # """

# # import sys
# # import os
# # import time
# # import itertools
# # import cv2

# # sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

# # from motion import compute_motion_score, is_motion_significant
# # from detector import ObjectDetector, draw_detections, ANIMAL_CLASSES
# # from camera_profile import CameraProfile, MountAngle
# # from vlm import confirm_candidate_async, is_confirmed

# # # Animal attacks can have more spatial spread than person-to-person fights
# # # (an animal lunging covers ground fast) - looser than the 0.6m assault
# # # threshold.
# # PROXIMITY_METERS = 1.0

# # COOLDOWN_SECONDS = 5.0

# # MAX_PROCESSING_WIDTH = 960

# # # A rapid-approach motion score above this (from the same Farneback
# # # motion gate you already have) is treated as a meaningful extra signal,
# # # on top of proximity, when deciding whether to flag a candidate.
# # # This is a coarser substitute for real per-object velocity tracking
# # # (which needs ByteTrack - not built yet).
# # RAPID_MOTION_THRESHOLD = 1.5


# # def resize_for_processing(frame, max_width: int = MAX_PROCESSING_WIDTH):
# #     h, w = frame.shape[:2]
# #     if w <= max_width:
# #         return frame
# #     scale = max_width / w
# #     new_size = (max_width, int(h * scale))
# #     return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


# # class AnimalAttackAlert:
# #     """
# #     Rule-based candidate flagger for person-animal proximity events.

# #     Same honesty note as AssaultAlert: this does NOT confirm an attack -
# #     it flags "this person+animal pair is close enough, with enough
# #     motion, that it's worth a VLM look."
# #     """

# #     def __init__(self, profile: CameraProfile):
# #         self.profile = profile
# #         self._last_alert_time = {}

# #     def check(self, detections: list[dict], motion_score: float) -> list[dict]:
# #         """
# #         detections: output of ObjectDetector.detect() for one frame.
# #         motion_score: the frame's overall motion magnitude (from
# #         motion.compute_motion_score) - used as the rapid-approach proxy
# #         signal described above.
# #         """
# #         persons = [d for d in detections if d["class"] == "person"]
# #         animals = [d for d in detections if d["class"] in ANIMAL_CLASSES]
# #         candidates = []

# #         for person, animal in itertools.product(persons, animals):
# #             p_box = person["bbox"]
# #             a_box = animal["bbox"]

# #             p_cx = (p_box[0] + p_box[2]) / 2
# #             p_cy = (p_box[1] + p_box[3]) / 2
# #             a_cx = (a_box[0] + a_box[2]) / 2
# #             a_cy = (a_box[1] + a_box[3]) / 2
# #             pixel_dist = ((p_cx - a_cx) ** 2 + (p_cy - a_cy) ** 2) ** 0.5

# #             p_height = p_box[3] - p_box[1]
# #             threshold_px = self.profile.proximity_threshold_px(
# #                 real_world_meters=PROXIMITY_METERS, bbox_height_px=p_height
# #             )

# #             if pixel_dist >= threshold_px:
# #                 continue

# #             # Rapid-motion tag: coarse proxy for "is something moving fast
# #             # right now" - not per-object velocity, just overall frame
# #             # motion at the moment proximity was detected. Real per-animal
# #             # velocity needs ByteTrack (not built yet) for a track history
# #             # to compute speed from.
# #             rapid_motion = motion_score >= RAPID_MOTION_THRESHOLD
# #             extra_signal = "rapid_motion_detected" if rapid_motion else "proximity_only_no_rapid_motion"

# #             pair_key = (
# #                 animal["class"],
# #                 round(p_cx / 50), round(p_cy / 50),
# #                 round(a_cx / 50), round(a_cy / 50),
# #             )
# #             now = time.time()
# #             last = self._last_alert_time.get(pair_key, 0)
# #             if now - last < COOLDOWN_SECONDS:
# #                 continue
# #             self._last_alert_time[pair_key] = now

# #             candidates.append({
# #                 "type": "animal_attack_candidate",
# #                 "animal_class": animal["class"],
# #                 "pixel_distance": round(pixel_dist, 1),
# #                 "threshold_px": round(threshold_px, 1),
# #                 "mount_angle": self.profile.mount_angle.value,
# #                 "extra_signal": extra_signal,
# #                 "motion_score": round(motion_score, 3),
# #                 "person_bbox": p_box,
# #                 "animal_bbox": a_box,
# #                 "timestamp": now,
# #             })

# #         return candidates


# # def main():
# #     source = sys.argv[1] if len(sys.argv) > 1 else 0
# #     if isinstance(source, str) and source.isdigit():
# #         source = int(source)

# #     cap = cv2.VideoCapture(source)
# #     if not cap.isOpened():
# #         raise RuntimeError(f"Could not open video source: {source}")

# #     tilt_deg = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
# #     profile = CameraProfile(camera_id="test_camera", tilt_deg=tilt_deg)
# #     print(f"Using camera profile: {profile.mount_angle.value} (tilt={tilt_deg}, uncalibrated, using bbox-height fallback)")
# #     print(f"Active modules for this angle: {profile.active_modules()}")
# #     print(f"Watching for animals: {sorted(ANIMAL_CLASSES)}\n")

# #     detector = ObjectDetector()
# #     alert = AnimalAttackAlert(profile)

# #     ok, prev_frame = cap.read()
# #     if not ok:
# #         raise RuntimeError("Could not read first frame.")
# #     prev_frame = resize_for_processing(prev_frame)
# #     prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

# #     print("Animal attack alert checkpoint running. Press 'q' to quit.")
# #     print("(Make sure LM Studio's local server is running with Kimi-VL loaded)\n")

# #     pending_confirmations = []

# #     while True:
# #         ok, frame = cap.read()
# #         if not ok:
# #             break

# #         frame = resize_for_processing(frame)
# #         curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
# #         score = compute_motion_score(prev_gray, curr_gray)
# #         prev_gray = curr_gray

# #         if is_motion_significant(score):
# #             detections = detector.detect(frame)
# #             frame = draw_detections(frame, detections)

# #             candidates = alert.check(detections, motion_score=score)
# #             for c in candidates:
# #                 print(
# #                     f"[CANDIDATE FLAGGED] animal_attack ({c['animal_class']}) - "
# #                     f"angle={c['mount_angle']} pixel_dist={c['pixel_distance']} "
# #                     f"threshold={c['threshold_px']} extra_signal={c['extra_signal']} "
# #                     f"motion={c['motion_score']} at {time.strftime('%H:%M:%S', time.localtime(c['timestamp']))}"
# #                 )
# #                 print("  -> dispatched to local VLM in background (video keeps running)...")

# #                 future = confirm_candidate_async(
# #                     frame,
# #                     [c["person_bbox"], c["animal_bbox"]],
# #                     "animal_attack_candidate",
# #                     mount_angle=c["mount_angle"],
# #                 )
# #                 pending_confirmations.append({"future": future, "candidate": c})

# #         still_pending = []
# #         for item in pending_confirmations:
# #             future = item["future"]
# #             c = item["candidate"]
# #             if future.done():
# #                 result = future.result()
# #                 if result.get("error"):
# #                     print(f"  -> VLM ERROR for {c['animal_class']} candidate: {result['error']}")
# #                 elif is_confirmed(result):
# #                     print(
# #                         f"  -> CONFIRMED {c['animal_class']} attack "
# #                         f"(confidence={result['confidence']:.2f}, "
# #                         f"{result.get('latency_seconds', '?')}s): {result['description']}"
# #                     )
# #                 else:
# #                     print(
# #                         f"  -> NOT confirmed (confidence={result.get('confidence', 0):.2f}, "
# #                         f"{result.get('latency_seconds', '?')}s): {result.get('description', '')}"
# #                     )
# #             else:
# #                 still_pending.append(item)
# #         pending_confirmations = still_pending

# #         if pending_confirmations:
# #             cv2.putText(
# #                 frame, f"VLM confirming... ({len(pending_confirmations)} pending)",
# #                 (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2,
# #             )

# #         cv2.imshow("fight - animal attack alert checkpoint", frame)
# #         if cv2.waitKey(1) & 0xFF == ord("q"):
# #             break

# #     cap.release()
# #     cv2.destroyAllWindows()


# # if __name__ == "__main__":
# #     main()
    

# """
# alerts/animal_attack.py

# Same cascade pattern as assault.py: cheap rule-based candidate flagging
# (person-to-animal proximity + motion), confirmed by the local VLM.

# Covers dog, cat, horse, sheep, cow, elephant, bear - any COCO animal
# class detector.py is configured to detect (see ANIMAL_CLASSES there).

# Usage:
#     python alerts/animal_attack.py [source] [tilt_deg]
#     python alerts/animal_attack.py 0 10   -> EYE_LEVEL
#     python alerts/animal_attack.py 0 25   -> ANGLED_LOW
#     python alerts/animal_attack.py 0 50   -> ANGLED_HIGH
# """

# import sys
# import os
# import time
# import itertools
# import cv2

# sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

# from motion import compute_motion_score, is_motion_significant
# from detector import ObjectDetector, draw_detections, ANIMAL_CLASSES
# from camera_profile import CameraProfile, MountAngle
# from vlm import confirm_candidate_async, is_confirmed

# # Animal attacks can have more spatial spread than person-to-person fights
# # (an animal lunging covers ground fast) - looser than the 0.6m assault
# # threshold.
# PROXIMITY_METERS = 1.0

# COOLDOWN_SECONDS = 5.0

# MAX_PROCESSING_WIDTH = 960

# # A rapid-approach motion score above this (from the same Farneback
# # motion gate you already have) is treated as a meaningful extra signal,
# # on top of proximity, when deciding whether to flag a candidate.
# # This is a coarser substitute for real per-object velocity tracking
# # (which needs ByteTrack - not built yet).
# RAPID_MOTION_THRESHOLD = 1.5


# def resize_for_processing(frame, max_width: int = MAX_PROCESSING_WIDTH):
#     h, w = frame.shape[:2]
#     if w <= max_width:
#         return frame
#     scale = max_width / w
#     new_size = (max_width, int(h * scale))
#     return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


# class AnimalAttackAlert:
#     """
#     Rule-based candidate flagger for person-animal proximity events.

#     Same honesty note as AssaultAlert: this does NOT confirm an attack -
#     it flags "this person+animal pair is close enough, with enough
#     motion, that it's worth a VLM look."
#     """

#     def __init__(self, profile: CameraProfile):
#         self.profile = profile
#         self._last_alert_time = {}

#     def check(self, detections: list[dict], motion_score: float) -> list[dict]:
#         """
#         detections: output of ObjectDetector.detect() for one frame.
#         motion_score: the frame's overall motion magnitude (from
#         motion.compute_motion_score) - used as the rapid-approach proxy
#         signal described above.
#         """
#         persons = [d for d in detections if d["class"] == "person"]
#         animals = [d for d in detections if d["class"] in ANIMAL_CLASSES]
#         candidates = []

#         for person, animal in itertools.product(persons, animals):
#             p_box = person["bbox"]
#             a_box = animal["bbox"]

#             p_cx = (p_box[0] + p_box[2]) / 2
#             p_cy = (p_box[1] + p_box[3]) / 2
#             a_cx = (a_box[0] + a_box[2]) / 2
#             a_cy = (a_box[1] + a_box[3]) / 2
#             pixel_dist = ((p_cx - a_cx) ** 2 + (p_cy - a_cy) ** 2) ** 0.5

#             p_height = p_box[3] - p_box[1]
#             threshold_px = self.profile.proximity_threshold_px(
#                 real_world_meters=PROXIMITY_METERS, bbox_height_px=p_height
#             )

#             if pixel_dist >= threshold_px:
#                 continue

#             # Rapid-motion tag: coarse proxy for "is something moving fast
#             # right now" - not per-object velocity, just overall frame
#             # motion at the moment proximity was detected. Real per-animal
#             # velocity needs ByteTrack (not built yet) for a track history
#             # to compute speed from. This signal applies regardless of
#             # camera angle - it's the one universal extra signal here.
#             rapid_motion = motion_score >= RAPID_MOTION_THRESHOLD
#             motion_signal = "rapid_motion_detected" if rapid_motion else "proximity_only_no_rapid_motion"

#             # --- ANGLE-SPECIFIC LOGIC BRANCHES HERE ---
#             # Same integration point as AssaultAlert. For animal attacks,
#             # the angle-specific signal is different from fist-to-head
#             # (animals don't have that pose feature) - the relevant signal
#             # is body-posture/lunge-angle for eye-level/angled-low views,
#             # vs. pure ground-plane closing-distance for angled-high views
#             # where posture is harder to see from above.
#             angle_signal = None

#             if self.profile.mount_angle in (MountAngle.EYE_LEVEL, MountAngle.ANGLED_LOW):
#                 if self.profile.is_module_active("pose_fight_detection"):
#                     # PLACEHOLDER - once core/pose.py exists, this would
#                     # check the animal's body posture (lunging/crouching
#                     # vs standing normally) - not built yet.
#                     angle_signal = "lunge_posture_pending_pose_module"

#             elif self.profile.mount_angle == MountAngle.ANGLED_HIGH:
#                 if self.profile.is_module_active("ground_plane_proximity"):
#                     # PLACEHOLDER - real ground-plane math needs the same
#                     # per-camera calibration wizard discussed for
#                     # AssaultAlert - not built yet, currently falls back
#                     # to the same bbox-height proximity math as other angles.
#                     angle_signal = "ground_plane_closing_distance_pending_calibration"

#             extra_signal = f"{motion_signal}|{angle_signal}" if angle_signal else motion_signal

#             pair_key = (
#                 animal["class"],
#                 round(p_cx / 50), round(p_cy / 50),
#                 round(a_cx / 50), round(a_cy / 50),
#             )
#             now = time.time()
#             last = self._last_alert_time.get(pair_key, 0)
#             if now - last < COOLDOWN_SECONDS:
#                 continue
#             self._last_alert_time[pair_key] = now

#             candidates.append({
#                 "type": "animal_attack_candidate",
#                 "animal_class": animal["class"],
#                 "pixel_distance": round(pixel_dist, 1),
#                 "threshold_px": round(threshold_px, 1),
#                 "mount_angle": self.profile.mount_angle.value,
#                 "extra_signal": extra_signal,
#                 "motion_score": round(motion_score, 3),
#                 "person_bbox": p_box,
#                 "animal_bbox": a_box,
#                 "timestamp": now,
#             })

#         return candidates


# def main():
#     source = sys.argv[1] if len(sys.argv) > 1 else 0
#     if isinstance(source, str) and source.isdigit():
#         source = int(source)

#     cap = cv2.VideoCapture(source)
#     if not cap.isOpened():
#         raise RuntimeError(f"Could not open video source: {source}")

#     tilt_deg = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
#     profile = CameraProfile(camera_id="test_camera", tilt_deg=tilt_deg)
#     print(f"Using camera profile: {profile.mount_angle.value} (tilt={tilt_deg}, uncalibrated, using bbox-height fallback)")
#     print(f"Active modules for this angle: {profile.active_modules()}")
#     print(f"Watching for animals: {sorted(ANIMAL_CLASSES)}\n")

#     detector = ObjectDetector()
#     alert = AnimalAttackAlert(profile)

#     ok, prev_frame = cap.read()
#     if not ok:
#         raise RuntimeError("Could not read first frame.")
#     prev_frame = resize_for_processing(prev_frame)
#     prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

#     print("Animal attack alert checkpoint running. Press 'q' to quit.")
#     print("(Make sure LM Studio's local server is running with Kimi-VL loaded)\n")

#     pending_confirmations = []

#     while True:
#         ok, frame = cap.read()
#         if not ok:
#             break

#         frame = resize_for_processing(frame)
#         curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         score = compute_motion_score(prev_gray, curr_gray)
#         prev_gray = curr_gray

#         if is_motion_significant(score):
#             detections = detector.detect(frame)
#             frame = draw_detections(frame, detections)

#             candidates = alert.check(detections, motion_score=score)
#             for c in candidates:
#                 print(
#                     f"[CANDIDATE FLAGGED] animal_attack ({c['animal_class']}) - "
#                     f"angle={c['mount_angle']} pixel_dist={c['pixel_distance']} "
#                     f"threshold={c['threshold_px']} extra_signal={c['extra_signal']} "
#                     f"motion={c['motion_score']} at {time.strftime('%H:%M:%S', time.localtime(c['timestamp']))}"
#                 )
#                 print("  -> dispatched to local VLM in background (video keeps running)...")

#                 future = confirm_candidate_async(
#                     frame,
#                     [c["person_bbox"], c["animal_bbox"]],
#                     "animal_attack_candidate",
#                     mount_angle=c["mount_angle"],
#                 )
#                 pending_confirmations.append({"future": future, "candidate": c})

#         still_pending = []
#         for item in pending_confirmations:
#             future = item["future"]
#             c = item["candidate"]
#             if future.done():
#                 result = future.result()
#                 if result.get("error"):
#                     print(f"  -> VLM ERROR for {c['animal_class']} candidate: {result['error']}")
#                 elif is_confirmed(result):
#                     print(
#                         f"  -> CONFIRMED {c['animal_class']} attack "
#                         f"(confidence={result['confidence']:.2f}, "
#                         f"{result.get('latency_seconds', '?')}s): {result['description']}"
#                     )
#                 else:
#                     print(
#                         f"  -> NOT confirmed (confidence={result.get('confidence', 0):.2f}, "
#                         f"{result.get('latency_seconds', '?')}s): {result.get('description', '')}"
#                     )
#             else:
#                 still_pending.append(item)
#         pending_confirmations = still_pending

#         if pending_confirmations:
#             cv2.putText(
#                 frame, f"VLM confirming... ({len(pending_confirmations)} pending)",
#                 (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2,
#             )

#         cv2.imshow("fight - animal attack alert checkpoint", frame)
#         if cv2.waitKey(1) & 0xFF == ord("q"):
#             break

#     cap.release()
#     cv2.destroyAllWindows()


# if __name__ == "__main__":
#     main()

"""
alerts/animal_attack.py

Same cascade pattern as assault.py: cheap rule-based candidate flagging
(person-to-animal proximity + motion), confirmed by the local VLM.

Covers dog, cat, horse, sheep, cow, elephant, bear - any COCO animal
class detector.py is configured to detect (see ANIMAL_CLASSES there).

Usage:
    python alerts/animal_attack.py [source] [tilt_deg]
    python alerts/animal_attack.py 0 10   -> EYE_LEVEL
    python alerts/animal_attack.py 0 25   -> ANGLED_LOW
    python alerts/animal_attack.py 0 50   -> ANGLED_HIGH
"""

import sys
import os
import time
import itertools
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from motion import compute_motion_score, is_motion_significant
from detector import ObjectDetector, draw_detections, ANIMAL_CLASSES
from camera_profile import CameraProfile, MountAngle
from vlm import confirm_candidate_async, is_confirmed

# Animal attacks can have more spatial spread than person-to-person fights
# (an animal lunging covers ground fast) - looser than the 0.6m assault
# threshold.
PROXIMITY_METERS = 1.0

COOLDOWN_SECONDS = 5.0

MAX_PROCESSING_WIDTH = 960

# A rapid-approach motion score above this (from the same Farneback
# motion gate you already have) is treated as a meaningful extra signal,
# on top of proximity, when deciding whether to flag a candidate.
# This is a coarser substitute for real per-object velocity tracking
# (which needs ByteTrack - not built yet).
RAPID_MOTION_THRESHOLD = 1.5


def resize_for_processing(frame, max_width: int = MAX_PROCESSING_WIDTH):
    """
    Checks BOTH width and height (see assault.py for why this matters
    for portrait-orientation videos).
    """
    h, w = frame.shape[:2]
    if w <= max_width and h <= max_width:
        return frame
    scale = max_width / max(w, h)
    new_size = (int(w * scale), int(h * scale))
    return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


class AnimalAttackAlert:
    """
    Rule-based candidate flagger for person-animal proximity events.

    Same honesty note as AssaultAlert: this does NOT confirm an attack -
    it flags "this person+animal pair is close enough, with enough
    motion, that it's worth a VLM look."
    """

    def __init__(self, profile: CameraProfile):
        self.profile = profile
        self._last_alert_time = {}

    def check(self, detections: list[dict], motion_score: float) -> list[dict]:
        """
        detections: output of ObjectDetector.detect() for one frame.
        motion_score: the frame's overall motion magnitude (from
        motion.compute_motion_score) - used as the rapid-approach proxy
        signal described above.
        """
        persons = [d for d in detections if d["class"] == "person"]
        animals = [d for d in detections if d["class"] in ANIMAL_CLASSES]
        candidates = []

        for person, animal in itertools.product(persons, animals):
            p_box = person["bbox"]
            a_box = animal["bbox"]

            p_cx = (p_box[0] + p_box[2]) / 2
            p_cy = (p_box[1] + p_box[3]) / 2
            a_cx = (a_box[0] + a_box[2]) / 2
            a_cy = (a_box[1] + a_box[3]) / 2
            pixel_dist = ((p_cx - a_cx) ** 2 + (p_cy - a_cy) ** 2) ** 0.5

            p_height = p_box[3] - p_box[1]
            threshold_px = self.profile.proximity_threshold_px(
                real_world_meters=PROXIMITY_METERS, bbox_height_px=p_height
            )

            if pixel_dist >= threshold_px:
                continue

            # Rapid-motion tag: coarse proxy for "is something moving fast
            # right now" - not per-object velocity, just overall frame
            # motion at the moment proximity was detected. Real per-animal
            # velocity needs ByteTrack (not built yet) for a track history
            # to compute speed from. This signal applies regardless of
            # camera angle - it's the one universal extra signal here.
            rapid_motion = motion_score >= RAPID_MOTION_THRESHOLD
            motion_signal = "rapid_motion_detected" if rapid_motion else "proximity_only_no_rapid_motion"

            # --- ANGLE-SPECIFIC LOGIC BRANCHES HERE ---
            # Same integration point as AssaultAlert. For animal attacks,
            # the angle-specific signal is different from fist-to-head
            # (animals don't have that pose feature) - the relevant signal
            # is body-posture/lunge-angle for eye-level/angled-low views,
            # vs. pure ground-plane closing-distance for angled-high views
            # where posture is harder to see from above.
            angle_signal = None

            if self.profile.mount_angle in (MountAngle.EYE_LEVEL, MountAngle.ANGLED_LOW):
                if self.profile.is_module_active("pose_fight_detection"):
                    # PLACEHOLDER - once core/pose.py exists, this would
                    # check the animal's body posture (lunging/crouching
                    # vs standing normally) - not built yet.
                    angle_signal = "lunge_posture_pending_pose_module"

            elif self.profile.mount_angle == MountAngle.ANGLED_HIGH:
                if self.profile.is_module_active("ground_plane_proximity"):
                    # PLACEHOLDER - real ground-plane math needs the same
                    # per-camera calibration wizard discussed for
                    # AssaultAlert - not built yet, currently falls back
                    # to the same bbox-height proximity math as other angles.
                    angle_signal = "ground_plane_closing_distance_pending_calibration"

            extra_signal = f"{motion_signal}|{angle_signal}" if angle_signal else motion_signal

            pair_key = (
                animal["class"],
                round(p_cx / 50), round(p_cy / 50),
                round(a_cx / 50), round(a_cy / 50),
            )
            now = time.time()
            last = self._last_alert_time.get(pair_key, 0)
            if now - last < COOLDOWN_SECONDS:
                continue
            self._last_alert_time[pair_key] = now

            candidates.append({
                "type": "animal_attack_candidate",
                "animal_class": animal["class"],
                "pixel_distance": round(pixel_dist, 1),
                "threshold_px": round(threshold_px, 1),
                "mount_angle": self.profile.mount_angle.value,
                "extra_signal": extra_signal,
                "motion_score": round(motion_score, 3),
                "person_bbox": p_box,
                "animal_bbox": a_box,
                "timestamp": now,
            })

        return candidates


def main():
    WINDOW_NAME = "fight - animal attack alert checkpoint"
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 960, 720)

    tilt_deg = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    profile = CameraProfile(camera_id="test_camera", tilt_deg=tilt_deg)
    print(f"Using camera profile: {profile.mount_angle.value} (tilt={tilt_deg}, uncalibrated, using bbox-height fallback)")
    print(f"Active modules for this angle: {profile.active_modules()}")
    print(f"Watching for animals: {sorted(ANIMAL_CLASSES)}\n")

    detector = ObjectDetector()
    alert = AnimalAttackAlert(profile)

    ok, prev_frame = cap.read()
    if not ok:
        raise RuntimeError("Could not read first frame.")
    prev_frame = resize_for_processing(prev_frame)
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

    print("Animal attack alert checkpoint running. Press 'q' to quit.")
    print("(Make sure LM Studio's local server is running with Kimi-VL loaded)\n")

    pending_confirmations = []

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame = resize_for_processing(frame)
        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        score = compute_motion_score(prev_gray, curr_gray)
        prev_gray = curr_gray

        if is_motion_significant(score):
            detections = detector.detect(frame)
            frame = draw_detections(frame, detections)

            candidates = alert.check(detections, motion_score=score)
            for c in candidates:
                print(
                    f"[CANDIDATE FLAGGED] animal_attack ({c['animal_class']}) - "
                    f"angle={c['mount_angle']} pixel_dist={c['pixel_distance']} "
                    f"threshold={c['threshold_px']} extra_signal={c['extra_signal']} "
                    f"motion={c['motion_score']} at {time.strftime('%H:%M:%S', time.localtime(c['timestamp']))}"
                )
                print("  -> dispatched to local VLM in background (video keeps running)...")

                future = confirm_candidate_async(
                    frame,
                    [c["person_bbox"], c["animal_bbox"]],
                    "animal_attack_candidate",
                    mount_angle=c["mount_angle"],
                )
                pending_confirmations.append({"future": future, "candidate": c})

        still_pending = []
        for item in pending_confirmations:
            future = item["future"]
            c = item["candidate"]
            if future.done():
                result = future.result()
                if result.get("error"):
                    print(f"  -> VLM ERROR for {c['animal_class']} candidate: {result['error']}")
                elif is_confirmed(result):
                    print(
                        f"  -> CONFIRMED {c['animal_class']} attack "
                        f"(confidence={result['confidence']:.2f}, "
                        f"{result.get('latency_seconds', '?')}s): {result['description']}"
                    )
                else:
                    print(
                        f"  -> NOT confirmed (confidence={result.get('confidence', 0):.2f}, "
                        f"{result.get('latency_seconds', '?')}s): {result.get('description', '')}"
                    )
            else:
                still_pending.append(item)
        pending_confirmations = still_pending

        if pending_confirmations:
            cv2.putText(
                frame, f"VLM confirming... ({len(pending_confirmations)} pending)",
                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2,
            )

        cv2.imshow(WINDOW_NAME, frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()