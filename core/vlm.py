import base64
import json
import os
import re
import sys
import threading
import time
import cv2
from concurrent.futures import ThreadPoolExecutor

from llama_cpp import Llama
from llama_cpp.llama_chat_format import Llava15ChatHandler

# --- Config ---------------------------------------------------------------

# UPDATE THESE to your actual file paths.
# Relative path - "models/" folder sitting alongside core/ and alerts/
# in your project root (E:\Fight\models\ locally, /app/models in Docker).
# Using a RELATIVE path (not a hardcoded absolute one) means this same
# line works correctly both when you run it locally from E:\Fight AND
# inside the Docker container - no path to edit between environments.
MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "Kimi-VL-A3B-Thinking-2506-Q4_K_M.gguf")
MMPROJ_PATH = os.path.join(MODEL_DIR, "mmproj-Kimi-VL-A3B-Thinking-2506-f16.gguf")

N_CTX = 4096          # enough for one image + short prompt + short answer
N_GPU_LAYERS = 0      # 0 = pure CPU. Raise this once you have a GPU set up.
N_THREADS = os.cpu_count() or 4

CONFIDENCE_THRESHOLD = 0.7  # below this, treat as unconfirmed

# CRITICAL: llama-cpp-python's Llama object is NOT safe to call from
# multiple threads at once. This lock + single-worker executor ensures
# only ONE inference ever runs at a time, no matter how many candidates
# get flagged simultaneously. Without this, concurrent candidates could
# crash the process or corrupt output.
_inference_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1)

print("[vlm.py] Loading Kimi-VL-A3B-Thinking directly in-process (no server)...")
print(f"[vlm.py]   model:  {MODEL_PATH}")
print(f"[vlm.py]   mmproj: {MMPROJ_PATH}")
_load_start = time.time()

_chat_handler = Llava15ChatHandler(clip_model_path=MMPROJ_PATH)
_llm = Llama(
    model_path=MODEL_PATH,
    chat_handler=_chat_handler,
    n_ctx=N_CTX,
    n_gpu_layers=N_GPU_LAYERS,
    n_threads=N_THREADS,
    verbose=False,
)

print(f"[vlm.py] Model loaded in {time.time() - _load_start:.1f}s. Fully offline, ready for inference.\n")


# --- Prompt templates -------------------------------------------------------
# One per alert type. Keep these tight: ask a specific question, demand
# JSON-only output, give the model an explicit schema to follow.

PROMPT_TEMPLATES = {
    "assault_candidate": (
        "You are a security monitoring assistant reviewing a single frame "
        "from a CCTV camera. Camera mounting angle: {mount_angle}. "
        "A motion-and-proximity rule has already "
        "flagged this frame because two people are close together with "
        "notable movement.\n\n"
        "Look at the image and determine whether this shows a physical "
        "altercation / fight / assault in progress, as opposed to a "
        "non-violent interaction (e.g. hugging, talking closely, walking "
        "together, waiting in line, dancing).\n\n"
        "Respond with ONLY a JSON object, no other text, no markdown "
        "fences, in exactly this format:\n"
        '{{"confirmed": true or false, "confidence": 0.0 to 1.0, '
        '"description": "one short sentence describing what is happening"}}'
    ),
    "weapon_candidate": (
        "You are a security monitoring assistant. Camera mounting angle: "
        "{mount_angle}. A weapon-detection rule "
        "has flagged this frame. Look at the image and determine whether "
        "a visible weapon (gun, knife, or similar) is actually present and "
        "being held/brandished, as opposed to a false positive (e.g. a "
        "phone, tool, or other object misidentified as a weapon).\n\n"
        "Respond with ONLY a JSON object, no other text, no markdown "
        "fences, in exactly this format:\n"
        '{{"confirmed": true or false, "confidence": 0.0 to 1.0, '
        '"description": "one short sentence describing what is visible"}}'
    ),
    "fire_candidate": (
        "You are a security monitoring assistant. Camera mounting angle: "
        "{mount_angle}. A fire/smoke-detection "
        "rule has flagged this frame. Look at the image and determine "
        "whether real fire or smoke is present, as opposed to a false "
        "positive (e.g. warm lighting, steam, red/orange objects, fog "
        "effects).\n\n"
        "Respond with ONLY a JSON object, no other text, no markdown "
        "fences, in exactly this format:\n"
        '{{"confirmed": true or false, "confidence": 0.0 to 1.0, '
        '"description": "one short sentence describing what is visible"}}'
    ),
    "animal_attack_candidate": (
        "You are a security monitoring assistant. Camera mounting angle: "
        "{mount_angle}. A rule has flagged this "
        "frame because an animal is close to a person with rapid approach "
        "motion. Look at the image and determine whether this shows an "
        "actual animal attack (biting, lunging aggressively, charging), "
        "as opposed to normal friendly interaction (e.g. an animal "
        "approaching for petting, playing, grazing nearby, walking on a "
        "leash).\n\n"
        "Respond with ONLY a JSON object, no other text, no markdown "
        "fences, in exactly this format:\n"
        '{{"confirmed": true or false, "confidence": 0.0 to 1.0, '
        '"description": "one short sentence describing what is happening and which animal"}}'
    ),
}


def build_prompt(candidate_type: str, mount_angle: str) -> str:
    template = PROMPT_TEMPLATES.get(candidate_type)
    if template is None:
        raise ValueError(f"No prompt template for candidate_type='{candidate_type}'")
    return template.format(mount_angle=mount_angle)


# --- Image prep --------------------------------------------------------------

def crop_region_of_interest(frame, bboxes, padding: int = 40):
    h, w = frame.shape[:2]
    xs = [b[0] for b in bboxes] + [b[2] for b in bboxes]
    ys = [b[1] for b in bboxes] + [b[3] for b in bboxes]
    x1 = max(0, min(xs) - padding)
    y1 = max(0, min(ys) - padding)
    x2 = min(w, max(xs) + padding)
    y2 = min(h, max(ys) + padding)
    return frame[y1:y2, x1:x2]


def _frame_to_data_uri(image) -> str:
    """OpenCV BGR image -> base64 JPEG data URI, decoded entirely in-process."""
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("Failed to encode image for VLM input.")
    b64 = base64.b64encode(buf).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


# --- Output parsing -----------------------------------------------------------

def parse_vlm_response(raw_text: str) -> dict:
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


# --- The actual inference call (runs in-process, no network) -----------------

def _run_inference(image_b64_uri: str, prompt: str) -> dict:
    """
    Blocking call - runs on the single background worker thread, never
    on the main video loop thread. The lock ensures we never call the
    model from two threads at once, even though the executor already
    limits us to 1 worker - this is defense in depth.
    """
    t0 = time.time()
    try:
        with _inference_lock:
            response = _llm.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_b64_uri}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=300,
                temperature=0.2,
            )
        raw_text = response["choices"][0]["message"]["content"]
        result = parse_vlm_response(raw_text)
        result["latency_seconds"] = round(time.time() - t0, 1)
        return result
    except Exception as e:
        return {
            "confirmed": False,
            "confidence": 0.0,
            "description": "",
            "error": f"inference_error: {e}",
            "latency_seconds": round(time.time() - t0, 1),
        }


def confirm_candidate_async(frame, bboxes, candidate_type: str, mount_angle: str = "unknown"):
    """
    Non-blocking entry point - identical interface to before, so
    assault.py / animal_attack.py need NO changes. Returns a Future
    immediately; the video loop keeps running while inference happens
    on the single background worker thread.
    """
    prompt = build_prompt(candidate_type, mount_angle)
    crop = crop_region_of_interest(frame, bboxes)
    data_uri = _frame_to_data_uri(crop)

    return _executor.submit(_run_inference, data_uri, prompt)


def is_confirmed(result: dict) -> bool:
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
    print("Running fully offline in-process inference (no server, no internet)...\n")

    future = confirm_candidate_async(frame, [(0, 0, w, h)], "assault_candidate", mount_angle="eye_level")
    result = future.result()

    print("\n--- Result ---")
    for k, v in result.items():
        print(f"{k}: {v}")

    print(f"\nFinal decision: {'CONFIRMED' if is_confirmed(result) else 'not confirmed'}")
    print("\nIf 'description' above is gibberish/unrelated to the image, Llava15ChatHandler")
    print("is likely not compatible with Kimi-VL's architecture - let me know and we'll")
    print("switch to the llama-server approach instead (still 100% local, different loading method).")

if __name__ == "__main__":
    main()
    