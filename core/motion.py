"""
motion.py

Step 2 checkpoint: the motion gate. Computes optical flow between
consecutive frames and decides whether there's enough motion to justify
running the expensive stages (detection, pose, VLM) on this frame.

Run directly to test against your webcam - it will print motion scores
live and tell you when the gate is OPEN (process this frame) vs
CLOSED (skip it) so you can see it responding to movement in real time.

Usage:
    python core/motion.py
"""

import sys
import cv2
import numpy as np

# Tune this after watching the printed scores for a few minutes.
# Start conservative (skip fewer frames) and tighten later once you've
# seen what "empty room" vs "someone walking" scores look like on your
# actual camera.
MOTION_THRESHOLD = 0.5


def compute_motion_score(prev_gray: np.ndarray, curr_gray: np.ndarray) -> float:
    """
    Returns a single float representing how much motion occurred between
    two grayscale frames. Higher = more motion.

    Uses Farneback dense optical flow (CPU-friendly, built into OpenCV -
    no GPU or extra model download needed, unlike RAFT).
    """
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, curr_gray,
        None,
        pyr_scale=0.5,
        levels=2,          # fewer pyramid levels = faster, less precise
        winsize=15,
        iterations=2,
        poly_n=5,
        poly_sigma=1.1,
        flags=0,
    )
    # magnitude of motion vectors at every pixel, then average across the frame
    magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    return float(np.mean(magnitude))


def is_motion_significant(score: float, threshold: float = MOTION_THRESHOLD) -> bool:
    return score >= threshold


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    ok, prev_frame = cap.read()
    if not ok:
        raise RuntimeError("Could not read first frame.")
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

    print("Motion gate running. Press 'q' to quit.")
    print(f"Threshold = {MOTION_THRESHOLD} (edit MOTION_THRESHOLD in this file to tune)\n")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        score = compute_motion_score(prev_gray, curr_gray)
        gate_open = is_motion_significant(score)

        status = "OPEN  (would process this frame)" if gate_open else "CLOSED (skipped - saves CPU)"
        print(f"motion score: {score:.4f}  ->  gate: {status}")

        # visual feedback: green border when gate is open, red when closed
        color = (0, 200, 0) if gate_open else (0, 0, 200)
        cv2.rectangle(frame, (0, 0), (frame.shape[1] - 1, frame.shape[0] - 1), color, 6)
        cv2.putText(
            frame, f"motion: {score:.3f}  gate: {'OPEN' if gate_open else 'CLOSED'}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2,
        )
        cv2.imshow("fight - motion gate checkpoint", frame)

        prev_gray = curr_gray

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()