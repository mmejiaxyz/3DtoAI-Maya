"""Snapshot the active 3D viewport as a PNG-encoded bytes buffer.

Primary path  : read the back buffer of the active M3dView directly.
Fallback path : one-frame playblast through Maya's hardware renderer.
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

SHOOT_VIEWPORT_VERSION = "v4-single-shot-2026-05-16"
print(f"[shoot.capture.viewport] loaded {SHOOT_VIEWPORT_VERSION}")


@dataclass
class Snapshot:
    png: bytes
    width: int
    height: int
    camera: str


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
    """Return (horizontal_deg, vertical_deg, label) for the active viewport camera."""
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

    return h_deg, v_deg, _angle_label(h_deg, v_deg)
