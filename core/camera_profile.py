"""
camera_profile.py

Solves the camera-angle brittleness problem by giving every camera a
profile that describes HOW it sees the scene (mount angle + physical
scale), and routes detection modules based on that profile instead of
hard-coded pixel thresholds.

Usage:
    profile = CameraProfile.load("cam_lobby_01")
    if profile.is_module_active("pose_fight_detection"):
        run_pose_pipeline(frame, profile)
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# 1. Angle categories
# ---------------------------------------------------------------------------

class MountAngle(str, Enum):
    EYE_LEVEL = "eye_level"           # 0-15 deg tilt from horizontal
    ANGLED_LOW = "angled_low"         # 15-40 deg
    ANGLED_HIGH = "angled_high"       # 40-65 deg
    OVERHEAD_STEEP = "overhead_steep" # 65-85 deg
    OVERHEAD_NADIR = "overhead_nadir" # 85-90 deg


ANGLE_RANGES = {
    MountAngle.EYE_LEVEL:      (0, 15),
    MountAngle.ANGLED_LOW:     (15, 40),
    MountAngle.ANGLED_HIGH:    (40, 65),
    MountAngle.OVERHEAD_STEEP: (65, 85),
    MountAngle.OVERHEAD_NADIR: (85, 90),
}


def classify_tilt_angle(tilt_deg: float) -> MountAngle:
    """Map a measured tilt angle (degrees from horizontal) to a category."""
    tilt_deg = max(0.0, min(90.0, tilt_deg))
    for angle_type, (lo, hi) in ANGLE_RANGES.items():
        if lo <= tilt_deg <= hi:
            return angle_type
    return MountAngle.ANGLED_LOW  # fallback, should not hit given clamp above


# ---------------------------------------------------------------------------
# 2. Which detection modules are valid per angle category
# ---------------------------------------------------------------------------
# Module names correspond to logical stages in your existing pipeline
# (alerts/, core/detector.py, core/tracker.py, etc). Extend this table as
# you add new detectors.

MODULE_MATRIX: dict[MountAngle, dict[str, bool]] = {
    MountAngle.EYE_LEVEL: {
        "pose_fight_detection": True,
        "fist_to_head_check": True,
        "face_recognition": True,
        "bbox_height_normalization": True,
        "ground_plane_proximity": False,   # not reliable at this angle
        "weapon_detection": True,
        "fire_smoke_detection": True,
        "dog_attack_detection": True,
    },
    MountAngle.ANGLED_LOW: {
        "pose_fight_detection": True,
        "fist_to_head_check": True,
        "face_recognition": True,
        "bbox_height_normalization": True,
        "ground_plane_proximity": False,
        "weapon_detection": True,
        "fire_smoke_detection": True,
        "dog_attack_detection": True,
    },
    MountAngle.ANGLED_HIGH: {
        "pose_fight_detection": True,       # degraded but usable
        "fist_to_head_check": False,        # foreshortening makes this unreliable
        "face_recognition": True,           # partial faces, lower confidence
        "bbox_height_normalization": True,
        "ground_plane_proximity": True,     # start blending in real-world calibration
        "weapon_detection": True,
        "fire_smoke_detection": True,
        "dog_attack_detection": True,
    },
    MountAngle.OVERHEAD_STEEP: {
        "pose_fight_detection": False,
        "fist_to_head_check": False,
        "face_recognition": False,
        "bbox_height_normalization": False,
        "ground_plane_proximity": True,
        "weapon_detection": True,           # SAHI slicing still works reasonably
        "fire_smoke_detection": True,
        "dog_attack_detection": True,       # via proximity + motion, not pose
    },
    MountAngle.OVERHEAD_NADIR: {
        "pose_fight_detection": False,
        "fist_to_head_check": False,
        "face_recognition": False,
        "bbox_height_normalization": False,
        "ground_plane_proximity": True,
        "weapon_detection": True,
        "fire_smoke_detection": True,
        "dog_attack_detection": True,
    },
}


# ---------------------------------------------------------------------------
# 3. Calibration: convert real-world meters <-> pixels for THIS camera
# ---------------------------------------------------------------------------

@dataclass
class Calibration:
    """
    Minimal one-point calibration: pixels-per-meter at the ground plane.
    Good enough for proximity thresholds without full homography.

    For angled/overhead cameras, pixels-per-meter varies slightly across
    the frame (near vs far from camera), so `reference_depth_px` records
    where in the frame this calibration was measured, letting you apply
    a simple linear correction if needed later.
    """
    pixels_per_meter: float
    reference_depth_px: Optional[float] = None  # y-coordinate where measured
    method: str = "manual_two_point"             # or "homography", "none"

    def meters_to_pixels(self, meters: float) -> float:
        return meters * self.pixels_per_meter

    def pixels_to_meters(self, pixels: float) -> float:
        if self.pixels_per_meter == 0:
            return 0.0
        return pixels / self.pixels_per_meter


def calibrate_from_two_points(
    pixel_dist: float, real_world_meters: float
) -> Calibration:
    """
    Build a Calibration from a single reference measurement.

    Example: installer marks two floor tiles 2 meters apart in a test
    frame, measures the pixel distance between them (e.g. 340px):

        calibrate_from_two_points(pixel_dist=340, real_world_meters=2.0)
        -> Calibration(pixels_per_meter=170.0)
    """
    if real_world_meters <= 0:
        raise ValueError("real_world_meters must be > 0")
    return Calibration(pixels_per_meter=pixel_dist / real_world_meters)


# ---------------------------------------------------------------------------
# 4. The camera profile itself
# ---------------------------------------------------------------------------

@dataclass
class CameraProfile:
    camera_id: str
    tilt_deg: float
    mount_angle: MountAngle = field(init=False)
    calibration: Optional[Calibration] = None
    frame_width: int = 1920
    frame_height: int = 1080
    notes: str = ""

    def __post_init__(self):
        self.mount_angle = classify_tilt_angle(self.tilt_deg)

    # -- module routing -----------------------------------------------------
    def is_module_active(self, module_name: str) -> bool:
        matrix = MODULE_MATRIX.get(self.mount_angle, {})
        return matrix.get(module_name, False)

    def active_modules(self) -> list[str]:
        matrix = MODULE_MATRIX.get(self.mount_angle, {})
        return [name for name, active in matrix.items() if active]

    # -- threshold resolution ------------------------------------------------
    def proximity_threshold_px(self, real_world_meters: float, bbox_height_px: Optional[float] = None) -> float:
        """
        Resolve a real-world proximity threshold (meters) into a pixel
        threshold appropriate for THIS camera's geometry.

        Priority:
          1. If calibrated (pixels-per-meter known) -> use it directly.
             Best for overhead / angled-high cameras.
          2. Else if bbox_height_px given -> fall back to bbox-relative
             normalization. Best for eye-level / angled-low cameras
             where calibration hasn't been done yet.
          3. Else -> raise, caller must supply one of the two.
        """
        if self.calibration is not None:
            return self.calibration.meters_to_pixels(real_world_meters)

        if bbox_height_px is not None:
            # Heuristic: an average adult standing is ~1.7m tall.
            # ratio of desired real-world distance to a "person height unit"
            # scaled onto this person's current apparent bbox height.
            AVG_PERSON_HEIGHT_M = 1.7
            ratio = real_world_meters / AVG_PERSON_HEIGHT_M
            return ratio * bbox_height_px

        raise ValueError(
            f"Camera '{self.camera_id}' has no calibration and no bbox_height_px "
            "was provided — cannot resolve a pixel threshold."
        )

    # -- persistence ----------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["mount_angle"] = self.mount_angle.value
        return d

    def save(self, directory: str = "./camera_profiles") -> str:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{self.camera_id}.json")
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return path

    @classmethod
    def load(cls, camera_id: str, directory: str = "./camera_profiles") -> "CameraProfile":
        path = os.path.join(directory, f"{camera_id}.json")
        with open(path) as f:
            data = json.load(f)
        calib = None
        if data.get("calibration"):
            calib = Calibration(**data["calibration"])
        return cls(
            camera_id=data["camera_id"],
            tilt_deg=data["tilt_deg"],
            calibration=calib,
            frame_width=data.get("frame_width", 1920),
            frame_height=data.get("frame_height", 1080),
            notes=data.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# 5. Example: wiring this into an existing alert module
# ---------------------------------------------------------------------------

def example_assault_alert_check(
    profile: CameraProfile,
    person_a_bbox,   # (x1, y1, x2, y2)
    person_b_bbox,
) -> bool:
    """
    Illustrates how AssaultAlert would use the profile instead of a
    hard-coded 120px constant. Drop-in replacement pattern for your
    alerts/assault.py module.
    """
    if not profile.is_module_active("pose_fight_detection") and not profile.is_module_active(
        "ground_plane_proximity"
    ):
        # Neither signal is trustworthy at this angle — skip this rule
        # entirely and rely on motion + VLM only.
        return False

    a_cx = (person_a_bbox[0] + person_a_bbox[2]) / 2
    a_cy = (person_a_bbox[1] + person_a_bbox[3]) / 2
    b_cx = (person_b_bbox[0] + person_b_bbox[2]) / 2
    b_cy = (person_b_bbox[1] + person_b_bbox[3]) / 2

    pixel_dist = ((a_cx - b_cx) ** 2 + (a_cy - b_cy) ** 2) ** 0.5

    a_height = person_a_bbox[3] - person_a_bbox[1]

    # "close" = within 0.6 meters, resolved per-camera
    threshold_px = profile.proximity_threshold_px(
        real_world_meters=0.6, bbox_height_px=a_height
    )

    return pixel_dist < threshold_px


if __name__ == "__main__":
    # --- Example: eye-level camera, no calibration yet ---
    cam1 = CameraProfile(camera_id="lobby_entrance", tilt_deg=10)
    print(cam1.mount_angle)              # MountAngle.EYE_LEVEL
    print(cam1.active_modules())

    # --- Example: overhead camera, calibrated ---
    calib = calibrate_from_two_points(pixel_dist=340, real_world_meters=2.0)
    cam2 = CameraProfile(camera_id="ceiling_hallway", tilt_deg=88, calibration=calib)
    print(cam2.mount_angle)              # MountAngle.OVERHEAD_NADIR
    print(cam2.active_modules())         # pose/face modules excluded
    print(cam2.proximity_threshold_px(real_world_meters=0.6))  # 102.0 px (170 px/m * 0.6m)

    cam1.save() 
    cam2.save() 