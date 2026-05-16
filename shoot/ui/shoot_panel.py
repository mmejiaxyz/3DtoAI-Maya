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

from shoot.capture.viewport import Snapshot, snapshot_active_view, get_viewport_angle
from shoot.comfy.downloader import MODELS, MODELS_BY_KEY, download_model, model_present
from shoot.comfy.manager import ComfyManager
from shoot.inference.comfy import ShotRequest, generate

SHOOT_PANEL_VERSION = "v6-mmejia-design-2026-05-16"
print(f"[shoot.ui.shoot_panel] loaded {SHOOT_PANEL_VERSION}")


# ── Design tokens (mirrors docs/style.css) ────────────────────────────────────

PAPER       = "#F3F1EE"
INK         = "#0C0E11"

FG_1 = "rgba(243, 241, 238, 255)"           # primary text
FG_2 = "rgba(243, 241, 238, 217)"           # body  (0.85)
FG_3 = "rgba(243, 241, 238, 166)"           # synopsis (0.65)
FG_4 = "rgba(243, 241, 238, 115)"           # dimmed (0.45)
FG_5 = "rgba(243, 241, 238, 102)"           # labels (0.40)
FG_6 = "rgba(243, 241, 238,  89)"           # nav resting (0.35)
FG_7 = "rgba(243, 241, 238,  76)"           # empty state (0.30)

RULE        = "rgba(243, 241, 238,  36)"    # 0.14
RULE_SOFT   = "rgba(243, 241, 238,  26)"    # 0.10

ACCENT_KILL = "#5A2A1F"   # burnt sienna — only used for the Kill action

PANEL_QSS = f"""
* {{
    font-family: "Consolas", "Cascadia Mono", "SF Mono", "Menlo", monospace;
    font-size: 10.5px;
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
    padding: 8px 18px;
    border: 0;
    border-bottom: 1px solid transparent;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-size: 10px;
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
    letter-spacing: 1.3px;
    font-size: 9px;
}}
QLabel[role="sublabel"] {{
    color: {FG_5};
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-size: 7.5px;
}}
QLabel[role="title"] {{
    color: {FG_1};
    font-size: 11px;
    letter-spacing: 0.5px;
}}
QLabel[role="meta"] {{
    color: {FG_5};
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-size: 9px;
}}

QPushButton {{
    background: transparent;
    color: {FG_1};
    border: 1px solid {RULE};
    border-radius: 0;
    padding: 6px 14px;
    text-transform: uppercase;
    letter-spacing: 1.4px;
    font-size: 9.5px;
}}
QPushButton:hover    {{ border-color: {FG_2}; color: {FG_1}; }}
QPushButton:pressed  {{ background: rgba(243, 241, 238, 18); }}
QPushButton:disabled {{ color: {FG_7}; border-color: {RULE_SOFT}; }}
QPushButton:default  {{ border-color: {FG_2}; }}

QPushButton[role="kill"] {{
    color: #E6B6A6;
    border-color: {ACCENT_KILL};
}}
QPushButton[role="kill"]:hover {{
    background: {ACCENT_KILL};
    color: {PAPER};
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
    padding: 6px 4px;
    selection-background-color: rgba(243, 241, 238, 60);
    selection-color: {INK};
}}
QPlainTextEdit {{
    border: 1px solid {RULE};
    padding: 8px 10px;
    line-height: 1.7;
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
    letter-spacing: 1.2px;
    font-size: 9px;
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 11px;
    height: 11px;
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
    height: 6px;
    text-align: center;
    color: {FG_5};
    font-size: 8px;
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
    padding: 4px 8px;
    font-size: 9.5px;
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
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._empty_label = label.upper()
        self._pixmap: Optional[QtGui.QPixmap] = None
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(320, 220)
        self.setText(self._empty_label)
        self.setStyleSheet(
            "QLabel {"
            f" background: transparent;"
            f" border: 1px solid {RULE};"
            f" border-radius: 0;"
            f" color: {FG_7};"
            f" letter-spacing: 1.4px;"
            f" font-size: 9px;"
            "}"
        )

    def set_png(self, data: bytes) -> None:
        image = QtGui.QImage.fromData(data, "PNG")
        if image.isNull():
            raise RuntimeError("Could not display generated PNG.")
        self._pixmap = QtGui.QPixmap.fromImage(image)
        self._update_display()

    def clear_image(self) -> None:
        self._pixmap = None
        self.clear()
        self.setText(self._empty_label)
        self.setAlignment(QtCore.Qt.AlignCenter)

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
        self.name.setMinimumWidth(280)
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
        self.resize(980, 640)
        self.setStyleSheet(PANEL_QSS)

        self._pool = QtCore.QThreadPool.globalInstance()
        self._manager = ComfyManager()
        self._last_snapshot: Optional[Snapshot] = None
        self._last_result: Optional[bytes] = None
        self._downloading: set[str] = set()
        self._download_queue: list[str] = []
        self._tasks: set[_Task] = set()
        self._busy = False

        self._build_ui()
        self._load_settings()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(3000)
        self._refresh_status()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs)
        self._build_shoot_tab()
        self._build_models_tab()

    def _build_shoot_tab(self) -> None:
        page = QtWidgets.QWidget()
        self.tabs.addTab(page, "SHOOT")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        # Site header — MANUEL MEJIA / CREATIVE TECHNOLOGIST · SHOOT
        masthead = QtWidgets.QHBoxLayout()
        site = QtWidgets.QLabel("MANUEL MEJIA")
        site.setProperty("role", "meta")
        role = QtWidgets.QLabel("— CREATIVE TECHNOLOGIST · SHOOT")
        role.setProperty("role", "label")
        masthead.addWidget(site)
        masthead.addWidget(role, 1)
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

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.status.setProperty("role", "meta")
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

        result_label = QtWidgets.QLabel("RESULT")
        result_label.setProperty("role", "sublabel")
        previews.addWidget(result_label)
        result_rule = QtWidgets.QFrame()
        result_rule.setProperty("role", "rule")
        previews.addWidget(result_rule)
        self.result_view = _ImageView("Generated image appears here")
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

        self.model_rows = {}
        for spec in MODELS:
            row = _ModelRow(spec)
            row.download_requested.connect(self._download_model)
            self.model_rows[spec.key] = row
            layout.addWidget(row)

        self.download_all_btn = QtWidgets.QPushButton("Download All Missing")
        self.download_all_btn.clicked.connect(self._download_all_missing)
        layout.addWidget(self.download_all_btn)
        layout.addStretch()

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
        except Exception:
            pass

    def _save_prompt_settings(self) -> None:
        try:
            from maya import cmds

            cmds.optionVar(sv=("shoot_prompt", self.prompt.toPlainText()))
            cmds.optionVar(iv=("shoot_seed", self.seed.value()))
            cmds.optionVar(iv=("shoot_lock_seed", int(self.lock_seed.isChecked())))
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
        if self.tabs.currentWidget() and self.tabs.tabText(self.tabs.currentIndex()) == "Models":
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

        Runs synchronously so the user sees immediate feedback. The in-flight
        generation task (if any) will fail on the next /history poll once the
        server is gone, which clears the busy state via _finish_generation.
        """
        self.status.setText("Killing ComfyUI...")
        QtWidgets.QApplication.processEvents()
        try:
            killed = self._manager.kill()
        except Exception as exc:
            self.status.setText(f"Kill failed: {exc}")
            return
        if killed:
            self.status.setText("ComfyUI killed.")
        else:
            self.status.setText("No ComfyUI process found to kill.")
        self._refresh_status()

    def _snap_viewport(self) -> None:
        try:
            snap = snapshot_active_view()
            _, _, label = get_viewport_angle()
            self._last_snapshot = snap
            self.reference_view.set_png(snap.png)
            self.status.setText(f"Snapped {snap.camera} — {label}.")
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
        if not self._last_snapshot:
            self.status.setText("Snap the viewport first.")
            return
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            self.status.setText("Add a prompt before generating.")
            return

        self._save_prompt_settings()
        self._set_busy(True)
        self.result_view.clear_image()
        self.save_btn.setEnabled(False)
        if not self.lock_seed.isChecked():
            self._randomize_seed()

        req = ShotRequest(
            prompt=prompt,
            reference_png=self._last_snapshot.png,
            width=self._last_snapshot.width,
            height=self._last_snapshot.height,
            aspect_ratio=self.aspect.currentText(),
            seed=self.seed.value(),
        )

        def task(signals):
            return generate(req, status_cb=signals.status.emit)

        worker = _Task(task)
        worker.signals.status.connect(self.status.setText)
        worker.signals.result.connect(self._show_result)
        worker.signals.failed.connect(self._show_generation_error)
        worker.signals.finished.connect(self._finish_generation)
        self._start_task(worker)

    def _show_result(self, result) -> None:
        self._last_result = result.png
        self.result_view.set_png(result.png)
        self.save_btn.setEnabled(True)
        self.status.setText("Done.")

    def _show_generation_error(self, msg: str) -> None:
        self.status.setText(f"Generation failed: {msg}")

    def _finish_generation(self) -> None:
        self._set_busy(False)
        self._refresh_status()

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
            spec.key for spec in MODELS if not model_present(spec, comfy_dir)
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
