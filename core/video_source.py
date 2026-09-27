"""
video_source.py

Step 1 checkpoint: confirm you can read frames from a camera or video
file at all, before adding any detection/motion logic on top.

Usage:
    python core/video_source.py                # opens default webcam (index 0)
    python core/video_source.py path/to/video.mp4   # opens a video file
"""

import sys
import cv2

TARGET_FPS = 15  # throttle to this, since we don't need more for detection


def open_source(source):
    """
    source: 0 (or any int) for a webcam index, or a file path string.
    """
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")
    return cap


def main():
    # default to webcam 0 if no argument given
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cap = open_source(source)
    frame_interval = 1.0 / TARGET_FPS

    print(f"Opened source: {source}. Press 'q' to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Stream ended or frame read failed.")
            break

        cv2.imshow("fight - video_source checkpoint", frame)

        # 'q' to quit
        if cv2.waitKey(int(frame_interval * 1000)) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()