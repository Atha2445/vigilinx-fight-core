"""
vlm.py

Step 5 (final pipeline piece): async VLM confirmation using your
LOCALLY INSTALLED Kimi-VL-A3B model, served through LM Studio.

Prerequisite: LM Studio must be running with the model loaded AND its
local server started (LM Studio -> Developer tab / Local Server ->
"Start Server"). Default address is http://localhost:1234.

This module does NOT run the model itself - it just calls the local
HTTP API that LM Studio exposes, exactly like calling a cloud API,
except it's on your own machine with no internet or cost involved.

Usage (standalone test):
    python core/vlm.py path/to/test_image.jpg
"""

import base64
import json
import re
import sys
import time
import requests
import cv2
from concurrent.futures import ThreadPoolExecutor, Future

# --- Config ---------------------------------------------------------------

LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
# The model identifier LM Studio shows for your loaded model. Check LM
# Studio's server logs / Developer tab if this doesn't match exactly -
# some quant filenames differ slightly (e.g. include the quant suffix).
MODEL_NAME = "kimi-vl-a3b-thinking-2506"

REQUEST_TIMEOUT_SECONDS = 90  # CPU inference is slow - give it real room
CONFIDENCE_THRESHOLD = 0.7    # below this, treat as unconfirmed

# Max concurrent VLM calls in flight. Since this is a single local CPU
# model, keep this at 1 - the model can't actually run two inferences
# at once faster than sequentially, and trying to will just contend for
# the same CPU cores and slow both down.
MAX_CONCURRENT_VLM_CALLS = 1

_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_VLM_CALLS)


# --- Prompt templates -------------------------------------------------------
# One per alert type. Keep these tight: ask a specific question, demand
# JSON-only output, give the model an explicit schema to follow.

PROMPT_TEMPLATES = {
    "assault_candidate": (
        "You are a security monitoring assistant reviewing a single frame "
        "from a CCTV camera. A motion-and-proximity rule has already "
        "flagged this frame because two people are close together with "
        "notable movement.\n\n"
        "Look at the image and determine whether this shows a physical "
        "altercation / fight / assault in progress, as opposed to a "
        "non-violent interaction (e.g. hugging, talking closely, walking "
        "together, waiting in line, dancing).\n\n"
        "Respond with ONLY a JSON object, no other text, no markdown "
        "fences, in exactly this format:\n"
        '{"confirmed": true or false, "confidence": 0.0 to 1.0, '
        '"description": "one short sentence describing what is happening"}'
    ),
    "weapon_candidate": (
        "You are a security monitoring assistant. A weapon-detection rule "
        "has flagged this frame. Look at the image and determine whether "
        "a visible weapon (gun, knife, or similar) is actually present and "
        "being held/brandished, as opposed to a false positive (e.g. a "
        "phone, tool, or other object misidentified as a weapon).\n\n"
        "Respond with ONLY a JSON object, no other text, no markdown "
        "fences, in exactly this format:\n"
        '{"confirmed": true or false, "confidence": 0.0 to 1.0, '
        '"description": "one short sentence describing what is visible"}'
    ),
    "fire_candidate": (
        "You are a security monitoring assistant. A fire/smoke-detection "
        "rule has flagged this frame. Look at the image and determine "
        "whether real fire or smoke is present, as opposed to a false "
        "positive (e.g. warm lighting, steam, red/orange objects, fog "
        "effects).\n\n"
        "Respond with ONLY a JSON object, no other text, no markdown "
        "fences, in exactly this format:\n"
        '{"confirmed": true or false, "confidence": 0.0 to 1.0, '
        '"description": "one short sentence describing what is visible"}'
    ),
    "dog_attack_candidate": (
        "You are a security monitoring assistant. A rule has flagged this "
        "frame because a dog is close to a person with rapid approach "
        "motion. Look at the image and determine whether this shows an "
        "actual dog attack / aggressive lunging, as opposed to normal "
        "friendly interaction (e.g. a dog approaching for petting, playing).\n\n"
        "Respond with ONLY a JSON object, no other text, no markdown "
        "fences, in exactly this format:\n"
        '{"confirmed": true or false, "confidence": 0.0 to 1.0, '
        '"description": "one short sentence describing what is happening"}'
    ),
}


# --- Image prep --------------------------------------------------------------

def crop_region_of_interest(frame, bboxes, padding: int = 40):
    """
    Crops a frame to a padded bounding region covering all given bboxes,
    instead of sending the full frame. Faster inference, more focused
    answer, since the model only sees the relevant area.
    """
    h, w = frame.shape[:2]
    xs = [b[0] for b in bboxes] + [b[2] for b in bboxes]
    ys = [b[1] for b in bboxes] + [b[3] for b in bboxes]
    x1 = max(0, min(xs) - padding)
    y1 = max(0, min(ys) - padding)
    x2 = min(w, max(xs) + padding)
    y2 = min(h, max(ys) + padding)
    return frame[y1:y2, x1:x2]


def encode_image_b64(image) -> str:
    """OpenCV BGR image -> base64-encoded JPEG string for the API payload."""
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("Failed to encode image for VLM request.")
    return base64.b64encode(buf).decode("utf-8")


# --- Output parsing -----------------------------------------------------------

def parse_vlm_response(raw_text: str) -> dict:
    """
    Parses the model's text response into the expected structured dict.
    Handles the common case where the model adds markdown fences or stray
    text around the JSON despite instructions - strips them and retries.

    Returns a dict with confirmed/confidence/description, OR a dict with
    confirmed=False and an "error" key if parsing ultimately fails - this
    is the fallback path so a malformed response never crashes the pipeline.
    """
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        return {
            "confirmed": bool(data.get("confirmed", False)),
            "confidence": float(data.get("confidence", 0.0)),
            "description": str(data.get("description", "")),
            "raw": raw_text,
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        return {
            "confirmed": False,
            "confidence": 0.0,
            "description": "",
            "error": f"parse_failed: {e}",
            "raw": raw_text,
        }


# --- The actual API call -------------------------------------------------------

def _call_local_vlm(image_b64: str, prompt: str) -> dict:
    """
    Blocking call to the local LM Studio server. Run this inside the
    thread pool (see confirm_candidate_async), never on the main loop.
    """
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.8,  # Moonshot's recommended setting for this Thinking model
        "max_tokens": 300,
    }

    t0 = time.time()
    try:
        resp = requests.post(
            f"{LM_STUDIO_BASE_URL}/chat/completions",
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]
        result = parse_vlm_response(raw_text)
        result["latency_seconds"] = round(time.time() - t0, 1)
        return result
    except requests.exceptions.ConnectionError:
        return {
            "confirmed": False,
            "confidence": 0.0,
            "description": "",
            "error": "connection_failed - is LM Studio's local server running?",
            "latency_seconds": round(time.time() - t0, 1),
        }
    except requests.exceptions.Timeout:
        return {
            "confirmed": False,
            "confidence": 0.0,
            "description": "",
            "error": f"timeout after {REQUEST_TIMEOUT_SECONDS}s - CPU inference may need a longer timeout",
            "latency_seconds": round(time.time() - t0, 1),
        }
    except Exception as e:
        return {
            "confirmed": False,
            "confidence": 0.0,
            "description": "",
            "error": f"unexpected_error: {e}",
            "latency_seconds": round(time.time() - t0, 1),
        }


def confirm_candidate_async(frame, bboxes, candidate_type: str):
    """
    Non-blocking entry point. Call this from your alert modules when a
    rule-based candidate is flagged. Returns a Future immediately - the
    video pipeline keeps running while this resolves in the background.

    Example:
        future = confirm_candidate_async(frame, [box_a, box_b], "assault_candidate")
        # ... keep processing frames ...
        if future.done():
            result = future.result()
            if result["confirmed"] and result["confidence"] >= CONFIDENCE_THRESHOLD:
                dispatch_alert(result)
    """
    prompt = PROMPT_TEMPLATES.get(candidate_type)
    if prompt is None:
        raise ValueError(f"No prompt template for candidate_type='{candidate_type}'")

    crop = crop_region_of_interest(frame, bboxes)
    image_b64 = encode_image_b64(crop)

    return _executor.submit(_call_local_vlm, image_b64, prompt)


def is_confirmed(result: dict) -> bool:
    """Final decision helper: applies the confidence threshold consistently."""
    if result.get("error"):
        return False
    return result.get("confirmed", False) and result.get("confidence", 0.0) >= CONFIDENCE_THRESHOLD


# --- Standalone test ---------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python core/vlm.py path/to/test_image.jpg")
        return

    image_path = sys.argv[1]
    frame = cv2.imread(image_path)
    if frame is None:
        raise RuntimeError(f"Could not read image: {image_path}")

    h, w = frame.shape[:2]
    print(f"Loaded {image_path} ({w}x{h})")
    print(f"Calling local VLM at {LM_STUDIO_BASE_URL} with model '{MODEL_NAME}'...")
    print("(Make sure LM Studio's local server is running and the model is loaded)\n")

    future = confirm_candidate_async(frame, [(0, 0, w, h)], "assault_candidate")
    print("Request sent, waiting for response (this may take a while on CPU)...")
    result = future.result()  # blocks in this standalone test, unlike real pipeline usage

    print("\n--- Result ---")
    for k, v in result.items():
        print(f"{k}: {v}")

    print(f"\nFinal decision: {'CONFIRMED' if is_confirmed(result) else 'not confirmed'}")


if __name__ == "__main__":
    main()