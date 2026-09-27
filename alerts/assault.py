# # # # """
# # # # alerts/assault.py

# # # # Step 4 checkpoint: your first working alert rule, end-to-end.

# # # # Pipeline: video_source -> motion gate -> detector -> THIS module -> console print

# # # # No VLM confirmation yet (that's the next and final piece). This just
# # # # proves the full candidate-flagging logic works before we add the
# # # # expensive VLM confirmation step on top.

# # # # Usage:
# # # #     python alerts/assault.py
# # # # """

# # # # import sys
# # # # import os
# # # # import time
# # # # import itertools
# # # # import cv2

# # # # # allow importing from core/ when running this file directly
# # # # sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

# # # # from motion import compute_motion_score, is_motion_significant
# # # # from detector import ObjectDetector, draw_detections
# # # # from camera_profile import CameraProfile, MountAngle

# # # # # How close two people need to be (in meters) to count as a candidate.
# # # # # 0.6m is "within arm's reach" - tune this after watching real triggers.
# # # # PROXIMITY_METERS = 0.6

# # # # # Require at least this much cooldown (seconds) before re-flagging the
# # # # # same pair of people, so one ongoing event doesn't spam the console.
# # # # COOLDOWN_SECONDS = 5.0


# # # # class AssaultAlert:
# # # #     """
# # # #     Rule-based candidate flagger. Checks every pair of detected persons
# # # #     in a frame - if two people are closer than the camera-appropriate
# # # #     threshold, flags a candidate.

# # # #     This does NOT confirm anything is actually a fight - it just says
# # # #     "this pair is close enough that a human/VLM should take a look."
# # # #     That confirmation step comes next.
# # # #     """

# # # #     def __init__(self, profile: CameraProfile):
# # # #         self.profile = profile
# # # #         self._last_alert_time = {}  # (track pair) -> timestamp, for cooldown

# # # #     def check(self, detections: list[dict]) -> list[dict]:
# # # #         """
# # # #         detections: output of ObjectDetector.detect() for one frame.
# # # #         Returns a list of candidate dicts, one per flagged pair.

# # # #         THIS is the integration point for your 3 shortlisted camera
# # # #         angles. The proximity check below runs for ALL angles (it's the
# # # #         one signal that's valid everywhere), but angle-specific extra
# # # #         checks get added/removed here based on the profile.
# # # #         """
# # # #         persons = [d for d in detections if d["class"] == "person"]
# # # #         candidates = []

# # # #         for a, b in itertools.combinations(persons, 2):
# # # #             a_box = a["bbox"]
# # # #             b_box = b["bbox"]

# # # #             a_cx = (a_box[0] + a_box[2]) / 2
# # # #             a_cy = (a_box[1] + a_box[3]) / 2
# # # #             b_cx = (b_box[0] + b_box[2]) / 2
# # # #             b_cy = (b_box[1] + b_box[3]) / 2
# # # #             pixel_dist = ((a_cx - b_cx) ** 2 + (a_cy - b_cy) ** 2) ** 0.5

# # # #             a_height = a_box[3] - a_box[1]
# # # #             threshold_px = self.profile.proximity_threshold_px(
# # # #                 real_world_meters=PROXIMITY_METERS, bbox_height_px=a_height
# # # #             )

# # # #             # base signal: are they close? (valid for every angle)
# # # #             is_close = pixel_dist < threshold_px
# # # #             if not is_close:
# # # #                 continue

# # # #             # --- ANGLE-SPECIFIC LOGIC BRANCHES HERE ---
# # # #             # This is the exact integration point for your 3 shortlisted
# # # #             # angles (EYE_LEVEL, ANGLED_LOW, ANGLED_HIGH). Each branch can
# # # #             # add extra confirming signals or adjust confidence, using
# # # #             # whatever that angle can reliably see.
# # # #             extra_signal = None
# # # #             confidence_boost = 0.0

# # # #             if self.profile.mount_angle in (MountAngle.EYE_LEVEL, MountAngle.ANGLED_LOW):
# # # #                 # Full pose visibility at this angle - once core/pose.py
# # # #                 # exists, call it here for fist-to-head distance.
# # # #                 if self.profile.is_module_active("fist_to_head_check"):
# # # #                     # PLACEHOLDER - wire in real pose check when core/pose.py is built:
# # # #                     # extra_signal = check_fist_to_head(frame, a_box, b_box)
# # # #                     extra_signal = "fist_to_head_pending_pose_module"
# # # #                     confidence_boost = 0.2

# # # #             elif self.profile.mount_angle == MountAngle.ANGLED_HIGH:
# # # #                 # Foreshortening makes fist-to-head unreliable at this angle
# # # #                 # (see MODULE_MATRIX - fist_to_head_check is False here).
# # # #                 # Rely on proximity + motion intensity instead.
# # # #                 if self.profile.is_module_active("ground_plane_proximity"):
# # # #                     extra_signal = "ground_plane_proximity_used"
# # # #                     confidence_boost = 0.1

# # # #             # simple cooldown key based on rounded position, since we don't
# # # #             # have persistent track IDs yet (that's ByteTrack, added later)
# # # #             pair_key = (round(a_cx / 50), round(a_cy / 50), round(b_cx / 50), round(b_cy / 50))
# # # #             now = time.time()
# # # #             last = self._last_alert_time.get(pair_key, 0)
# # # #             if now - last < COOLDOWN_SECONDS:
# # # #                 continue
# # # #             self._last_alert_time[pair_key] = now

# # # #             candidates.append({
# # # #                 "type": "assault_candidate",
# # # #                 "pixel_distance": round(pixel_dist, 1),
# # # #                 "threshold_px": round(threshold_px, 1),
# # # #                 "mount_angle": self.profile.mount_angle.value,
# # # #                 "extra_signal": extra_signal,
# # # #                 "confidence_boost": confidence_boost,
# # # #                 "person_a_bbox": a_box,
# # # #                 "person_b_bbox": b_box,
# # # #                 "timestamp": now,
# # # #             })

# # # #         return candidates


# # # # def main():
# # # #     source = sys.argv[1] if len(sys.argv) > 1 else 0
# # # #     if isinstance(source, str) and source.isdigit():
# # # #         source = int(source)

# # # #     cap = cv2.VideoCapture(source)
# # # #     if not cap.isOpened():
# # # #         raise RuntimeError(f"Could not open video source: {source}")

# # # #     # For now, build a default profile in code instead of loading a saved
# # # #     # one - swap this for CameraProfile.load("your_camera_id") once you've
# # # #     # run the calibration wizard for a real camera.
# # # #     #
# # # #     # Pass tilt degrees as a 2nd argument to test different angle branches:
# # # #     #   python alerts/assault.py 0 10   -> EYE_LEVEL
# # # #     #   python alerts/assault.py 0 25   -> ANGLED_LOW
# # # #     #   python alerts/assault.py 0 50   -> ANGLED_HIGH
# # # #     tilt_deg = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
# # # #     profile = CameraProfile(camera_id="test_camera", tilt_deg=tilt_deg)
# # # #     print(f"Using camera profile: {profile.mount_angle.value} (tilt={tilt_deg}, uncalibrated, using bbox-height fallback)")
# # # #     print(f"Active modules for this angle: {profile.active_modules()}\n")

# # # #     detector = ObjectDetector()
# # # #     alert = AssaultAlert(profile)

# # # #     ok, prev_frame = cap.read()
# # # #     if not ok:
# # # #         raise RuntimeError("Could not read first frame.")
# # # #     prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

# # # #     print("Assault alert checkpoint running. Press 'q' to quit.")
# # # #     print("(Test by having two people/objects get close together in frame)\n")

# # # #     while True:
# # # #         ok, frame = cap.read()
# # # #         if not ok:
# # # #             break

# # # #         curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
# # # #         score = compute_motion_score(prev_gray, curr_gray)
# # # #         prev_gray = curr_gray

# # # #         if is_motion_significant(score):
# # # #             detections = detector.detect(frame)
# # # #             frame = draw_detections(frame, detections)

# # # #             candidates = alert.check(detections)
# # # #             for c in candidates:
# # # #                 # THIS is where the VLM call will go in the next step -
# # # #                 # for now, just prove the candidate is correctly flagged.
# # # #                 print(
# # # #                     f"[CANDIDATE FLAGGED] assault - angle={c['mount_angle']} "
# # # #                     f"pixel_dist={c['pixel_distance']} threshold={c['threshold_px']} "
# # # #                     f"extra_signal={c['extra_signal']} at {time.strftime('%H:%M:%S', time.localtime(c['timestamp']))}"
# # # #                 )
# # # #                 cv2.putText(
# # # #                     frame, "ASSAULT CANDIDATE", (10, 60),
# # # #                     cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
# # # #                 )

# # # #         cv2.imshow("fight - assault alert checkpoint", frame)
# # # #         if cv2.waitKey(1) & 0xFF == ord("q"):
# # # #             break

# # # #     cap.release()
# # # #     cv2.destroyAllWindows()


# # # # if __name__ == "__main__":
# # # #     main()

# # # """
# # # alerts/assault.py

# # # Step 5 checkpoint: candidate flagging + async VLM confirmation.

# # # Pipeline: video_source -> motion gate -> detector -> AssaultAlert -> vlm.py (async) -> console print

# # # Candidates are flagged instantly (as before) and simultaneously sent to
# # # the local Kimi-VL-A3B model via LM Studio for confirmation. The video
# # # loop never waits on the VLM response - results print whenever they
# # # arrive, tagged with which candidate they belong to.

# # # Usage:
# # #     python alerts/assault.py [source] [tilt_deg]
# # #     python alerts/assault.py 0 10   -> EYE_LEVEL
# # #     python alerts/assault.py 0 25   -> ANGLED_LOW
# # #     python alerts/assault.py 0 50   -> ANGLED_HIGH
# # # """

# # # import sys
# # # import os
# # # import time
# # # import itertools
# # # import cv2

# # # # allow importing from core/ when running this file directly
# # # sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

# # # from motion import compute_motion_score, is_motion_significant
# # # from detector import ObjectDetector, draw_detections
# # # from camera_profile import CameraProfile, MountAngle
# # # import vlm

# # # # How close two people need to be (in meters) to count as a candidate.
# # # # 0.6m is "within arm's reach" - tune this after watching real triggers.
# # # PROXIMITY_METERS = 0.6

# # # # Require at least this much cooldown (seconds) before re-flagging the
# # # # same pair of people, so one ongoing event doesn't spam the console.
# # # COOLDOWN_SECONDS = 5.0


# # # class AssaultAlert:
# # #     """
# # #     Rule-based candidate flagger. Checks every pair of detected persons
# # #     in a frame - if two people are closer than the camera-appropriate
# # #     threshold, flags a candidate.

# # #     This does NOT confirm anything is actually a fight - it just says
# # #     "this pair is close enough that a human/VLM should take a look."
# # #     """

# # #     def __init__(self, profile: CameraProfile):
# # #         self.profile = profile
# # #         self._last_alert_time = {}  # (track pair) -> timestamp, for cooldown

# # #     def check(self, detections: list[dict]) -> list[dict]:
# # #         persons = [d for d in detections if d["class"] == "person"]
# # #         candidates = []

# # #         for a, b in itertools.combinations(persons, 2):
# # #             a_box = a["bbox"]
# # #             b_box = b["bbox"]

# # #             a_cx = (a_box[0] + a_box[2]) / 2
# # #             a_cy = (a_box[1] + a_box[3]) / 2
# # #             b_cx = (b_box[0] + b_box[2]) / 2
# # #             b_cy = (b_box[1] + b_box[3]) / 2
# # #             pixel_dist = ((a_cx - b_cx) ** 2 + (a_cy - b_cy) ** 2) ** 0.5

# # #             a_height = a_box[3] - a_box[1]
# # #             threshold_px = self.profile.proximity_threshold_px(
# # #                 real_world_meters=PROXIMITY_METERS, bbox_height_px=a_height
# # #             )

# # #             is_close = pixel_dist < threshold_px
# # #             if not is_close:
# # #                 continue

# # #             extra_signal = None
# # #             confidence_boost = 0.0

# # #             if self.profile.mount_angle in (MountAngle.EYE_LEVEL, MountAngle.ANGLED_LOW):
# # #                 if self.profile.is_module_active("fist_to_head_check"):
# # #                     # PLACEHOLDER - wire in real pose check when core/pose.py is built:
# # #                     # extra_signal = check_fist_to_head(frame, a_box, b_box)
# # #                     extra_signal = "fist_to_head_pending_pose_module"
# # #                     confidence_boost = 0.2

# # #             elif self.profile.mount_angle == MountAngle.ANGLED_HIGH:
# # #                 if self.profile.is_module_active("ground_plane_proximity"):
# # #                     extra_signal = "ground_plane_proximity_used"
# # #                     confidence_boost = 0.1

# # #             pair_key = (round(a_cx / 50), round(a_cy / 50), round(b_cx / 50), round(b_cy / 50))
# # #             now = time.time()
# # #             last = self._last_alert_time.get(pair_key, 0)
# # #             if now - last < COOLDOWN_SECONDS:
# # #                 continue
# # #             self._last_alert_time[pair_key] = now

# # #             candidates.append({
# # #                 "type": "assault_candidate",
# # #                 "pixel_distance": round(pixel_dist, 1),
# # #                 "threshold_px": round(threshold_px, 1),
# # #                 "mount_angle": self.profile.mount_angle.value,
# # #                 "extra_signal": extra_signal,
# # #                 "confidence_boost": confidence_boost,
# # #                 "person_a_bbox": a_box,
# # #                 "person_b_bbox": b_box,
# # #                 "timestamp": now,
# # #             })

# # #         return candidates


# # # def _on_vlm_result(candidate: dict, result: dict):
# # #     """Callback fired from vlm.py's background thread once Kimi-VL responds.
# # #     Runs off the main video-loop thread - keep this fast and side-effect-light
# # #     (just printing for now; this is where alert dispatch would eventually go)."""
# # #     flagged_at = time.strftime("%H:%M:%S", time.localtime(candidate["timestamp"]))
# # #     verdict = result.get("verdict", "UNKNOWN")

# # #     if verdict == "ERROR":
# # #         print(
# # #             f"[VLM ERROR] candidate flagged at {flagged_at} "
# # #             f"(angle={candidate['mount_angle']}) -> {result.get('error')}"
# # #         )
# # #         return

# # #     print(
# # #         f"[VLM RESULT] candidate flagged at {flagged_at} "
# # #         f"(angle={candidate['mount_angle']}, extra_signal={candidate['extra_signal']}) "
# # #         f"-> {verdict} ({result.get('latency_s')}s) :: {result.get('raw_text')}"
# # #     )


# # # def main():
# # #     source = sys.argv[1] if len(sys.argv) > 1 else 0
# # #     if isinstance(source, str) and source.isdigit():
# # #         source = int(source)

# # #     cap = cv2.VideoCapture(source)
# # #     if not cap.isOpened():
# # #         raise RuntimeError(f"Could not open video source: {source}")

# # #     tilt_deg = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
# # #     profile = CameraProfile(camera_id="test_camera", tilt_deg=tilt_deg)
# # #     print(f"Using camera profile: {profile.mount_angle.value} (tilt={tilt_deg}, uncalibrated, using bbox-height fallback)")
# # #     print(f"Active modules for this angle: {profile.active_modules()}\n")
# # #     # print(f"VLM confirmation target: {vlm.LM_STUDIO_BASE_URL} model={vlm.LM_STUDIO_MODEL}\n")
# # #     print(f"VLM confirmation: offline in-process (Kimi-VL-A3B, {vlm.N_GPU_LAYERS} GPU layers)\n")
# # #     detector = ObjectDetector()
# # #     alert = AssaultAlert(profile)

# # #     ok, prev_frame = cap.read()
# # #     if not ok:
# # #         raise RuntimeError("Could not read first frame.")
# # #     prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

# # #     print("Assault alert checkpoint running. Press 'q' to quit.")
# # #     print("(Test by having two people/objects get close together in frame)\n")

# # #     while True:
# # #         ok, frame = cap.read()
# # #         if not ok:
# # #             break

# # #         curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
# # #         score = compute_motion_score(prev_gray, curr_gray)
# # #         prev_gray = curr_gray

# # #         if is_motion_significant(score):
# # #             # Take a clean copy BEFORE any boxes/text get drawn on `frame` -
# # #             # this is what gets cropped and sent to the VLM, so it should
# # #             # not contain our own overlay artwork.
# # #             clean_frame = frame.copy()

# # #             detections = detector.detect(frame)
# # #             frame = draw_detections(frame, detections)

# # #             candidates = alert.check(detections)
# # #             for c in candidates:
# # #                 print(
# # #                     f"[CANDIDATE FLAGGED] assault - angle={c['mount_angle']} "
# # #                     f"pixel_dist={c['pixel_distance']} threshold={c['threshold_px']} "
# # #                     f"extra_signal={c['extra_signal']} at {time.strftime('%H:%M:%S', time.localtime(c['timestamp']))}"
# # #                 )
# # #                 cv2.putText(
# # #                     frame, "ASSAULT CANDIDATE", (10, 60),
# # #                     cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
# # #                 )
# # #                 # Fire off VLM confirmation in the background - non-blocking.
# # #                 vlm.confirm_candidate_async(clean_frame, c, _on_vlm_result)

# # #         cv2.imshow("fight - assault alert checkpoint", frame)
# # #         if cv2.waitKey(1) & 0xFF == ord("q"):
# # #             break

# # #     cap.release()
# # #     cv2.destroyAllWindows()


# # # if __name__ == "__main__":
# # #     main()

# # """
# # alerts/assault.py

# # Full pipeline checkpoint: video_source -> motion gate -> detector ->
# # rule engine (this file) -> async VLM confirmation via local Kimi-VL.

# # This is now the COMPLETE cascade for the assault/fight alert type:
# # cheap rule-based candidate flagging, confirmed by your local VLM
# # running in a background thread so the video feed keeps playing at
# # full speed while the VLM (slowly, on CPU) thinks about each candidate.

# # Prerequisite: LM Studio running locally with Kimi-VL-A3B-Thinking-2506
# # loaded, and its Local Server started (see core/vlm.py for details).

# # Usage:
# #     python alerts/assault.py                # webcam, default tilt=20 (ANGLED_LOW)
# #     python alerts/assault.py 0 10            # webcam, tilt=10 (EYE_LEVEL)
# #     python alerts/assault.py 0 50            # webcam, tilt=50 (ANGLED_HIGH)
# #     python alerts/assault.py path/to/video.mp4 25
# # """

# # import sys
# # import os
# # import time
# # import itertools
# # import cv2

# # # allow importing from core/ when running this file directly
# # sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

# # from motion import compute_motion_score, is_motion_significant
# # from detector import ObjectDetector, draw_detections
# # from camera_profile import CameraProfile, MountAngle
# # from vlm import confirm_candidate_async, is_confirmed

# # # How close two people need to be (in meters) to count as a candidate.
# # # 0.6m is "within arm's reach" - tune this after watching real triggers.
# # PROXIMITY_METERS = 0.6

# # # Require at least this much cooldown (seconds) before re-flagging the
# # # same pair of people, so one ongoing event doesn't spam the console.
# # COOLDOWN_SECONDS = 5.0

# # # High-resolution video files (1080p/4K) are much slower to process on
# # # CPU than they need to be for detection purposes. Downscale so the
# # # longer edge is at most this many pixels before running motion/YOLO -
# # # this is the fix for "video appears stuck / frozen on one frame".
# # MAX_PROCESSING_WIDTH = 960


# # def resize_for_processing(frame, max_width: int = MAX_PROCESSING_WIDTH):
# #     """
# #     Shrinks a frame down to a manageable size for CPU processing.
# #     Returns the resized frame. Detection/motion all run on this smaller
# #     version - much faster, and accuracy loss is minimal since YOLO/pose
# #     models don't need full resolution to find people at typical camera
# #     distances.
# #     """
# #     h, w = frame.shape[:2]
# #     if w <= max_width:
# #         return frame
# #     scale = max_width / w
# #     new_size = (max_width, int(h * scale))
# #     return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


# # class AssaultAlert:
# #     """
# #     Rule-based candidate flagger. Checks every pair of detected persons
# #     in a frame - if two people are closer than the camera-appropriate
# #     threshold, flags a candidate.

# #     This does NOT confirm anything is actually a fight - it just says
# #     "this pair is close enough that a human/VLM should take a look."
# #     That confirmation step comes next.
# #     """

# #     def __init__(self, profile: CameraProfile):
# #         self.profile = profile
# #         self._last_alert_time = {}  # (track pair) -> timestamp, for cooldown

# #     def check(self, detections: list[dict]) -> list[dict]:
# #         """
# #         detections: output of ObjectDetector.detect() for one frame.
# #         Returns a list of candidate dicts, one per flagged pair.

# #         THIS is the integration point for your 3 shortlisted camera
# #         angles. The proximity check below runs for ALL angles (it's the
# #         one signal that's valid everywhere), but angle-specific extra
# #         checks get added/removed here based on the profile.
# #         """
# #         persons = [d for d in detections if d["class"] == "person"]
# #         candidates = []

# #         for a, b in itertools.combinations(persons, 2):
# #             a_box = a["bbox"]
# #             b_box = b["bbox"]

# #             a_cx = (a_box[0] + a_box[2]) / 2
# #             a_cy = (a_box[1] + a_box[3]) / 2
# #             b_cx = (b_box[0] + b_box[2]) / 2
# #             b_cy = (b_box[1] + b_box[3]) / 2
# #             pixel_dist = ((a_cx - b_cx) ** 2 + (a_cy - b_cy) ** 2) ** 0.5

# #             a_height = a_box[3] - a_box[1]
# #             threshold_px = self.profile.proximity_threshold_px(
# #                 real_world_meters=PROXIMITY_METERS, bbox_height_px=a_height
# #             )

# #             # base signal: are they close? (valid for every angle)
# #             is_close = pixel_dist < threshold_px
# #             if not is_close:
# #                 continue

# #             # --- ANGLE-SPECIFIC LOGIC BRANCHES HERE ---
# #             # This is the exact integration point for your 3 shortlisted
# #             # angles (EYE_LEVEL, ANGLED_LOW, ANGLED_HIGH). Each branch can
# #             # add extra confirming signals or adjust confidence, using
# #             # whatever that angle can reliably see.
# #             extra_signal = None
# #             confidence_boost = 0.0

# #             if self.profile.mount_angle in (MountAngle.EYE_LEVEL, MountAngle.ANGLED_LOW):
# #                 # Full pose visibility at this angle - once core/pose.py
# #                 # exists, call it here for fist-to-head distance.
# #                 if self.profile.is_module_active("fist_to_head_check"):
# #                     # PLACEHOLDER - wire in real pose check when core/pose.py is built:
# #                     # extra_signal = check_fist_to_head(frame, a_box, b_box)
# #                     extra_signal = "fist_to_head_pending_pose_module"
# #                     confidence_boost = 0.2

# #             elif self.profile.mount_angle == MountAngle.ANGLED_HIGH:
# #                 # Foreshortening makes fist-to-head unreliable at this angle
# #                 # (see MODULE_MATRIX - fist_to_head_check is False here).
# #                 # Rely on proximity + motion intensity instead.
# #                 if self.profile.is_module_active("ground_plane_proximity"):
# #                     extra_signal = "ground_plane_proximity_used"
# #                     confidence_boost = 0.1

# #             # simple cooldown key based on rounded position, since we don't
# #             # have persistent track IDs yet (that's ByteTrack, added later)
# #             pair_key = (round(a_cx / 50), round(a_cy / 50), round(b_cx / 50), round(b_cy / 50))
# #             now = time.time()
# #             last = self._last_alert_time.get(pair_key, 0)
# #             if now - last < COOLDOWN_SECONDS:
# #                 continue
# #             self._last_alert_time[pair_key] = now

# #             candidates.append({
# #                 "type": "assault_candidate",
# #                 "pixel_distance": round(pixel_dist, 1),
# #                 "threshold_px": round(threshold_px, 1),
# #                 "mount_angle": self.profile.mount_angle.value,
# #                 "extra_signal": extra_signal,
# #                 "confidence_boost": confidence_boost,
# #                 "person_a_bbox": a_box,
# #                 "person_b_bbox": b_box,
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

# #     # For now, build a default profile in code instead of loading a saved
# #     # one - swap this for CameraProfile.load("your_camera_id") once you've
# #     # run the calibration wizard for a real camera.
# #     #
# #     # Pass tilt degrees as a 2nd argument to test different angle branches:
# #     #   python alerts/assault.py 0 10   -> EYE_LEVEL
# #     #   python alerts/assault.py 0 25   -> ANGLED_LOW
# #     #   python alerts/assault.py 0 50   -> ANGLED_HIGH
# #     tilt_deg = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
# #     profile = CameraProfile(camera_id="test_camera", tilt_deg=tilt_deg)
# #     print(f"Using camera profile: {profile.mount_angle.value} (tilt={tilt_deg}, uncalibrated, using bbox-height fallback)")
# #     print(f"Active modules for this angle: {profile.active_modules()}\n")

# #     detector = ObjectDetector()
# #     alert = AssaultAlert(profile)

# #     ok, prev_frame = cap.read()
# #     if not ok:
# #         raise RuntimeError("Could not read first frame.")
# #     prev_frame = resize_for_processing(prev_frame)
# #     prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

# #     print("Assault alert checkpoint running. Press 'q' to quit.")
# #     print("(Test by having two people/objects get close together in frame)")
# #     print("(VLM runs offline in-process via llama-cpp-python — no server needed)\n")

# #     # Tracks in-flight VLM confirmations so we don't block the video loop
# #     # waiting for a response. Each entry: {"future": Future, "candidate": dict}
# #     pending_confirmations = []

# #     while True:
# #         ok, frame = cap.read()
# #         if not ok:
# #             break

# #         # Downscale BEFORE any processing - this is the fix for high-res
# #         # video files appearing to freeze/get stuck. All motion/detection
# #         # runs on the smaller frame from here on.
# #         frame = resize_for_processing(frame)

# #         curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
# #         score = compute_motion_score(prev_gray, curr_gray)
# #         prev_gray = curr_gray

# #         if is_motion_significant(score):
# #             detections = detector.detect(frame)
# #             frame = draw_detections(frame, detections)

# #             candidates = alert.check(detections)
# #             for c in candidates:
# #                 print(
# #                     f"[CANDIDATE FLAGGED] assault - angle={c['mount_angle']} "
# #                     f"pixel_dist={c['pixel_distance']} threshold={c['threshold_px']} "
# #                     f"extra_signal={c['extra_signal']} at {time.strftime('%H:%M:%S', time.localtime(c['timestamp']))}"
# #                 )
# #                 print("  -> dispatched to local VLM in background (video keeps running)...")

# #                 # Non-blocking: this returns immediately with a Future.
# #                 # The actual HTTP call + CPU inference happens on a
# #                 # background thread (see vlm.py's ThreadPoolExecutor).
# #                 future = confirm_candidate_async(
# #                     frame, [c["person_a_bbox"], c["person_b_bbox"]], "assault_candidate"
# #                 )
# #                 pending_confirmations.append({"future": future, "candidate": c})

# #         # Check any pending VLM confirmations for completion - non-blocking,
# #         # just polls whether each background thread has finished yet.
# #         still_pending = []
# #         for item in pending_confirmations:
# #             future = item["future"]
# #             c = item["candidate"]
# #             if future.done():
# #                 result = future.result()
# #                 if result.get("error"):
# #                     print(f"  -> VLM ERROR for candidate at {time.strftime('%H:%M:%S')}: {result['error']}")
# #                 elif is_confirmed(result):
# #                     print(
# #                         f"  -> CONFIRMED (confidence={result['confidence']:.2f}, "
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

# #         # visual indicator: show how many VLM confirmations are still processing
# #         if pending_confirmations:
# #             cv2.putText(
# #                 frame, f"VLM confirming... ({len(pending_confirmations)} pending)",
# #                 (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2,
# #             )

# #         cv2.imshow("fight - assault alert checkpoint", frame)
# #         if cv2.waitKey(1) & 0xFF == ord("q"):
# #             break

# #     cap.release()
# #     cv2.destroyAllWindows()


# # if __name__ == "__main__":
# #     main()

# """
# alerts/assault.py

# Full pipeline checkpoint: video_source -> motion gate -> detector ->
# rule engine (this file) -> async VLM confirmation via local Kimi-VL.

# This is now the COMPLETE cascade for the assault/fight alert type:
# cheap rule-based candidate flagging, confirmed by your local VLM
# running in a background thread so the video feed keeps playing at
# full speed while the VLM (slowly, on CPU) thinks about each candidate.

# Prerequisite: LM Studio running locally with Kimi-VL-A3B-Thinking-2506
# loaded, and its Local Server started (see core/vlm.py for details).

# Usage:
#     python alerts/assault.py                # webcam, default tilt=20 (ANGLED_LOW)
#     python alerts/assault.py 0 10            # webcam, tilt=10 (EYE_LEVEL)
#     python alerts/assault.py 0 50            # webcam, tilt=50 (ANGLED_HIGH)
#     python alerts/assault.py path/to/video.mp4 25
# """

# import sys
# import os
# import time
# import itertools
# import cv2

# # allow importing from core/ when running this file directly
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

# from motion import compute_motion_score, is_motion_significant
# from detector import ObjectDetector, draw_detections
# from camera_profile import CameraProfile, MountAngle
# from vlm import confirm_candidate_async, is_confirmed

# # How close two people need to be (in meters) to count as a candidate.
# # 0.6m is "within arm's reach" - tune this after watching real triggers.
# PROXIMITY_METERS = 0.6

# # Require at least this much cooldown (seconds) before re-flagging the
# # same pair of people, so one ongoing event doesn't spam the console.
# COOLDOWN_SECONDS = 5.0

# # High-resolution video files (1080p/4K) are much slower to process on
# # CPU than they need to be for detection purposes. Downscale so the
# # longer edge is at most this many pixels before running motion/YOLO -
# # this is the fix for "video appears stuck / frozen on one frame".
# MAX_PROCESSING_WIDTH = 960


# def resize_for_processing(frame, max_width: int = MAX_PROCESSING_WIDTH):
#     """
#     Shrinks a frame down to a manageable size for CPU processing.
#     Returns the resized frame. Detection/motion all run on this smaller
#     version - much faster, and accuracy loss is minimal since YOLO/pose
#     models don't need full resolution to find people at typical camera
#     distances.
#     """
#     h, w = frame.shape[:2]
#     if w <= max_width:
#         return frame
#     scale = max_width / w
#     new_size = (max_width, int(h * scale))
#     return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


# class AssaultAlert:
#     """
#     Rule-based candidate flagger. Checks every pair of detected persons
#     in a frame - if two people are closer than the camera-appropriate
#     threshold, flags a candidate.

#     This does NOT confirm anything is actually a fight - it just says
#     "this pair is close enough that a human/VLM should take a look."
#     That confirmation step comes next.
#     """

#     def __init__(self, profile: CameraProfile):
#         self.profile = profile
#         self._last_alert_time = {}  # (track pair) -> timestamp, for cooldown

#     def check(self, detections: list[dict]) -> list[dict]:
#         """
#         detections: output of ObjectDetector.detect() for one frame.
#         Returns a list of candidate dicts, one per flagged pair.

#         THIS is the integration point for your 3 shortlisted camera
#         angles. The proximity check below runs for ALL angles (it's the
#         one signal that's valid everywhere), but angle-specific extra
#         checks get added/removed here based on the profile.
#         """
#         persons = [d for d in detections if d["class"] == "person"]
#         candidates = []

#         for a, b in itertools.combinations(persons, 2):
#             a_box = a["bbox"]
#             b_box = b["bbox"]

#             a_cx = (a_box[0] + a_box[2]) / 2
#             a_cy = (a_box[1] + a_box[3]) / 2
#             b_cx = (b_box[0] + b_box[2]) / 2
#             b_cy = (b_box[1] + b_box[3]) / 2
#             pixel_dist = ((a_cx - b_cx) ** 2 + (a_cy - b_cy) ** 2) ** 0.5

#             a_height = a_box[3] - a_box[1]
#             threshold_px = self.profile.proximity_threshold_px(
#                 real_world_meters=PROXIMITY_METERS, bbox_height_px=a_height
#             )

#             # base signal: are they close? (valid for every angle)
#             is_close = pixel_dist < threshold_px
#             if not is_close:
#                 continue

#             # --- ANGLE-SPECIFIC LOGIC BRANCHES HERE ---
#             # This is the exact integration point for your 3 shortlisted
#             # angles (EYE_LEVEL, ANGLED_LOW, ANGLED_HIGH). Each branch tags
#             # the candidate with which extra signal WOULD apply at this
#             # angle - honest note: fist_to_head is still a placeholder
#             # until core/pose.py exists (real pose estimation), and
#             # ground_plane_proximity doesn't yet use real calibration
#             # (no calibration wizard built yet) - both currently fall back
#             # to the same bbox-height proximity math. This tagging is kept
#             # so downstream code (and you, reading the logs) can see which
#             # branch WOULD be active once those pieces are built, without
#             # pretending there's a numeric accuracy difference that isn't
#             # real yet.
#             extra_signal = None

#             if self.profile.mount_angle in (MountAngle.EYE_LEVEL, MountAngle.ANGLED_LOW):
#                 if self.profile.is_module_active("fist_to_head_check"):
#                     # PLACEHOLDER - wire in real pose check when core/pose.py is built:
#                     # extra_signal = check_fist_to_head(frame, a_box, b_box)
#                     extra_signal = "fist_to_head_pending_pose_module"

#             elif self.profile.mount_angle == MountAngle.ANGLED_HIGH:
#                 if self.profile.is_module_active("ground_plane_proximity"):
#                     # PLACEHOLDER - real ground-plane math needs a per-camera
#                     # calibration (pixels-per-meter) that hasn't been built
#                     # yet - currently uses the same bbox-height fallback as
#                     # every other angle.
#                     extra_signal = "ground_plane_proximity_pending_calibration"

#             # simple cooldown key based on rounded position, since we don't
#             # have persistent track IDs yet (that's ByteTrack, added later)
#             pair_key = (round(a_cx / 50), round(a_cy / 50), round(b_cx / 50), round(b_cy / 50))
#             now = time.time()
#             last = self._last_alert_time.get(pair_key, 0)
#             if now - last < COOLDOWN_SECONDS:
#                 continue
#             self._last_alert_time[pair_key] = now

#             candidates.append({
#                 "type": "assault_candidate",
#                 "pixel_distance": round(pixel_dist, 1),
#                 "threshold_px": round(threshold_px, 1),
#                 "mount_angle": self.profile.mount_angle.value,
#                 "extra_signal": extra_signal,
#                 "person_a_bbox": a_box,
#                 "person_b_bbox": b_box,
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

#     # For now, build a default profile in code instead of loading a saved
#     # one - swap this for CameraProfile.load("your_camera_id") once you've
#     # run the calibration wizard for a real camera.
#     #
#     # Pass tilt degrees as a 2nd argument to test different angle branches:
#     #   python alerts/assault.py 0 10   -> EYE_LEVEL
#     #   python alerts/assault.py 0 25   -> ANGLED_LOW
#     #   python alerts/assault.py 0 50   -> ANGLED_HIGH
#     tilt_deg = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
#     profile = CameraProfile(camera_id="test_camera", tilt_deg=tilt_deg)
#     print(f"Using camera profile: {profile.mount_angle.value} (tilt={tilt_deg}, uncalibrated, using bbox-height fallback)")
#     print(f"Active modules for this angle: {profile.active_modules()}\n")

#     detector = ObjectDetector()
#     alert = AssaultAlert(profile)

#     ok, prev_frame = cap.read()
#     if not ok:
#         raise RuntimeError("Could not read first frame.")
#     prev_frame = resize_for_processing(prev_frame)
#     prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

#     print("Assault alert checkpoint running. Press 'q' to quit.")
#     print("(Test by having two people/objects get close together in frame)")
#     print("(Make sure LM Studio's local server is running with Kimi-VL loaded)\n")

#     # Tracks in-flight VLM confirmations so we don't block the video loop
#     # waiting for a response. Each entry: {"future": Future, "candidate": dict}
#     pending_confirmations = []

#     while True:
#         ok, frame = cap.read()
#         if not ok:
#             break

#         # Downscale BEFORE any processing - this is the fix for high-res
#         # video files appearing to freeze/get stuck. All motion/detection
#         # runs on the smaller frame from here on.
#         frame = resize_for_processing(frame)

#         curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         score = compute_motion_score(prev_gray, curr_gray)
#         prev_gray = curr_gray

#         if is_motion_significant(score):
#             detections = detector.detect(frame)
#             frame = draw_detections(frame, detections)

#             candidates = alert.check(detections)
#             for c in candidates:
#                 print(
#                     f"[CANDIDATE FLAGGED] assault - angle={c['mount_angle']} "
#                     f"pixel_dist={c['pixel_distance']} threshold={c['threshold_px']} "
#                     f"extra_signal={c['extra_signal']} at {time.strftime('%H:%M:%S', time.localtime(c['timestamp']))}"
#                 )
#                 print("  -> dispatched to local VLM in background (video keeps running)...")

#                 # Non-blocking: this returns immediately with a Future.
#                 # The actual HTTP call + CPU inference happens on a
#                 # background thread (see vlm.py's ThreadPoolExecutor).
#                 # mount_angle is now passed through so the VLM prompt
#                 # actually reflects the camera's real viewing angle.
#                 future = confirm_candidate_async(
#                     frame,
#                     [c["person_a_bbox"], c["person_b_bbox"]],
#                     "assault_candidate",
#                     mount_angle=c["mount_angle"],
#                 )
#                 pending_confirmations.append({"future": future, "candidate": c})

#         # Check any pending VLM confirmations for completion - non-blocking,
#         # just polls whether each background thread has finished yet.
#         still_pending = []
#         for item in pending_confirmations:
#             future = item["future"]
#             c = item["candidate"]
#             if future.done():
#                 result = future.result()
#                 if result.get("error"):
#                     print(f"  -> VLM ERROR for candidate at {time.strftime('%H:%M:%S')}: {result['error']}")
#                 elif is_confirmed(result):
#                     print(
#                         f"  -> CONFIRMED (confidence={result['confidence']:.2f}, "
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

#         # visual indicator: show how many VLM confirmations are still processing
#         if pending_confirmations:
#             cv2.putText(
#                 frame, f"VLM confirming... ({len(pending_confirmations)} pending)",
#                 (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2,
#             )

#         cv2.imshow("fight - assault alert checkpoint", frame)
#         if cv2.waitKey(1) & 0xFF == ord("q"):
#             break

#     cap.release()
#     cv2.destroyAllWindows()


# if __name__ == "__main__":
#     main()

"""
alerts/assault.py

Full pipeline checkpoint: video_source -> motion gate -> detector ->
rule engine (this file) -> async VLM confirmation via local Kimi-VL.

This is now the COMPLETE cascade for the assault/fight alert type:
cheap rule-based candidate flagging, confirmed by your local VLM
running in a background thread so the video feed keeps playing at
full speed while the VLM (slowly, on CPU) thinks about each candidate.

Prerequisite: LM Studio running locally with Kimi-VL-A3B-Thinking-2506
loaded, and its Local Server started (see core/vlm.py for details).

Usage:
    python alerts/assault.py                # webcam, default tilt=20 (ANGLED_LOW)
    python alerts/assault.py 0 10            # webcam, tilt=10 (EYE_LEVEL)
    python alerts/assault.py 0 50            # webcam, tilt=50 (ANGLED_HIGH)
    python alerts/assault.py path/to/video.mp4 25
"""

import sys
import os
import time
import itertools
import cv2

# allow importing from core/ when running this file directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from motion import compute_motion_score, is_motion_significant
from detector import ObjectDetector, draw_detections
from camera_profile import CameraProfile, MountAngle
from vlm import confirm_candidate_async, is_confirmed

# How close two people need to be (in meters) to count as a candidate.
# 0.6m is "within arm's reach" - tune this after watching real triggers.
PROXIMITY_METERS = 0.6

# Require at least this much cooldown (seconds) before re-flagging the
# same pair of people, so one ongoing event doesn't spam the console.
COOLDOWN_SECONDS = 5.0

# High-resolution video files (1080p/4K) are much slower to process on
# CPU than they need to be for detection purposes. Downscale so the
# longer edge is at most this many pixels before running motion/YOLO -
# this is the fix for "video appears stuck / frozen on one frame".
MAX_PROCESSING_WIDTH = 960


def resize_for_processing(frame, max_width: int = MAX_PROCESSING_WIDTH):
    """
    Shrinks a frame down to a manageable size for CPU processing.
    Returns the resized frame. Detection/motion all run on this smaller
    version - much faster, and accuracy loss is minimal since YOLO/pose
    models don't need full resolution to find people at typical camera
    distances.

    Checks BOTH width and height (not just width) - this matters for
    portrait-orientation videos (e.g. phone recordings) where width may
    already be under max_width but height is very large. Without this,
    tall videos display cut off / "zoomed" since the display window
    can end up taller than your screen.
    """
    h, w = frame.shape[:2]
    if w <= max_width and h <= max_width:
        return frame
    # scale based on whichever dimension is larger, so both width and
    # height end up within bounds while preserving aspect ratio
    scale = max_width / max(w, h)
    new_size = (int(w * scale), int(h * scale))
    return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


class AssaultAlert:
    """
    Rule-based candidate flagger. Checks every pair of detected persons
    in a frame - if two people are closer than the camera-appropriate
    threshold, flags a candidate.

    This does NOT confirm anything is actually a fight - it just says
    "this pair is close enough that a human/VLM should take a look."
    That confirmation step comes next.
    """

    def __init__(self, profile: CameraProfile):
        self.profile = profile
        self._last_alert_time = {}  # (track pair) -> timestamp, for cooldown

    def check(self, detections: list[dict]) -> list[dict]:
        """
        detections: output of ObjectDetector.detect() for one frame.
        Returns a list of candidate dicts, one per flagged pair.

        THIS is the integration point for your 3 shortlisted camera
        angles. The proximity check below runs for ALL angles (it's the
        one signal that's valid everywhere), but angle-specific extra
        checks get added/removed here based on the profile.
        """
        persons = [d for d in detections if d["class"] == "person"]
        candidates = []

        for a, b in itertools.combinations(persons, 2):
            a_box = a["bbox"]
            b_box = b["bbox"]

            a_cx = (a_box[0] + a_box[2]) / 2
            a_cy = (a_box[1] + a_box[3]) / 2
            b_cx = (b_box[0] + b_box[2]) / 2
            b_cy = (b_box[1] + b_box[3]) / 2
            pixel_dist = ((a_cx - b_cx) ** 2 + (a_cy - b_cy) ** 2) ** 0.5

            a_height = a_box[3] - a_box[1]
            threshold_px = self.profile.proximity_threshold_px(
                real_world_meters=PROXIMITY_METERS, bbox_height_px=a_height
            )

            # base signal: are they close? (valid for every angle)
            is_close = pixel_dist < threshold_px
            if not is_close:
                continue

            # --- ANGLE-SPECIFIC LOGIC BRANCHES HERE ---
            # This is the exact integration point for your 3 shortlisted
            # angles (EYE_LEVEL, ANGLED_LOW, ANGLED_HIGH). Each branch tags
            # the candidate with which extra signal WOULD apply at this
            # angle - honest note: fist_to_head is still a placeholder
            # until core/pose.py exists (real pose estimation), and
            # ground_plane_proximity doesn't yet use real calibration
            # (no calibration wizard built yet) - both currently fall back
            # to the same bbox-height proximity math. This tagging is kept
            # so downstream code (and you, reading the logs) can see which
            # branch WOULD be active once those pieces are built, without
            # pretending there's a numeric accuracy difference that isn't
            # real yet.
            extra_signal = None

            if self.profile.mount_angle in (MountAngle.EYE_LEVEL, MountAngle.ANGLED_LOW):
                if self.profile.is_module_active("fist_to_head_check"):
                    # PLACEHOLDER - wire in real pose check when core/pose.py is built:
                    # extra_signal = check_fist_to_head(frame, a_box, b_box)
                    extra_signal = "fist_to_head_pending_pose_module"

            elif self.profile.mount_angle == MountAngle.ANGLED_HIGH:
                if self.profile.is_module_active("ground_plane_proximity"):
                    # PLACEHOLDER - real ground-plane math needs a per-camera
                    # calibration (pixels-per-meter) that hasn't been built
                    # yet - currently uses the same bbox-height fallback as
                    # every other angle.
                    extra_signal = "ground_plane_proximity_pending_calibration"

            # simple cooldown key based on rounded position, since we don't
            # have persistent track IDs yet (that's ByteTrack, added later)
            pair_key = (round(a_cx / 50), round(a_cy / 50), round(b_cx / 50), round(b_cy / 50))
            now = time.time()
            last = self._last_alert_time.get(pair_key, 0)
            if now - last < COOLDOWN_SECONDS:
                continue
            self._last_alert_time[pair_key] = now

            candidates.append({
                "type": "assault_candidate",
                "pixel_distance": round(pixel_dist, 1),
                "threshold_px": round(threshold_px, 1),
                "mount_angle": self.profile.mount_angle.value,
                "extra_signal": extra_signal,
                "person_a_bbox": a_box,
                "person_b_bbox": b_box,
                "timestamp": now,
            })

        return candidates


def main():
    WINDOW_NAME = "fight - assault alert checkpoint"
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    # Explicitly resizable window - without this, OpenCV can size the
    # window to the raw frame dimensions, which cuts off tall/portrait
    # videos if they're taller than your screen. WINDOW_NORMAL lets you
    # freely resize/drag the window edges to see the whole frame.
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 960, 720)  # sensible default, drag to resize as needed

    # For now, build a default profile in code instead of loading a saved
    # one - swap this for CameraProfile.load("your_camera_id") once you've
    # run the calibration wizard for a real camera.
    #
    # Pass tilt degrees as a 2nd argument to test different angle branches:
    #   python alerts/assault.py 0 10   -> EYE_LEVEL
    #   python alerts/assault.py 0 25   -> ANGLED_LOW
    #   python alerts/assault.py 0 50   -> ANGLED_HIGH
    tilt_deg = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    profile = CameraProfile(camera_id="test_camera", tilt_deg=tilt_deg)
    print(f"Using camera profile: {profile.mount_angle.value} (tilt={tilt_deg}, uncalibrated, using bbox-height fallback)")
    print(f"Active modules for this angle: {profile.active_modules()}\n")

    detector = ObjectDetector()
    alert = AssaultAlert(profile)

    ok, prev_frame = cap.read()
    if not ok:
        raise RuntimeError("Could not read first frame.")
    prev_frame = resize_for_processing(prev_frame)
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

    print("Assault alert checkpoint running. Press 'q' to quit.")
    print("(Test by having two people/objects get close together in frame)")
    print("(Make sure LM Studio's local server is running with Kimi-VL loaded)\n")

    # Tracks in-flight VLM confirmations so we don't block the video loop
    # waiting for a response. Each entry: {"future": Future, "candidate": dict}
    pending_confirmations = []

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # Downscale BEFORE any processing - this is the fix for high-res
        # video files appearing to freeze/get stuck. All motion/detection
        # runs on the smaller frame from here on.
        frame = resize_for_processing(frame)

        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        score = compute_motion_score(prev_gray, curr_gray)
        prev_gray = curr_gray

        if is_motion_significant(score):
            detections = detector.detect(frame)
            frame = draw_detections(frame, detections)

            candidates = alert.check(detections)
            for c in candidates:
                print(
                    f"[CANDIDATE FLAGGED] assault - angle={c['mount_angle']} "
                    f"pixel_dist={c['pixel_distance']} threshold={c['threshold_px']} "
                    f"extra_signal={c['extra_signal']} at {time.strftime('%H:%M:%S', time.localtime(c['timestamp']))}"
                )
                print("  -> dispatched to local VLM in background (video keeps running)...")

                # Non-blocking: this returns immediately with a Future.
                # The actual HTTP call + CPU inference happens on a
                # background thread (see vlm.py's ThreadPoolExecutor).
                # mount_angle is now passed through so the VLM prompt
                # actually reflects the camera's real viewing angle.
                future = confirm_candidate_async(
                    frame,
                    [c["person_a_bbox"], c["person_b_bbox"]],
                    "assault_candidate",
                    mount_angle=c["mount_angle"],
                )
                pending_confirmations.append({"future": future, "candidate": c})

        # Check any pending VLM confirmations for completion - non-blocking,
        # just polls whether each background thread has finished yet.
        still_pending = []
        for item in pending_confirmations:
            future = item["future"]
            c = item["candidate"]
            if future.done():
                result = future.result()
                if result.get("error"):
                    print(f"  -> VLM ERROR for candidate at {time.strftime('%H:%M:%S')}: {result['error']}")
                elif is_confirmed(result):
                    print(
                        f"  -> CONFIRMED (confidence={result['confidence']:.2f}, "
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

        # visual indicator: show how many VLM confirmations are still processing
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