"""Snapshot the active 3D viewport as a PNG-encoded bytes buffer.

Primary path: read the back buffer of the active M3dView directly. This is
fast and bypasses disk. If that fails (some GPU drivers refuse the
readback, especially on headless or Metal-backed renders), fall back to a
one-frame playblast through Maya's hardware renderer.
"""
from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui


@dataclass
class Snapshot:
    png: bytes
    width: int
    height: int
    camera: str


def _active_camera() -> str:
    view = omui.M3dView.active3dView()
    cam_dag = om.MDagPath()
    view.getCamera(cam_dag)
    return cam_dag.partialPathName()


def _readback_active_view() -> Optional[Snapshot]:
    try:
        from PySide6.QtGui import QImage
    except ImportError:
        from PySide2.QtGui import QImage  # safety net for older Maya

    view = omui.M3dView.active3dView()
    view.refresh(True, True)
    image = om.MImage()
    view.readColorBuffer(image, True)  # True = read RGBA
    w, h = image.getSize()
    if w == 0 or h == 0:
        return None

    # MImage pixels are BGRA, bottom-up. Round-trip through QImage to flip
    # and re-encode as PNG without dragging numpy in.
    raw = bytes(image.pixels())
    qimg = QImage(raw, w, h, QImage.Format_ARGB32).mirrored(False, True)
    buf = io.BytesIO()
    # QImage.save needs a QBuffer; easier path: write to a temp file.
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
    try:
        if not qimg.save(tmp_path, "PNG"):
            return None
        with open(tmp_path, "rb") as f:
            png_bytes = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return Snapshot(png=png_bytes, width=w, height=h, camera=_active_camera())


def _playblast_fallback(width: int = 1920, height: int = 1080) -> Snapshot:
    cam = _active_camera()
    tmpdir = tempfile.mkdtemp(prefix="shoot_pb_")
    out = os.path.join(tmpdir, "frame")
    current = cmds.currentTime(q=True)
    files = cmds.playblast(
        format="image",
        compression="png",
        filename=out,
        widthHeight=(width, height),
        startTime=current,
        endTime=current,
        forceOverwrite=True,
        viewer=False,
        offScreen=True,
        showOrnaments=False,
        percent=100,
        quality=100,
    )
    # playblast returns the path with a frame token; resolve actual file.
    candidates = [p for p in os.listdir(tmpdir) if p.endswith(".png")]
    if not candidates:
        raise RuntimeError("playblast produced no frame")
    path = os.path.join(tmpdir, candidates[0])
    with open(path, "rb") as f:
        png = f.read()
    return Snapshot(png=png, width=width, height=height, camera=cam)


def snapshot_active_view() -> Snapshot:
    shot = _readback_active_view()
    if shot is not None:
        return shot
    return _playblast_fallback()
