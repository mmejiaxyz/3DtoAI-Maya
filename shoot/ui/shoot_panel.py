"""Shoot panel: PySide6 dockable widget for Maya 2026.

Left column: prompt, camera settings, Shoot button.
Right column: preview of the result.
Generation runs on a QThreadPool worker so the Maya UI thread stays free.
"""
from __future__ import annotations

from typing import Optional

# Maya 2026 ships PySide6. Keep a PySide2 fallback so the same file works
# if someone ports this to 2024.
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
    PYSIDE_VERSION = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
    PYSIDE_VERSION = 2

import maya.OpenMayaUI as omui_legacy

from shoot.capture.viewport import snapshot_active_view, Snapshot
from shoot.inference.gemini import ShotRequest, ShotResult, generate
from shoot import settings as shoot_settings


PANEL_OBJECT_NAME = "shootPanel"


def _maya_main_window() -> QtWidgets.QWidget:
    ptr = omui_legacy.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


class _ShootSignals(QtCore.QObject):
    done = QtCore.Signal(object)   # ShotResult
    failed = QtCore.Signal(str)


class _ShootWorker(QtCore.QRunnable):
    def __init__(self, req: ShotRequest):
        super().__init__()
        self.req = req
        self.signals = _ShootSignals()

    def run(self):
        try:
            result = generate(self.req)
            self.signals.done.emit(result)
        except Exception as e:
            self.signals.failed.emit(str(e))


class ShootPanel(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent or _maya_main_window())
        self.setObjectName(PANEL_OBJECT_NAME)
        self.setWindowTitle("Shoot")
        self.setWindowFlags(QtCore.Qt.Window)
        self.resize(1100, 600)
        self._pool = QtCore.QThreadPool.globalInstance()
        self._last_snapshot: Optional[Snapshot] = None
        self._build_ui()

    def _build_ui(self):
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # --- Left: controls ---------------------------------------------
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(8)

        cam_row = QtWidgets.QHBoxLayout()
        self.aspect = QtWidgets.QComboBox()
        self.aspect.addItems(["16:9", "4:3", "1:1", "9:16", "2.35:1"])
        self.focal = QtWidgets.QComboBox()
        self.focal.addItems(["24", "35", "50", "85"])
        self.focal.setCurrentText("35")
        self.aperture = QtWidgets.QComboBox()
        self.aperture.addItems(["1.4", "2", "2.8", "4", "8"])
        self.aperture.setCurrentText("2.8")
        for label, w in [("Aspect", self.aspect), ("Focal (mm)", self.focal), ("f/", self.aperture)]:
            col = QtWidgets.QVBoxLayout()
            col.addWidget(QtWidgets.QLabel(label))
            col.addWidget(w)
            cam_row.addLayout(col)
        left.addLayout(cam_row)

        left.addWidget(QtWidgets.QLabel("Prompt"))
        self.prompt = QtWidgets.QPlainTextEdit()
        self.prompt.setPlaceholderText("Describe how this shot should look…")
        self.prompt.setMinimumHeight(120)
        left.addWidget(self.prompt)

        btn_row = QtWidgets.QHBoxLayout()
        self.preview_btn = QtWidgets.QPushButton("Snap Viewport")
        self.preview_btn.clicked.connect(self._on_snap_clicked)
        self.shoot_btn = QtWidgets.QPushButton("Shoot")
        self.shoot_btn.setDefault(True)
        self.shoot_btn.clicked.connect(self._on_shoot_clicked)
        btn_row.addWidget(self.preview_btn)
        btn_row.addWidget(self.shoot_btn)
        left.addLayout(btn_row)

        api_row = QtWidgets.QHBoxLayout()
        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("Gemini API key (optional, env GEMINI_API_KEY wins)")
        existing = shoot_settings.get_api_key()
        if existing:
            self.api_key_edit.setPlaceholderText("Gemini API key set ✓")
        save_key_btn = QtWidgets.QPushButton("Save Key")
        save_key_btn.clicked.connect(self._on_save_key)
        api_row.addWidget(self.api_key_edit)
        api_row.addWidget(save_key_btn)
        left.addLayout(api_row)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: #888;")
        left.addWidget(self.status)
        left.addStretch(1)

        left_wrap = QtWidgets.QWidget()
        left_wrap.setLayout(left)
        left_wrap.setFixedWidth(360)
        root.addWidget(left_wrap)

        # --- Right: previews --------------------------------------------
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(6)
        self.ref_label = QtWidgets.QLabel("Reference (viewport)")
        self.ref_view = _ImageView()
        self.result_label = QtWidgets.QLabel("Result")
        self.result_view = _ImageView()
        for w in (self.ref_label, self.ref_view, self.result_label, self.result_view):
            right.addWidget(w)
        right.setStretchFactor(self.ref_view, 1)
        right.setStretchFactor(self.result_view, 1)
        right_wrap = QtWidgets.QWidget()
        right_wrap.setLayout(right)
        root.addWidget(right_wrap, 1)

    # ---- actions ------------------------------------------------------

    def _on_save_key(self):
        key = self.api_key_edit.text().strip()
        if not key:
            self._set_status("Enter a key first.")
            return
        shoot_settings.set_api_key(key)
        self.api_key_edit.clear()
        self.api_key_edit.setPlaceholderText("Gemini API key set ✓")
        self._set_status("API key saved to Maya optionVar.")

    def _on_snap_clicked(self):
        try:
            snap = snapshot_active_view()
        except Exception as e:
            self._set_status(f"Snap failed: {e}")
            return
        self._last_snapshot = snap
        self.ref_view.set_png(snap.png)
        self._set_status(f"Captured {snap.camera} ({snap.width}×{snap.height}).")

    def _on_shoot_clicked(self):
        if self._last_snapshot is None:
            self._on_snap_clicked()
            if self._last_snapshot is None:
                return
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            self._set_status("Write a prompt first.")
            return

        req = ShotRequest(
            prompt=prompt,
            reference_png=self._last_snapshot.png,
            aspect_ratio=self.aspect.currentText(),
            focal_length_mm=int(self.focal.currentText()),
            aperture=float(self.aperture.currentText()),
        )
        self._set_busy(True, "Shooting…")
        worker = _ShootWorker(req)
        worker.signals.done.connect(self._on_shot_done)
        worker.signals.failed.connect(self._on_shot_failed)
        self._pool.start(worker)

    def _on_shot_done(self, result: ShotResult):
        self.result_view.set_png(result.png)
        self._set_busy(False, "Done.")

    def _on_shot_failed(self, msg: str):
        self._set_busy(False, f"Failed: {msg}")

    # ---- helpers ------------------------------------------------------

    def _set_busy(self, busy: bool, status: str = ""):
        self.shoot_btn.setEnabled(not busy)
        self.preview_btn.setEnabled(not busy)
        if status:
            self._set_status(status)

    def _set_status(self, msg: str):
        self.status.setText(msg)


class _ImageView(QtWidgets.QLabel):
    """QLabel that holds a QPixmap and rescales on resize."""

    def __init__(self):
        super().__init__()
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet("background: #111; border: 1px solid #2a2a2a;")
        self.setMinimumHeight(160)
        self._src: Optional[QtGui.QPixmap] = None

    def set_png(self, png: bytes):
        pm = QtGui.QPixmap()
        pm.loadFromData(png, "PNG")
        self._src = pm
        self._render()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def _render(self):
        if self._src is None:
            return
        scaled = self._src.scaled(
            self.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)


_panel_instance: Optional[ShootPanel] = None


def show_panel():
    global _panel_instance
    if _panel_instance is None or not _panel_instance.isVisible():
        # If a stale instance exists, drop it.
        if _panel_instance is not None:
            try:
                _panel_instance.close()
                _panel_instance.deleteLater()
            except Exception:
                pass
        _panel_instance = ShootPanel()
    _panel_instance.show()
    _panel_instance.raise_()
    _panel_instance.activateWindow()
