"""Snapshot the active 3D viewport as a PNG-encoded bytes buffer.

Primary path  : read the back buffer of the active M3dView directly.
Fallback path : one-frame playblast through Maya's hardware renderer.

Also exposes the active camera's spherical pose around the scene's
bbox center (h°, v°, distance) — used by the multi-angle flow to encode
the camera-delta vs. an anchor pose as a continuous-degree prompt.
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
from dataclasses import dataclass
from typing import Optional

from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui

SHOOT_VIEWPORT_VERSION = "v5-multi-angle-2026-05-18"
print(f"[shoot.capture.viewport] loaded {SHOOT_VIEWPORT_VERSION}")


@dataclass
class Snapshot:
    png: bytes
    width: int
    height: int
    camera: str


@dataclass
class CameraState:
    """Active viewport camera in spherical coords around the scene bbox center.

    h_deg    : azimuth in degrees, 0 = looking toward +Z from -Z (Maya world).
    v_deg    : elevation in degrees, positive = above the scene center.
    distance : world-space camera-to-center distance. Drives dolly/zoom
               detection (close-up vs wide-shot) in multi-angle mode.
    label    : human-readable shorthand ("front-right view, eye level").
    """
    h_deg:    float
    v_deg:    float
    distance: float
    label:    str


# ── Active-camera helpers ─────────────────────────────────────────────────────

def _active_camera() -> str:
    view = omui.M3dView.active3dView()
    try:
        cam_dag = view.getCamera()
    except TypeError:
        cam_dag = om.MDagPath()
        view.getCamera(cam_dag)
    return cam_dag.partialPathName()


def _active_model_panel() -> Optional[str]:
    try:
        panel = cmds.getPanel(withFocus=True)
        if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
            return panel
    except Exception:
        pass
    try:
        for panel in (cmds.getPanel(visiblePanels=True) or []):
            try:
                if cmds.getPanel(typeOf=panel) == "modelPanel":
                    return panel
            except Exception:
                continue
    except Exception:
        pass
    return None


# ── Single-frame capture ──────────────────────────────────────────────────────

def _readback_active_view() -> Optional[Snapshot]:
    try:
        view = omui.M3dView.active3dView()
        view.refresh(True, True)
        image = om.MImage()
        view.readColorBuffer(image, True)
        w, h = image.getSize()
        if w == 0 or h == 0:
            return None
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
        try:
            image.writeToFile(tmp_path, "png")
            with open(tmp_path, "rb") as f:
                png_bytes = f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return Snapshot(png=png_bytes, width=w, height=h, camera=_active_camera())
    except Exception:
        import traceback
        sys.stderr.write("[shoot] readback failed, falling back to playblast:\n")
        traceback.print_exc(file=sys.stderr)
        return None


def _playblast_fallback(width: int = 1920, height: int = 1080) -> Snapshot:
    cam = _active_camera()
    tmpdir = tempfile.mkdtemp(prefix="shoot_pb_")
    out = os.path.join(tmpdir, "frame")
    current = cmds.currentTime(q=True)
    cmds.playblast(
        format="image", compression="png", filename=out,
        widthHeight=(width, height), startTime=current, endTime=current,
        forceOverwrite=True, viewer=False, offScreen=True,
        showOrnaments=False, percent=100, quality=100,
    )
    candidates = [p for p in os.listdir(tmpdir) if p.endswith(".png")]
    if not candidates:
        raise RuntimeError("playblast produced no frame")
    with open(os.path.join(tmpdir, candidates[0]), "rb") as f:
        png = f.read()
    return Snapshot(png=png, width=width, height=height, camera=cam)


def snapshot_active_view() -> Snapshot:
    shot = _readback_active_view()
    return shot if shot is not None else _playblast_fallback()


# ── Viewport angle (informational) ────────────────────────────────────────────

def _angle_label(h_deg: float, v_deg: float) -> str:
    h = h_deg % 360
    if h < 22.5 or h >= 337.5:
        h_text = "front"
    elif h < 67.5:
        h_text = "front-right"
    elif h < 112.5:
        h_text = "right side"
    elif h < 157.5:
        h_text = "back-right"
    elif h < 202.5:
        h_text = "back"
    elif h < 247.5:
        h_text = "back-left"
    elif h < 292.5:
        h_text = "left side"
    else:
        h_text = "front-left"

    if v_deg > 40:
        v_text = "top-down"
    elif v_deg > 20:
        v_text = "high angle"
    elif v_deg > -10:
        v_text = "eye level"
    elif v_deg > -30:
        v_text = "low angle"
    else:
        v_text = "worm's eye"

    return f"{h_text} view, {v_text}"


def _scene_center() -> tuple[float, float, float]:
    meshes = cmds.ls(type="mesh", visible=True, long=True) or []
    transforms = []
    for mesh in meshes:
        parent = cmds.listRelatives(mesh, parent=True, fullPath=True)
        if parent:
            transforms.append(parent[0])
    if not transforms:
        return (0.0, 0.0, 0.0)
    bbox = cmds.exactWorldBoundingBox(transforms)
    return (
        (bbox[0] + bbox[3]) * 0.5,
        (bbox[1] + bbox[4]) * 0.5,
        (bbox[2] + bbox[5]) * 0.5,
    )


def get_viewport_angle(scene_center: Optional[tuple] = None) -> tuple[float, float, str]:
    """Back-compat shim — same shape as before, returns (h, v, label)."""
    state = get_camera_state(scene_center)
    return state.h_deg, state.v_deg, state.label


def get_camera_state(scene_center: Optional[tuple] = None) -> CameraState:
    """Active viewport camera in spherical coords around the scene bbox center.

    MUST be called from Maya's main thread — ``cmds.modelPanel`` raises
    ``"Flag withFocus must be passed a boolean argument"`` off-thread.
    """
    panel = _active_model_panel()
    camera = None
    if panel:
        try:
            camera = cmds.modelPanel(panel, q=True, camera=True)
        except Exception:
            camera = None
    if not camera:
        camera = _active_camera()

    cam_pos = cmds.xform(camera, q=True, ws=True, t=True)
    if scene_center is None:
        scene_center = _scene_center()

    dx = cam_pos[0] - scene_center[0]
    dy = cam_pos[1] - scene_center[1]
    dz = cam_pos[2] - scene_center[2]

    h_deg = math.degrees(math.atan2(dx, dz)) % 360
    horiz = math.sqrt(dx * dx + dz * dz)
    v_deg = math.degrees(math.atan2(dy, horiz))
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)

    return CameraState(
        h_deg=h_deg,
        v_deg=v_deg,
        distance=distance,
        label=_angle_label(h_deg, v_deg),
    )


# ── Camera-delta → prompt encoder ─────────────────────────────────────────────
#
# Multi-angle mode: the Qwen-Image-Edit + Multiple-Angles LoRA was trained on
# degree-based imperatives ("Rotate the camera 45 degrees to the right.").
# We extend that grammar to continuous degrees + composed clauses so the
# *exact* Maya camera move maps to a prompt, not a snap to nearest preset.

# Noise floors — below this, an axis is treated as unchanged.
_DH_NOISE_DEG       = 2.0
_DV_NOISE_DEG       = 2.0
_DDIST_NOISE_RATIO  = 0.08   # 8% dolly is below perception

# Past these, a single axis "wins" and we use a named-shot phrase that the
# LoRA was *literally* trained on, rather than degree numerics that may
# wander out of distribution.
_AERIAL_MIN_V_DEG   = 50.0
_LOW_ANGLE_MAX_V_DEG = -35.0


def _normalize_delta_h(delta_h: float) -> float:
    """Normalize a horizontal-azimuth difference to (-180, +180]."""
    return ((delta_h + 540.0) % 360.0) - 180.0


def describe_camera_delta(anchor: CameraState, current: CameraState) -> str:
    """Encode (anchor → current) camera move as one imperative sentence.

    Single-axis dominant moves snap to the LoRA's named shots when the
    axis crosses a strong threshold:
      • |Δv| past _AERIAL_MIN_V_DEG / _LOW_ANGLE_MAX_V_DEG   → aerial / low-angle
      • |Δd| past ~25% with little orbit                      → close-up / wide
    Otherwise the result is composed from degree-precise clauses for the
    axes that changed (rotate left/right, tilt up/down, dolly closer/farther).
    """
    delta_h = _normalize_delta_h(current.h_deg - anchor.h_deg)
    delta_v = current.v_deg - anchor.v_deg

    if anchor.distance > 1e-6:
        delta_d_ratio = (current.distance - anchor.distance) / anchor.distance
    else:
        delta_d_ratio = 0.0

    # 1) Strong tilt → use the LoRA-trained named shot. Modest orbit alongside
    #    a strong tilt is dropped; aerial/low-angle dominate.
    abs_dh = abs(delta_h)
    if current.v_deg >= _AERIAL_MIN_V_DEG and delta_v > 10.0 and abs_dh < 25.0:
        return "Turn the camera to an aerial view."
    if current.v_deg <= _LOW_ANGLE_MAX_V_DEG and delta_v < -10.0 and abs_dh < 25.0:
        return "Turn the camera to a low-angle view."

    # 2) Strong dolly with little orbit/tilt → close-up / wide.
    if abs(delta_d_ratio) >= 0.25 and abs_dh < 15.0 and abs(delta_v) < 10.0:
        if delta_d_ratio < 0:
            return "Turn the camera to a close-up."
        return "Turn the camera to a wide-angle lens."

    # 3) Compose degree-precise clauses for each axis above its noise floor.
    parts: list[str] = []
    if abs_dh >= _DH_NOISE_DEG:
        side = "right" if delta_h > 0 else "left"
        parts.append(f"rotate the camera {int(round(abs_dh))} degrees to the {side}")
    if abs(delta_v) >= _DV_NOISE_DEG:
        direction = "up" if delta_v > 0 else "down"
        parts.append(f"tilt the camera {int(round(abs(delta_v)))} degrees {direction}")
    if abs(delta_d_ratio) >= _DDIST_NOISE_RATIO:
        if delta_d_ratio < 0:
            parts.append(f"dolly the camera {int(round(abs(delta_d_ratio) * 100))} percent closer")
        else:
            parts.append(f"dolly the camera {int(round(delta_d_ratio * 100))} percent farther")

    if not parts:
        # Camera barely moved — give Qwen-Edit a no-op-shaped instruction
        # that's still inside the LoRA's grammar.
        return "Keep the camera in the same position."

    if len(parts) == 1:
        return parts[0][0].upper() + parts[0][1:] + "."
    if len(parts) == 2:
        joined = parts[0] + " and " + parts[1]
        return joined[0].upper() + joined[1:] + "."
    joined = parts[0] + ", " + parts[1] + ", and " + parts[2]
    return joined[0].upper() + joined[1:] + "."
