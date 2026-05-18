"""Compact Maya panel for the Shoot viewport-to-image flow."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Callable, Optional

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

from shoot.capture.viewport import (
    CameraState,
    Snapshot,
    describe_camera_delta,
    get_camera_state,
    snapshot_active_view,
)
from shoot.comfy.downloader import (
    MODELS_ALL,
    MODELS_BY_KEY,
    download_model,
    model_present,
)
from shoot.comfy.manager import ComfyManager
from shoot.inference.comfy import (
    MODE_FLUX2_DEV,
    MODE_KLEIN,
    MODE_MULTIANGLE,
    MODES_ORDERED,
    ShotRequest,
    generate,
)

SHOOT_PANEL_VERSION = "v12-expand-preview-2026-05-18"
print(f"[shoot.ui.shoot_panel] loaded {SHOOT_PANEL_VERSION}")


# ── Design tokens ─────────────────────────────────────────────────────────────
# Strictly monochromatic. Paper text over ink, opacity ladder for hierarchy.

PAPER       = "#F3F1EE"
INK         = "#0C0E11"

FG_1 = "rgba(243, 241, 238, 255)"           # primary text
FG_2 = "rgba(243, 241, 238, 217)"           # body  (0.85)
FG_3 = "rgba(243, 241, 238, 166)"           # synopsis (0.65)
FG_4 = "rgba(243, 241, 238, 115)"           # dimmed (0.45)
FG_5 = "rgba(243, 241, 238, 128)"           # labels (0.50) — bumped for readability
FG_6 = "rgba(243, 241, 238, 102)"           # resting (0.40)
FG_7 = "rgba(243, 241, 238,  76)"           # empty state (0.30)

RULE        = "rgba(243, 241, 238,  46)"    # 0.18
RULE_SOFT   = "rgba(243, 241, 238,  30)"    # 0.12

PANEL_QSS = f"""
* {{
    font-family: "Consolas", "Cascadia Mono", "SF Mono", "Menlo", monospace;
    font-size: 13px;
    color: {FG_1};
    letter-spacing: 0.3px;
}}

QWidget#shootPanel {{
    background: {INK};
}}

QTabWidget::pane {{
    border: 0;
    border-top: 1px solid {RULE};
    background: {INK};
    margin-top: 0;
}}
QTabBar::tab {{
    background: transparent;
    color: {FG_6};
    padding: 10px 22px;
    border: 0;
    border-bottom: 1px solid transparent;
    text-transform: uppercase;
    letter-spacing: 1.4px;
    font-size: 12px;
}}
QTabBar::tab:hover    {{ color: {FG_2}; }}
QTabBar::tab:selected {{ color: {FG_1}; border-bottom: 1px solid {FG_1}; }}

QLabel {{
    background: transparent;
    color: {FG_2};
}}
QLabel[role="label"] {{
    color: {FG_5};
    text-transform: uppercase;
    letter-spacing: 1.6px;
    font-size: 11px;
}}
QLabel[role="sublabel"] {{
    color: {FG_5};
    text-transform: uppercase;
    letter-spacing: 1.8px;
    font-size: 10px;
}}
QLabel[role="title"] {{
    color: {FG_1};
    font-size: 14px;
    letter-spacing: 0.6px;
}}
QLabel[role="meta"] {{
    color: {FG_5};
    text-transform: uppercase;
    letter-spacing: 1.4px;
    font-size: 11px;
}}

QPushButton {{
    background: transparent;
    color: {FG_1};
    border: 1px solid {RULE};
    border-radius: 0;
    padding: 8px 18px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-size: 11.5px;
}}
QPushButton:hover    {{ border-color: {FG_2}; color: {FG_1}; }}
QPushButton:pressed  {{ background: rgba(243, 241, 238, 18); }}
QPushButton:disabled {{ color: {FG_7}; border-color: {RULE_SOFT}; }}
QPushButton:default  {{ border-color: {FG_2}; }}

/* Kill button — bracketed label, hairline border, no chromatic accent.
   The brackets in the visible label do the visual work of warning. */
QPushButton[role="kill"] {{
    color: {FG_2};
    border-color: {FG_5};
}}
QPushButton[role="kill"]:hover {{
    color: {INK};
    background: {PAPER};
    border-color: {PAPER};
}}
QPushButton[role="kill"]:disabled {{
    color: {FG_7};
    border-color: {RULE_SOFT};
    background: transparent;
}}

QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background: transparent;
    color: {FG_1};
    border: 0;
    border-bottom: 1px solid {RULE};
    border-radius: 0;
    padding: 8px 6px;
    font-size: 13px;
    selection-background-color: rgba(243, 241, 238, 60);
    selection-color: {INK};
}}
QPlainTextEdit {{
    border: 1px solid {RULE};
    padding: 12px 14px;
    line-height: 1.7;
    font-size: 14px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {FG_2};
}}

QComboBox::drop-down {{ border: 0; width: 18px; }}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid {FG_5};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {INK};
    color: {FG_1};
    border: 1px solid {RULE};
    selection-background-color: rgba(243, 241, 238, 24);
    padding: 4px 0;
}}

QSpinBox::up-button, QSpinBox::down-button {{
    width: 0;
    height: 0;
    border: 0;
}}

QCheckBox {{
    color: {FG_5};
    text-transform: uppercase;
    letter-spacing: 1.4px;
    font-size: 11px;
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 13px;
    height: 13px;
    border: 1px solid {RULE};
    border-radius: 0;
    background: transparent;
}}
QCheckBox::indicator:checked {{
    background: {PAPER};
    border-color: {PAPER};
}}

QProgressBar {{
    background: transparent;
    border: 1px solid {RULE};
    border-radius: 0;
    height: 8px;
    text-align: center;
    color: {FG_5};
    font-size: 10px;
}}
QProgressBar::chunk {{ background: {PAPER}; }}

QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {RULE};
    min-height: 24px;
    border-radius: 0;
}}
QScrollBar::handle:vertical:hover {{ background: {FG_5}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QToolTip {{
    background: {INK};
    color: {FG_2};
    border: 1px solid {RULE};
    padding: 6px 10px;
    font-size: 11.5px;
    letter-spacing: 0.3px;
}}

QFrame[role="rule"] {{
    background: {RULE};
    max-height: 1px;
    min-height: 1px;
    border: 0;
}}
"""


class _ImageView(QtWidgets.QLabel):
    """A square-ish image preview that scales to fit its widget bounds.

    When constructed with ``clickable=True``, emits ``expand_requested`` on
    a left click while an image is loaded — the panel uses this to open
    the result at full-screen scale for inspection before save.
    """

    expand_requested = QtCore.Signal()

    def __init__(self, label: str, parent=None, clickable: bool = False):
        super().__init__(parent)
        self._empty_label = label.upper()
        self._pixmap: Optional[QtGui.QPixmap] = None
        self._clickable = clickable
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(320, 220)
        self.setText(self._empty_label)
        if clickable:
            self.setToolTip("Click to view at full size")
        self.setStyleSheet(
            "QLabel {"
            f" background: transparent;"
            f" border: 1px solid {RULE};"
            f" border-radius: 0;"
            f" color: {FG_7};"
            f" letter-spacing: 1.6px;"
            f" font-size: 11px;"
            "}"
        )

    def set_png(self, data: bytes) -> None:
        image = QtGui.QImage.fromData(data, "PNG")
        if image.isNull():
            raise RuntimeError("Could not display generated PNG.")
        self._pixmap = QtGui.QPixmap.fromImage(image)
        self._update_display()
        if self._clickable:
            self.setCursor(QtCore.Qt.PointingHandCursor)

    def clear_image(self) -> None:
        self._pixmap = None
        self.clear()
        self.setText(self._empty_label)
        self.setAlignment(QtCore.Qt.AlignCenter)
        if self._clickable:
            self.unsetCursor()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            self._clickable
            and self._pixmap is not None
            and event.button() == QtCore.Qt.LeftButton
        ):
            self.expand_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_display()

    def _update_display(self) -> None:
        if not self._pixmap:
            return
        self.setPixmap(
            self._pixmap.scaled(
                self.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )

    def pixmap_copy(self) -> Optional[QtGui.QPixmap]:
        """Return the original, full-resolution pixmap (or None if empty)."""
        return self._pixmap


class _ImagePreviewDialog(QtWidgets.QDialog):
    """Full-screen-ish preview of a PNG. Click or Escape dismisses it.

    Used by the Shoot panel so the user can inspect the generated image
    at native fit-to-screen scale before deciding whether to save.
    """

    def __init__(self, pixmap: QtGui.QPixmap, parent=None):
        super().__init__(parent)
        self.setObjectName("shootPreviewDialog")
        self.setWindowTitle("Preview")
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.WindowCloseButtonHint)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog#shootPreviewDialog {{ background: {INK}; }}"
            f"QLabel {{ background: transparent; color: {FG_5};"
            "  letter-spacing: 1.6px; font-size: 10px; }"
        )

        self._pixmap = pixmap

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)

        self._view = QtWidgets.QLabel()
        self._view.setAlignment(QtCore.Qt.AlignCenter)
        self._view.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )
        layout.addWidget(self._view, 1)

        hint = QtWidgets.QLabel(
            f"{pixmap.width()} × {pixmap.height()} · CLICK OR ESC TO CLOSE"
        )
        hint.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(hint)

        # Size to ~90% of the available screen so window chrome + image
        # both fit comfortably. The label scales the pixmap on every resize.
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.resize(int(avail.width() * 0.9), int(avail.height() * 0.9))
        self._update_view()

    def _update_view(self) -> None:
        if self._pixmap.isNull():
            return
        self._view.setPixmap(
            self._pixmap.scaled(
                self._view.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_view()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (
            QtCore.Qt.Key_Escape,
            QtCore.Qt.Key_Return,
            QtCore.Qt.Key_Enter,
        ):
            self.accept()
            return
        super().keyPressEvent(event)


class _TaskSignals(QtCore.QObject):
    status = QtCore.Signal(str)
    result = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    finished = QtCore.Signal()


class _Task(QtCore.QRunnable):
    def __init__(self, fn: Callable[[_TaskSignals], object]):
        super().__init__()
        self.fn = fn
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            self.signals.result.emit(self.fn(self.signals))
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.finished.emit()


class _ModelRow(QtWidgets.QWidget):
    download_requested = QtCore.Signal(str)

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setStyleSheet(f"_ModelRow {{ border-top: 1px solid {RULE_SOFT}; }}")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 10)
        layout.setSpacing(14)

        self.name = QtWidgets.QLabel(spec.display_name.upper())
        self.name.setProperty("role", "meta")
        # No minimum width — the name column shrinks first if the panel is narrow.
        self.name.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored,
            QtWidgets.QSizePolicy.Fixed,
        )
        self.name.setMinimumWidth(0)
        self.name.setFixedHeight(22)
        self.state = QtWidgets.QLabel("CHECKING")
        self.state.setProperty("role", "sublabel")
        self.state.setFixedWidth(92)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setFixedWidth(140)
        self.size = QtWidgets.QLabel(spec.size_label.upper())
        self.size.setProperty("role", "sublabel")
        self.size.setFixedWidth(62)
        self.button = QtWidgets.QPushButton("Download")
        self.button.setFixedWidth(110)
        self.button.clicked.connect(lambda: self.download_requested.emit(spec.key))

        layout.addWidget(self.name, 1)
        layout.addWidget(self.state)
        layout.addWidget(self.progress)
        layout.addWidget(self.size)
        layout.addWidget(self.button)

    def _set_state(self, text: str, color: str) -> None:
        self.state.setText(text.upper())
        self.state.setStyleSheet(
            f"color: {color};"
            "text-transform: uppercase;"
            "letter-spacing: 1.5px;"
            "font-size: 7.5px;"
        )

    def set_ready(self, ready: bool) -> None:
        self.progress.setVisible(False)
        self.button.setEnabled(not ready)
        if ready:
            self._set_state("Ready", FG_1)
            self.button.setText("Ready")
        else:
            self._set_state("Missing", FG_5)
            self.button.setText("Download")

    def set_busy(self, message: str = "Downloading") -> None:
        self._set_state(message, FG_2)
        self.progress.setVisible(True)
        self.button.setEnabled(False)

    def set_progress(self, done: int, total: int) -> None:
        self.progress.setVisible(True)
        if total:
            self.progress.setValue(max(0, min(100, int(done * 100 / total))))


class ShootPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(None)
        self.setObjectName("shootPanel")
        self.setWindowTitle("Shoot")
        self.setWindowFlags(QtCore.Qt.Window)
        # Lock a sane minimum so dragging the resize handle below this
        # can't trigger a layout fight, and a sane starting size so the
        # initial open doesn't snap large from a content-driven sizeHint.
        self.setMinimumSize(880, 560)
        self.resize(1080, 720)
        # Refuse layout-driven autosizing; we manage our own bounds.
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred,
        )
        self.setStyleSheet(PANEL_QSS)

        self._pool = QtCore.QThreadPool.globalInstance()
        self._manager = ComfyManager()
        self._last_snapshot: Optional[Snapshot] = None
        self._last_snapshot_camera: Optional[CameraState] = None
        self._last_result: Optional[bytes] = None
        self._downloading: set[str] = set()
        self._download_queue: list[str] = []
        self._tasks: set[_Task] = set()
        self._busy = False
        # Flag the running generate() task checks each poll. Kill flips it,
        # which causes wait_for_image to raise and unstick the timer.
        self._cancel_generation = False
        # Log-tail state — track last byte read so we only append new content
        # each poll. If the file shrinks (server restart truncates the log),
        # we reset to 0 in _tail_log_tick.
        self._log_position: int = 0

        # ── Multi-angle anchor state ───────────────────────────────────────
        # The first successful generation in the session becomes the anchor:
        # its result PNG is reused as the reference for every Multi-Angle gen,
        # and its camera pose at snap time is the pivot the camera-delta is
        # measured against. Cleared by the user via "Clear Anchor".
        self._anchor_png:    Optional[bytes]       = None
        self._anchor_camera: Optional[CameraState] = None
        # Current selected mode (one of MODE_KLEIN / MODE_FLUX2_DEV / MODE_MULTIANGLE).
        self._mode: str = MODE_KLEIN
        # Live-derived prompt for Multi-Angle mode, recomputed every status tick.
        self._derived_prompt: str = ""

        self._build_ui()
        self._load_settings()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(3000)
        self._refresh_status()

        # First-launch wizard runs after the panel is painted so it parents
        # correctly. No-op once the user has been through it.
        QtCore.QTimer.singleShot(0, self._maybe_show_onboarding)

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_shoot_tab()
        self._build_models_tab()
        self._build_log_tab()

        # Footer credit — plain text (rich-text + RichText format have
        # unstable width hints in Qt and were causing the window to grow
        # on every move/resize event).
        footer_rule = QtWidgets.QFrame()
        footer_rule.setProperty("role", "rule")
        root.addWidget(footer_rule)
        credit = QtWidgets.QLabel(
            "CREATED BY MMEJIA.XYZ  —  A CREATIVE TECHNOLOGIST BASED IN BERLIN"
        )
        credit.setProperty("role", "sublabel")
        credit.setStyleSheet(
            f"color: {FG_5};"
            "padding: 10px 12px 4px 12px;"
            "letter-spacing: 1.8px;"
            "font-size: 10px;"
        )
        # Crucial: tell the layout this label can shrink horizontally and
        # has a fixed vertical footprint — no height-for-width feedback.
        credit.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored,
            QtWidgets.QSizePolicy.Fixed,
        )
        credit.setMinimumWidth(0)
        credit.setFixedHeight(28)
        root.addWidget(credit)

    def _build_shoot_tab(self) -> None:
        page = QtWidgets.QWidget()
        self.tabs.addTab(page, "SHOOT")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        # Masthead — plugin name on the left, project sub-label on the right.
        masthead = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("SHOOT")
        title.setStyleSheet(
            f"color: {FG_1}; font-size: 16px; letter-spacing: 2px;"
        )
        sub = QtWidgets.QLabel("— MAYA 2027 · VIEWPORT TO STILL")
        sub.setProperty("role", "label")
        sub.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored,
            QtWidgets.QSizePolicy.Fixed,
        )
        sub.setMinimumWidth(0)
        masthead.addWidget(title)
        masthead.addWidget(sub, 1)
        layout.addLayout(masthead)

        rule = QtWidgets.QFrame()
        rule.setProperty("role", "rule")
        rule.setFrameShape(QtWidgets.QFrame.HLine)
        layout.addWidget(rule)

        # ComfyUI status bar (acts like a wall-label data row)
        header = QtWidgets.QHBoxLayout()
        self.comfy_dot = QtWidgets.QLabel("·")
        self.comfy_dot.setFixedWidth(14)
        self.comfy_label = QtWidgets.QLabel("CHECKING SERVER")
        self.comfy_label.setProperty("role", "meta")
        self.comfy_label.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored,
            QtWidgets.QSizePolicy.Fixed,
        )
        self.comfy_label.setMinimumWidth(0)
        self.comfy_label.setFixedHeight(22)
        self.start_btn = QtWidgets.QPushButton("Start Server")
        self.start_btn.clicked.connect(self._start_comfy)
        self.kill_btn = QtWidgets.QPushButton("Kill Server")
        self.kill_btn.setProperty("role", "kill")
        self.kill_btn.setToolTip(
            "Force-kill the ComfyUI process listening on the configured port.\n"
            "Available during a running generation and for servers Shoot did not start."
        )
        self.kill_btn.clicked.connect(self._kill_comfy)
        header.addWidget(self.comfy_dot)
        header.addWidget(self.comfy_label, 1)
        header.addWidget(self.start_btn)
        header.addWidget(self.kill_btn)
        layout.addLayout(header)

        # ── Mode row ──────────────────────────────────────────────────────
        # Drives which workflow generate() builds. The Turbo checkbox only
        # affects Flux 2 dev and is hidden in the other two modes.
        mode_row = QtWidgets.QHBoxLayout()
        mode_label = QtWidgets.QLabel("MODE")
        mode_label.setProperty("role", "sublabel")
        mode_label.setFixedWidth(54)
        self.mode = QtWidgets.QComboBox()
        for key, label in MODES_ORDERED:
            self.mode.addItem(label, key)
        self.mode.currentIndexChanged.connect(self._on_mode_changed)
        self.turbo_lora = QtWidgets.QCheckBox("TURBO LORA · 8 STEPS")
        self.turbo_lora.setChecked(True)
        self.turbo_lora.setToolTip(
            "Flux 2 dev only — 8-step inference via the Turbo LoRA.\n"
            "Uncheck for full 20-step quality (~2.5× slower)."
        )
        self.turbo_lora.toggled.connect(lambda _checked: self._save_mode_settings())
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.mode, 1)
        mode_row.addWidget(self.turbo_lora)
        layout.addLayout(mode_row)

        # ── Anchor row (Multi-Angle only) ─────────────────────────────────
        # First successful generation in the session populates the anchor:
        # its result PNG becomes the reference for every Multi-Angle gen and
        # its camera pose is the pivot for camera-delta encoding.
        self.anchor_row = QtWidgets.QWidget()
        anchor_row_layout = QtWidgets.QHBoxLayout(self.anchor_row)
        anchor_row_layout.setContentsMargins(0, 0, 0, 0)
        anchor_label = QtWidgets.QLabel("ANCHOR")
        anchor_label.setProperty("role", "sublabel")
        anchor_label.setFixedWidth(54)
        self.anchor_status = QtWidgets.QLabel("NONE — RUN A KLEIN OR FLUX 2 DEV GENERATION FIRST")
        self.anchor_status.setProperty("role", "meta")
        self.anchor_status.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored,
            QtWidgets.QSizePolicy.Fixed,
        )
        self.anchor_status.setMinimumWidth(0)
        self.anchor_status.setFixedHeight(22)
        self.clear_anchor_btn = QtWidgets.QPushButton("Clear Anchor")
        self.clear_anchor_btn.clicked.connect(self._clear_anchor)
        anchor_row_layout.addWidget(anchor_label)
        anchor_row_layout.addWidget(self.anchor_status, 1)
        anchor_row_layout.addWidget(self.clear_anchor_btn)
        layout.addWidget(self.anchor_row)
        self.anchor_row.setVisible(False)  # mode == Multi-Angle only

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(28)
        layout.addLayout(body, 1)

        controls = QtWidgets.QVBoxLayout()
        controls.setSpacing(10)
        body.addLayout(controls, 0)

        prompt_label = QtWidgets.QLabel("PROMPT")
        prompt_label.setProperty("role", "label")
        controls.addWidget(prompt_label)
        self.prompt = QtWidgets.QPlainTextEdit()
        self.prompt.setPlaceholderText(
            "Third-person · archival · no marketing verbs."
        )
        self.prompt.setMinimumWidth(320)
        self.prompt.setMinimumHeight(120)
        controls.addWidget(self.prompt)

        # Derived-prompt preview — only meaningful in Multi-Angle mode where
        # the camera-delta replaces user text. Updates every status tick.
        self.derived_prompt_container = QtWidgets.QWidget()
        derived_layout = QtWidgets.QVBoxLayout(self.derived_prompt_container)
        derived_layout.setContentsMargins(0, 4, 0, 0)
        derived_layout.setSpacing(4)
        derived_label = QtWidgets.QLabel("PROMPT (DERIVED FROM CAMERA)")
        derived_label.setProperty("role", "sublabel")
        self.derived_prompt_view = QtWidgets.QLabel("—")
        self.derived_prompt_view.setStyleSheet(
            f"color: {FG_2};"
            f"border: 1px solid {RULE};"
            "padding: 8px 10px;"
            "font-size: 12px;"
            "letter-spacing: 0.3px;"
        )
        self.derived_prompt_view.setWordWrap(True)
        self.derived_prompt_view.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        derived_layout.addWidget(derived_label)
        derived_layout.addWidget(self.derived_prompt_view)
        controls.addWidget(self.derived_prompt_container)
        self.derived_prompt_container.setVisible(False)

        prompt_buttons = QtWidgets.QHBoxLayout()
        self.optimize_btn = QtWidgets.QPushButton("Optimize")
        self.optimize_btn.clicked.connect(self._optimize_prompt)
        self.clear_prompt_btn = QtWidgets.QPushButton("Clear")
        self.clear_prompt_btn.clicked.connect(self.prompt.clear)
        prompt_buttons.addWidget(self.optimize_btn)
        prompt_buttons.addWidget(self.clear_prompt_btn)
        controls.addLayout(prompt_buttons)

        # Settings row — labels styled as data-row labels
        settings_rule = QtWidgets.QFrame()
        settings_rule.setProperty("role", "rule")
        controls.addWidget(settings_rule)

        settings = QtWidgets.QFormLayout()
        settings.setHorizontalSpacing(20)
        settings.setVerticalSpacing(8)
        settings.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        aspect_label = QtWidgets.QLabel("ASPECT")
        aspect_label.setProperty("role", "sublabel")
        self.aspect = QtWidgets.QComboBox()
        self.aspect.addItems(["16:9", "4:3", "1:1", "9:16"])
        settings.addRow(aspect_label, self.aspect)

        seed_label = QtWidgets.QLabel("SEED")
        seed_label.setProperty("role", "sublabel")
        seed_row = QtWidgets.QHBoxLayout()
        seed_row.setSpacing(6)
        self.lock_seed = QtWidgets.QCheckBox("LOCK")
        self.seed = QtWidgets.QSpinBox()
        self.seed.setRange(0, 2147483647)
        self.seed.setValue(random.randint(0, 2147483647))
        self.random_seed_btn = QtWidgets.QPushButton("Random")
        self.random_seed_btn.clicked.connect(self._randomize_seed)
        seed_row.addWidget(self.lock_seed)
        seed_row.addWidget(self.seed, 1)
        seed_row.addWidget(self.random_seed_btn)
        seed_widget = QtWidgets.QWidget()
        seed_widget.setLayout(seed_row)
        settings.addRow(seed_label, seed_widget)
        controls.addLayout(settings)

        actions_rule = QtWidgets.QFrame()
        actions_rule.setProperty("role", "rule")
        controls.addWidget(actions_rule)

        self.snap_btn = QtWidgets.QPushButton("Snap Viewport")
        self.snap_btn.clicked.connect(self._snap_viewport)
        controls.addWidget(self.snap_btn)

        self.shoot_btn = QtWidgets.QPushButton("Generate")
        self.shoot_btn.setDefault(True)
        self.shoot_btn.clicked.connect(self._generate_image)
        controls.addWidget(self.shoot_btn)

        self.save_btn = QtWidgets.QPushButton("Save Result")
        self.save_btn.clicked.connect(self._save_result)
        self.save_btn.setEnabled(False)
        controls.addWidget(self.save_btn)
        controls.addStretch()

        # Status label — single line, elided if too long. Wrapping triggers
        # heightForWidth which causes the resize-loop bug.
        self.status = QtWidgets.QLabel("")
        self.status.setProperty("role", "meta")
        self.status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.status.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored,
            QtWidgets.QSizePolicy.Fixed,
        )
        self.status.setMinimumWidth(0)
        self.status.setFixedHeight(20)
        controls.addWidget(self.status)

        # Right: previews — each preceded by a sublabel and a hairline
        previews = QtWidgets.QVBoxLayout()
        previews.setSpacing(6)
        body.addLayout(previews, 1)

        snap_label = QtWidgets.QLabel("VIEWPORT SNAP")
        snap_label.setProperty("role", "sublabel")
        previews.addWidget(snap_label)
        snap_rule = QtWidgets.QFrame()
        snap_rule.setProperty("role", "rule")
        previews.addWidget(snap_rule)
        self.reference_view = _ImageView("Snap the viewport to begin")
        previews.addWidget(self.reference_view, 1)

        result_label = QtWidgets.QLabel("RESULT  ·  CLICK TO EXPAND")
        result_label.setProperty("role", "sublabel")
        previews.addWidget(result_label)
        result_rule = QtWidgets.QFrame()
        result_rule.setProperty("role", "rule")
        previews.addWidget(result_rule)
        self.result_view = _ImageView("Generated image appears here", clickable=True)
        self.result_view.expand_requested.connect(self._show_result_fullsize)
        previews.addWidget(self.result_view, 1)

    def _build_models_tab(self) -> None:
        page = QtWidgets.QWidget()
        self.tabs.addTab(page, "MODELS")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        path_row = QtWidgets.QHBoxLayout()
        path_row.setSpacing(14)
        comfy_label = QtWidgets.QLabel("COMFYUI")
        comfy_label.setProperty("role", "sublabel")
        comfy_label.setFixedWidth(96)
        self.comfy_path = QtWidgets.QLineEdit(str(self._manager.install_dir))
        self.comfy_path.editingFinished.connect(self._save_comfy_path)
        path_row.addWidget(comfy_label)
        path_row.addWidget(self.comfy_path, 1)
        layout.addLayout(path_row)

        token_row = QtWidgets.QHBoxLayout()
        token_row.setSpacing(14)
        token_label = QtWidgets.QLabel("HF TOKEN")
        token_label.setProperty("role", "sublabel")
        token_label.setFixedWidth(96)
        self.hf_token = QtWidgets.QLineEdit()
        self.hf_token.setEchoMode(QtWidgets.QLineEdit.Password)
        self.hf_token.setPlaceholderText("Required for gated weights")
        self.save_token_btn = QtWidgets.QPushButton("Save")
        self.save_token_btn.clicked.connect(self._save_hf_token)
        token_row.addWidget(token_label)
        token_row.addWidget(self.hf_token, 1)
        token_row.addWidget(self.save_token_btn)
        layout.addLayout(token_row)

        rule = QtWidgets.QFrame()
        rule.setProperty("role", "rule")
        layout.addWidget(rule)

        # Scroll area for the model rows — the catalogue covers Klein, Flux 2
        # dev, and Qwen multi-angle (~11 rows total) and would overflow a
        # fixed-height tab without scrolling.
        models_scroll = QtWidgets.QScrollArea()
        models_scroll.setWidgetResizable(True)
        models_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        models_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        models_inner = QtWidgets.QWidget()
        models_layout = QtWidgets.QVBoxLayout(models_inner)
        models_layout.setContentsMargins(0, 0, 0, 0)
        models_layout.setSpacing(0)

        self.model_rows = {}
        for spec in MODELS_ALL:
            row = _ModelRow(spec)
            row.download_requested.connect(self._download_model)
            self.model_rows[spec.key] = row
            models_layout.addWidget(row)

        models_layout.addStretch()
        models_scroll.setWidget(models_inner)
        layout.addWidget(models_scroll, 1)

        self.download_all_btn = QtWidgets.QPushButton("Download All Missing")
        self.download_all_btn.clicked.connect(self._download_all_missing)
        layout.addWidget(self.download_all_btn)

    # ── Log tab ───────────────────────────────────────────────────────────────

    def _build_log_tab(self) -> None:
        """Live terminal-style view of ComfyUI's stdout/stderr.

        Tails the log file written by the manager (%TEMP%/shoot_comfy_<port>.log).
        We poll every 500 ms and only read incremental new bytes — if the
        file shrinks (next `start()` truncates it), reset to byte 0.
        """
        page = QtWidgets.QWidget()
        self.tabs.addTab(page, "LOG")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)

        header_row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("COMFYUI · STDOUT + STDERR")
        title.setProperty("role", "sublabel")
        self.log_path_label = QtWidgets.QLabel(str(self._manager.log_path()))
        self.log_path_label.setProperty("role", "meta")
        self.log_path_label.setStyleSheet(
            f"color: {FG_5}; font-size: 10px;"
        )
        self.log_path_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse
        )
        # Long temp paths must not enlarge the panel.
        self.log_path_label.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored,
            QtWidgets.QSizePolicy.Fixed,
        )
        self.log_path_label.setMinimumWidth(0)

        self.log_clear_btn = QtWidgets.QPushButton("Clear")
        self.log_clear_btn.clicked.connect(self._clear_log_view)
        self.log_open_btn = QtWidgets.QPushButton("Open File")
        self.log_open_btn.clicked.connect(self._open_log_file)
        self.log_pause_btn = QtWidgets.QPushButton("Pause Tail")
        self.log_pause_btn.setCheckable(True)
        self.log_pause_btn.toggled.connect(self._toggle_log_pause)

        header_row.addWidget(title)
        header_row.addStretch(1)
        header_row.addWidget(self.log_pause_btn)
        header_row.addWidget(self.log_clear_btn)
        header_row.addWidget(self.log_open_btn)
        layout.addLayout(header_row)

        path_row = QtWidgets.QHBoxLayout()
        path_label = QtWidgets.QLabel("FILE")
        path_label.setProperty("role", "sublabel")
        path_label.setFixedWidth(48)
        path_row.addWidget(path_label)
        path_row.addWidget(self.log_path_label, 1)
        layout.addLayout(path_row)

        rule = QtWidgets.QFrame()
        rule.setProperty("role", "rule")
        layout.addWidget(rule)

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        # Cap memory: keep last ~10k lines.
        self.log_view.setMaximumBlockCount(10000)
        self.log_view.setStyleSheet(
            f"QPlainTextEdit {{"
            f" background: {INK};"
            f" color: {FG_2};"
            f" border: 1px solid {RULE};"
            f" border-radius: 0;"
            f" padding: 12px 14px;"
            f" font-family: 'Consolas', 'Cascadia Mono', monospace;"
            f" font-size: 12px;"
            f" line-height: 1.5;"
            f" letter-spacing: 0;"
            f"}}"
        )
        layout.addWidget(self.log_view, 1)

        # Tail timer — independent of the status refresh timer.
        self._log_timer = QtCore.QTimer(self)
        self._log_timer.timeout.connect(self._tail_log_tick)
        self._log_timer.start(500)

    def _tail_log_tick(self) -> None:
        if self.log_pause_btn.isChecked():
            return
        path = self._manager.log_path()
        try:
            if not path.exists():
                return
            size = path.stat().st_size
            # File was truncated (server restart) — reset our cursor.
            if size < self._log_position:
                self._log_position = 0
                self.log_view.clear()
            if size == self._log_position:
                return
            with open(path, "rb") as f:
                f.seek(self._log_position)
                chunk = f.read(size - self._log_position)
                self._log_position = size
        except Exception:
            return

        if not chunk:
            return

        # Stay pinned to bottom only if user is already at the bottom — so
        # they can scroll up and read older lines without being yanked back.
        scrollbar = self.log_view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        text = chunk.decode("utf-8", errors="replace").rstrip("\r\n")
        self.log_view.appendPlainText(text)
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _clear_log_view(self) -> None:
        self.log_view.clear()
        # Don't reset _log_position — we still want incremental tailing,
        # we just hid what's already on disk.

    def _open_log_file(self) -> None:
        path = str(self._manager.log_path())
        url = QtCore.QUrl.fromLocalFile(path)
        QtGui.QDesktopServices.openUrl(url)

    def _toggle_log_pause(self, paused: bool) -> None:
        self.log_pause_btn.setText("Resume Tail" if paused else "Pause Tail")

    # ── Busy / status ─────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in (
            self.start_btn,
            self.snap_btn, self.shoot_btn, self.optimize_btn,
        ):
            button.setEnabled(not busy)
        # Kill button is intentionally NOT disabled during busy — the user
        # must be able to kill a runaway generation at any moment.

    def _set_generation_controls_enabled(self, enabled: bool) -> None:
        self.snap_btn.setEnabled(enabled)
        self.shoot_btn.setEnabled(enabled)
        self.optimize_btn.setEnabled(enabled)

    def _start_task(self, worker: _Task) -> None:
        self._tasks.add(worker)
        worker.signals.finished.connect(lambda worker=worker: self._tasks.discard(worker))
        self._pool.start(worker)

    def _load_settings(self) -> None:
        try:
            from maya import cmds

            if cmds.optionVar(exists="shoot_prompt"):
                self.prompt.setPlainText(cmds.optionVar(q="shoot_prompt"))
            if cmds.optionVar(exists="shoot_hf_token"):
                self.hf_token.setText(cmds.optionVar(q="shoot_hf_token"))
            if cmds.optionVar(exists="shoot_seed"):
                self.seed.setValue(int(cmds.optionVar(q="shoot_seed")))
            if cmds.optionVar(exists="shoot_lock_seed"):
                self.lock_seed.setChecked(bool(cmds.optionVar(q="shoot_lock_seed")))
            if cmds.optionVar(exists="shoot_mode"):
                stored_mode = cmds.optionVar(q="shoot_mode")
                for i in range(self.mode.count()):
                    if self.mode.itemData(i) == stored_mode:
                        self.mode.setCurrentIndex(i)
                        self._mode = stored_mode
                        break
            if cmds.optionVar(exists="shoot_turbo_lora"):
                self.turbo_lora.setChecked(bool(cmds.optionVar(q="shoot_turbo_lora")))
        except Exception:
            pass
        # Apply visibility/enabled state for the loaded mode.
        self._update_mode_ui()

    def _maybe_show_onboarding(self) -> None:
        try:
            from maya import cmds

            if cmds.optionVar(exists="shoot_onboarded") and cmds.optionVar(q="shoot_onboarded"):
                return
            # Pre-wizard users who already have Comfy + all models configured
            # don't need to see the wizard — silently mark them onboarded.
            from shoot.comfy.downloader import all_present

            if self._manager.is_installed() and all_present(self._manager.install_dir):
                cmds.optionVar(iv=("shoot_onboarded", 1))
                return
        except Exception:
            return

        try:
            from shoot.ui.onboarding import OnboardingWizard
        except Exception as exc:
            print(f"[shoot.ui.shoot_panel] onboarding wizard unavailable: {exc}")
            return

        wizard = OnboardingWizard(parent=self)
        accepted = wizard.exec_() == QtWidgets.QDialog.Accepted
        if accepted:
            try:
                from maya import cmds

                cmds.optionVar(iv=("shoot_onboarded", 1))
            except Exception:
                pass
        self._apply_wizard_settings()

    def _apply_wizard_settings(self) -> None:
        """Pick up any optionVar changes the wizard made (comfy_dir, hf_token)
        and reflect them in the panel widgets + manager."""
        try:
            from maya import cmds

            if cmds.optionVar(exists="shoot_comfy_dir"):
                path = cmds.optionVar(q="shoot_comfy_dir")
                if path:
                    self.comfy_path.setText(path)
                    self._manager = ComfyManager(install_dir=Path(path).expanduser())
            if cmds.optionVar(exists="shoot_hf_token"):
                self.hf_token.setText(cmds.optionVar(q="shoot_hf_token"))
        except Exception:
            pass
        self._refresh_status()

    def _save_prompt_settings(self) -> None:
        try:
            from maya import cmds

            cmds.optionVar(sv=("shoot_prompt", self.prompt.toPlainText()))
            cmds.optionVar(iv=("shoot_seed", self.seed.value()))
            cmds.optionVar(iv=("shoot_lock_seed", int(self.lock_seed.isChecked())))
        except Exception:
            pass

    def _save_mode_settings(self) -> None:
        try:
            from maya import cmds

            cmds.optionVar(sv=("shoot_mode", self._mode))
            cmds.optionVar(iv=("shoot_turbo_lora", int(self.turbo_lora.isChecked())))
        except Exception:
            pass

    def _save_comfy_path(self) -> None:
        path = Path(self.comfy_path.text()).expanduser()
        self._manager = ComfyManager(install_dir=path)
        try:
            from maya import cmds

            cmds.optionVar(sv=("shoot_comfy_dir", str(path)))
        except Exception:
            pass
        self._refresh_status()

    def _save_hf_token(self) -> None:
        try:
            from maya import cmds

            cmds.optionVar(sv=("shoot_hf_token", self.hf_token.text().strip()))
            self.status.setText("HuggingFace token saved.")
        except Exception as exc:
            self.status.setText(f"Could not save token: {exc}")

    def _refresh_status(self) -> None:
        running = self._manager.is_running(timeout=0.2)
        installed = self._manager.is_installed()
        # In-system color: paper at full opacity = running, at 0.30 = idle.
        self.comfy_dot.setStyleSheet(
            f"color: {FG_1};" if running else f"color: {FG_7};"
        )
        self.comfy_label.setText(self._manager.status_text(timeout=0.2).upper())
        self.start_btn.setEnabled(installed and not running and not self._busy)
        # Kill is enabled whenever a process is listening on the port — even
        # mid-generation, and even if Shoot did not start the server.
        self.kill_btn.setEnabled(running)
        self._set_generation_controls_enabled(not self._busy)
        # Multi-Angle mode: update the camera-delta preview every tick so the
        # user can see what prompt will be injected as they orbit.
        if self._mode == MODE_MULTIANGLE:
            self._update_derived_prompt()
        if self.tabs.currentWidget() and self.tabs.tabText(self.tabs.currentIndex()) == "MODELS":
            self._refresh_model_rows()

    def _refresh_model_rows(self) -> None:
        comfy_dir = Path(self.comfy_path.text()).expanduser()
        for row in self.model_rows.values():
            if row.spec.key in self._downloading:
                continue
            row.set_ready(model_present(row.spec, comfy_dir))

    def _start_comfy(self) -> None:
        self._set_busy(True)
        self.status.setText("Starting ComfyUI...")

        def task(signals):
            self._manager.start_and_wait(status_cb=signals.status.emit)
            return None

        worker = _Task(task)
        worker.signals.status.connect(self.status.setText)
        worker.signals.failed.connect(lambda msg: self.status.setText(f"ComfyUI error: {msg}"))
        worker.signals.finished.connect(lambda: (self._set_busy(False), self._refresh_status()))
        self._start_task(worker)

    def _kill_comfy(self) -> None:
        """Force-kill ComfyUI. Allowed at any time, including mid-generation.

        Order matters:
          1. Flip the cancel flag so the in-flight wait_for_image bails
             immediately instead of running 30-min timeout-bound polls.
          2. Kill the server (sync).
          3. Clear busy / status now — don't wait for the worker to wind
             down, the user already pressed Kill, they want the timer gone.
        """
        # 1. Signal any running generation to cancel.
        was_busy = self._busy
        self._cancel_generation = True

        self.status.setText("Killing ComfyUI...")
        QtWidgets.QApplication.processEvents()

        # 2. Kill the server.
        try:
            killed = self._manager.kill()
        except Exception as exc:
            self.status.setText(f"Kill failed: {exc}")
            return

        # 3. Force the panel out of busy state synchronously. The worker
        #    thread will still emit `failed` and `finished` after its next
        #    poll wakes up (within ~3s); those handlers are idempotent.
        if was_busy:
            self._set_busy(False)

        if killed:
            self.status.setText(
                "ComfyUI killed — generation cancelled." if was_busy
                else "ComfyUI killed."
            )
        else:
            self.status.setText("No ComfyUI process found to kill.")
        self._refresh_status()

    def _snap_viewport(self) -> None:
        try:
            snap = snapshot_active_view()
            camera = get_camera_state()
            self._last_snapshot = snap
            self._last_snapshot_camera = camera
            self.reference_view.set_png(snap.png)
            self.status.setText(f"Snapped {snap.camera} — {camera.label}.")
        except Exception as exc:
            self.status.setText(f"Viewport capture failed: {exc}")

    def _randomize_seed(self) -> None:
        self.seed.setValue(random.randint(0, 2147483647))

    def _optimize_prompt(self) -> None:
        text = self.prompt.toPlainText().strip()
        if not text:
            self.status.setText("Write a short prompt first.")
            return
        self.prompt.setPlainText(_optimize_prompt(text))
        self.status.setText("Prompt optimized for image editing.")

    def _generate_image(self) -> None:
        if self._busy:
            return

        if self._mode == MODE_MULTIANGLE:
            req = self._build_multiangle_request()
        else:
            req = self._build_snap_based_request()
        if req is None:
            # _build_*_request already set a status message explaining why.
            return

        self._save_prompt_settings()
        self._cancel_generation = False
        self._set_busy(True)
        self.result_view.clear_image()
        self.save_btn.setEnabled(False)
        if not self.lock_seed.isChecked():
            self._randomize_seed()
            req.seed = self.seed.value()

        def task(signals):
            return generate(
                req,
                status_cb=signals.status.emit,
                cancelled=lambda: self._cancel_generation,
            )

        worker = _Task(task)
        worker.signals.status.connect(self._on_generation_status)
        worker.signals.result.connect(self._show_result)
        worker.signals.failed.connect(self._show_generation_error)
        worker.signals.finished.connect(self._finish_generation)
        self._start_task(worker)

    # ── Request builders ──────────────────────────────────────────────────────

    def _build_snap_based_request(self) -> Optional[ShotRequest]:
        """Build a Klein or Flux-2-dev request from the latest viewport snap."""
        if not self._last_snapshot:
            self.status.setText("Snap the viewport first.")
            return None
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            self.status.setText("Add a prompt before generating.")
            return None
        return ShotRequest(
            prompt=prompt,
            reference_png=self._last_snapshot.png,
            width=self._last_snapshot.width,
            height=self._last_snapshot.height,
            aspect_ratio=self.aspect.currentText(),
            seed=self.seed.value(),
            mode=self._mode,
            use_turbo_lora=self.turbo_lora.isChecked(),
        )

    def _build_multiangle_request(self) -> Optional[ShotRequest]:
        """Build a Qwen multi-angle request from anchor + current camera.

        Reads the live viewport camera on the main thread *here* — the
        worker thread can't call cmds.modelPanel without raising.
        """
        if not self._anchor_png or not self._anchor_camera:
            self.status.setText(
                "No anchor set. Generate a base image in Klein or Flux 2 dev "
                "mode first, then switch to Multi-Angle to orbit."
            )
            return None
        try:
            current_camera = get_camera_state()
        except Exception as exc:
            self.status.setText(f"Could not read camera: {exc}")
            return None
        derived = describe_camera_delta(self._anchor_camera, current_camera)
        self._derived_prompt = derived
        self.derived_prompt_view.setText(derived)
        return ShotRequest(
            prompt=derived,
            reference_png=self._anchor_png,
            seed=self.seed.value(),
            mode=MODE_MULTIANGLE,
        )

    def _on_generation_status(self, msg: str) -> None:
        # Drop late status pings after a cancel so the timer text doesn't
        # overwrite the "ComfyUI killed — generation cancelled" line.
        if self._cancel_generation:
            return
        self.status.setText(msg)

    def _show_result(self, result) -> None:
        self._last_result = result.png
        self.result_view.set_png(result.png)
        self.save_btn.setEnabled(True)
        # The first successful Klein/Flux-2-dev gen in a session becomes the
        # anchor: its PNG is the reference for every subsequent Multi-Angle
        # gen, and its camera pose is the pivot for camera-delta encoding.
        if (
            self._anchor_png is None
            and self._mode in (MODE_KLEIN, MODE_FLUX2_DEV)
            and self._last_snapshot_camera is not None
        ):
            self._anchor_png = result.png
            self._anchor_camera = self._last_snapshot_camera
            self._update_anchor_status()
        self.status.setText("Done.")

    # ── Mode + anchor ─────────────────────────────────────────────────────────

    def _on_mode_changed(self, index: int) -> None:
        data = self.mode.itemData(index)
        if data:
            self._mode = data
            self._save_mode_settings()
        self._update_mode_ui()

    def _update_mode_ui(self) -> None:
        """Show/hide mode-conditional widgets and adjust prompt-field behavior.

        In Multi-Angle mode the user's text is ignored — the camera-delta
        sentence is sent instead. We disable the prompt field there to make
        that visible at a glance.
        """
        is_dev = self._mode == MODE_FLUX2_DEV
        is_multiangle = self._mode == MODE_MULTIANGLE
        self.turbo_lora.setVisible(is_dev)
        self.anchor_row.setVisible(is_multiangle)
        self.derived_prompt_container.setVisible(is_multiangle)
        self.prompt.setEnabled(not is_multiangle)
        if is_multiangle:
            self.prompt.setPlaceholderText(
                "Camera-driven mode — prompt is derived from the viewport."
            )
        else:
            self.prompt.setPlaceholderText(
                "Third-person · archival · no marketing verbs."
            )
        self._update_derived_prompt()
        self._update_anchor_status()

    def _update_derived_prompt(self) -> None:
        """Recompute the camera-delta sentence and write it to the preview."""
        if self._mode != MODE_MULTIANGLE:
            return
        if not self._anchor_camera:
            self.derived_prompt_view.setText("—")
            return
        try:
            current = get_camera_state()
        except Exception:
            return
        self._derived_prompt = describe_camera_delta(self._anchor_camera, current)
        self.derived_prompt_view.setText(self._derived_prompt)

    def _update_anchor_status(self) -> None:
        if self._anchor_camera is None:
            self.anchor_status.setText(
                "NONE — RUN A KLEIN OR FLUX 2 DEV GENERATION FIRST"
            )
            self.clear_anchor_btn.setEnabled(False)
        else:
            cam = self._anchor_camera
            self.anchor_status.setText(
                f"SET · {cam.label.upper()}  ·  "
                f"H {cam.h_deg:6.1f}°   V {cam.v_deg:5.1f}°   D {cam.distance:6.2f}"
            )
            self.clear_anchor_btn.setEnabled(True)

    def _clear_anchor(self) -> None:
        self._anchor_png = None
        self._anchor_camera = None
        self._derived_prompt = ""
        self._update_anchor_status()
        self._update_derived_prompt()
        self.status.setText("Anchor cleared. Next Klein/Flux 2 dev gen will set a new anchor.")

    def _show_generation_error(self, msg: str) -> None:
        # If the user explicitly cancelled, don't overwrite the
        # "ComfyUI killed" status with a noisy connection-lost message.
        if self._cancel_generation:
            return
        self.status.setText(f"Generation failed: {msg}")

    def _finish_generation(self) -> None:
        self._set_busy(False)
        self._cancel_generation = False
        self._refresh_status()

    def _show_result_fullsize(self) -> None:
        """Open the current result image at fit-to-screen scale.

        Triggered by left-clicking the RESULT preview thumbnail. The
        dialog dismisses on click or Escape. Snap is intentionally not
        clickable — the user can re-snap in one click.
        """
        pixmap = self.result_view.pixmap_copy()
        if pixmap is None or pixmap.isNull():
            return
        dialog = _ImagePreviewDialog(pixmap, parent=self)
        dialog.exec_()

    def _save_result(self) -> None:
        if not self._last_result:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save generated image",
            "shoot_output.png",
            "PNG Images (*.png)",
        )
        if not path:
            return
        with open(path, "wb") as fh:
            fh.write(self._last_result)
        self.status.setText(f"Saved {path}")

    def _download_all_missing(self) -> None:
        comfy_dir = Path(self.comfy_path.text()).expanduser()
        self._download_queue = [
            spec.key for spec in MODELS_ALL if not model_present(spec, comfy_dir)
        ]
        if not self._download_queue:
            self.status.setText("All required models are ready.")
            return
        self._download_next_queued_model()

    def _download_next_queued_model(self) -> None:
        if self._download_queue:
            self._download_model(self._download_queue.pop(0))

    def _download_model(self, key: str) -> None:
        spec = MODELS_BY_KEY[key]
        if key in self._downloading:
            return
        comfy_dir = Path(self.comfy_path.text()).expanduser()
        token = self.hf_token.text().strip()
        row = self.model_rows[key]
        self._downloading.add(key)
        row.set_busy()
        self.download_all_btn.setEnabled(False)
        self.status.setText(f"Downloading {spec.display_name}...")

        def task(signals):
            download_model(
                spec,
                comfy_dir,
                hf_token=token,
                progress_cb=lambda done, total: signals.result.emit(("progress", key, done, total)),
                status_cb=signals.status.emit,
            )
            return ("done", key)

        worker = _Task(task)
        worker.signals.status.connect(self.status.setText)
        worker.signals.result.connect(self._handle_download_event)
        worker.signals.failed.connect(self._download_failed)
        worker.signals.finished.connect(
            lambda key=key: self._finish_download(key)
        )
        self._start_task(worker)

    def _finish_download(self, key: str) -> None:
        self._downloading.discard(key)
        self.download_all_btn.setEnabled(True)
        self._refresh_model_rows()
        self._download_next_queued_model()

    def _download_failed(self, msg: str) -> None:
        self._download_queue = []
        self.status.setText(f"Download failed: {msg}")

    def _handle_download_event(self, event) -> None:
        kind = event[0]
        if kind == "progress":
            _, key, done, total = event
            self.model_rows[key].set_progress(int(done), int(total))
        elif kind == "done":
            _, key = event
            self.model_rows[key].set_ready(True)
            self.status.setText("Model download complete.")

    def closeEvent(self, event) -> None:
        self._timer.stop()
        if hasattr(self, "_log_timer"):
            self._log_timer.stop()
        self._save_prompt_settings()
        super().closeEvent(event)


def _optimize_prompt(text: str) -> str:
    prompt = " ".join(text.split())
    lower = prompt.lower()
    additions = []
    if not any(word in lower for word in ("photo", "photoreal", "cinematic", "render")):
        additions.append("photorealistic")
    if "light" not in lower:
        additions.append("natural cinematic lighting")
    if not any(word in lower for word in ("texture", "material", "surface")):
        additions.append("detailed materials and clean surface texture")
    if not any(word in lower for word in ("background", "environment", "scene")):
        additions.append("cohesive background environment")
    additions.append("preserve the subject pose, silhouette, scale, and camera framing")
    return f"{prompt}. " + ", ".join(additions) + "."


def _maya_main_window():
    import maya.OpenMayaUI as omui

    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


_panel_instance = None


def show_panel() -> None:
    global _panel_instance
    if _panel_instance:
        try:
            _panel_instance.close()
        except Exception:
            pass
    _panel_instance = ShootPanel()
    _panel_instance.show()
