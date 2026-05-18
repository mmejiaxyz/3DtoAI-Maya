"""First-launch onboarding wizard for the Shoot panel.

A modal QDialog stepped through four phases:

  1. Welcome  — explain what the wizard will do.
  2. ComfyUI  — detect or install ComfyUI (Windows: full auto via git
                clone + venv + pip install; mac/linux: link + path
                picker, user installs manually then comes back).
  3. HF Token — optional read token for the gated FLUX.2 Klein UNet.
  4. Models   — download the three required weights.
  5. Done     — close and reveal the panel.

The wizard writes the same Maya optionVars the panel already reads
(`shoot_comfy_dir`, `shoot_hf_token`), so the panel state is in sync
the moment the wizard closes. Setting `shoot_onboarded=1` prevents
the wizard from reappearing on future launches.

Long-running ops (clone+install ComfyUI, model downloads) run on the
global QThreadPool and stream status back through Qt signals.
"""
from __future__ import annotations

import platform
from pathlib import Path
from typing import Callable, Optional

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from shoot.comfy import installer
from shoot.comfy.downloader import (
    MODELS,
    MODELS_BY_KEY,
    download_model,
    model_present,
)
from shoot.comfy.manager import ComfyManager


# ── Design tokens (mirror shoot_panel) ────────────────────────────────────────

PAPER = "#F3F1EE"
INK   = "#0C0E11"
FG_1  = "rgba(243, 241, 238, 255)"
FG_2  = "rgba(243, 241, 238, 217)"
FG_3  = "rgba(243, 241, 238, 166)"
FG_5  = "rgba(243, 241, 238, 128)"
FG_6  = "rgba(243, 241, 238, 102)"
FG_7  = "rgba(243, 241, 238,  76)"
RULE      = "rgba(243, 241, 238,  46)"
RULE_SOFT = "rgba(243, 241, 238,  30)"

WIZARD_QSS = f"""
* {{
    font-family: "Consolas", "Cascadia Mono", "SF Mono", "Menlo", monospace;
    font-size: 13px;
    color: {FG_1};
    letter-spacing: 0.3px;
}}
QDialog#shootWizard {{ background: {INK}; }}

QLabel[role="title"] {{
    color: {FG_1};
    font-size: 22px;
    letter-spacing: 2px;
    padding: 0 0 4px 0;
}}
QLabel[role="step"] {{
    color: {FG_6};
    font-size: 10px;
    letter-spacing: 2.4px;
}}
QLabel[role="body"]     {{ color: {FG_2}; }}
QLabel[role="sublabel"] {{ color: {FG_5}; font-size: 10px; letter-spacing: 1.8px; }}
QLabel[role="hint"]     {{ color: {FG_6}; font-size: 11px; }}
QLabel[role="ok"]       {{ color: {FG_1}; }}
QLabel[role="warn"]     {{ color: {FG_3}; }}

QFrame[role="rule"] {{
    background: {RULE};
    max-height: 1px;
    min-height: 1px;
    border: 0;
}}

QLineEdit, QPlainTextEdit {{
    background: transparent;
    border: 1px solid {RULE};
    color: {FG_1};
    padding: 7px 9px;
    selection-background-color: {FG_7};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {FG_3}; }}

QPushButton {{
    background: transparent;
    border: 1px solid {RULE};
    color: {FG_1};
    padding: 8px 18px;
    letter-spacing: 1.5px;
}}
QPushButton:hover    {{ border-color: {FG_3}; }}
QPushButton:pressed  {{ background: rgba(243, 241, 238, 14); }}
QPushButton:disabled {{ color: {FG_6}; border-color: {RULE_SOFT}; }}
QPushButton[role="primary"] {{ color: {INK}; background: {PAPER}; border-color: {PAPER}; }}
QPushButton[role="primary"]:hover {{ background: {FG_2}; }}
QPushButton[role="primary"]:disabled {{ color: {FG_5}; background: {RULE_SOFT}; border-color: {RULE_SOFT}; }}

QProgressBar {{
    background: transparent;
    border: 1px solid {RULE_SOFT};
    height: 4px;
    text-align: center;
    color: {FG_6};
}}
QProgressBar::chunk {{ background: {PAPER}; }}

QPlainTextEdit#wizardLog {{
    background: rgba(0, 0, 0, 80);
    color: {FG_3};
    font-size: 11px;
    border: 1px solid {RULE_SOFT};
}}
"""


# ── Threadpool helper ────────────────────────────────────────────────────────


class _TaskSignals(QtCore.QObject):
    status   = QtCore.Signal(str)
    progress = QtCore.Signal(int, int)
    result   = QtCore.Signal(object)
    failed   = QtCore.Signal(str)
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


# ── Step widgets ──────────────────────────────────────────────────────────────


class _StepBase(QtWidgets.QWidget):
    """Common scaffold: title, body, content area."""

    def __init__(self, step_index: int, step_total: int, title: str, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        step = QtWidgets.QLabel(f"STEP {step_index} OF {step_total}")
        step.setProperty("role", "step")
        layout.addWidget(step)

        t = QtWidgets.QLabel(title)
        t.setProperty("role", "title")
        layout.addWidget(t)

        rule = QtWidgets.QFrame()
        rule.setProperty("role", "rule")
        layout.addWidget(rule)

        self.content = QtWidgets.QVBoxLayout()
        self.content.setContentsMargins(0, 6, 0, 0)
        self.content.setSpacing(12)
        layout.addLayout(self.content, 1)


class WelcomeStep(_StepBase):
    def __init__(self, parent=None):
        super().__init__(1, 4, "Welcome to Shoot", parent)
        body = QtWidgets.QLabel(
            "Shoot turns a Maya viewport into a still rendered by a local "
            "FLUX.2 Klein workflow on ComfyUI.\n\n"
            "This short setup will:\n"
            "  •  Locate or install ComfyUI\n"
            "  •  Save an optional HuggingFace token (gated UNet)\n"
            "  •  Download the three model weights\n\n"
            "You can skip any step and configure it later from the Models tab."
        )
        body.setProperty("role", "body")
        body.setWordWrap(True)
        self.content.addWidget(body)
        self.content.addStretch(1)


class ComfyStep(_StepBase):
    """Detect / install / point-to-existing ComfyUI."""

    state_changed = QtCore.Signal(bool)  # True when ready to advance

    def __init__(self, parent=None):
        super().__init__(2, 4, "ComfyUI", parent)
        self._pool = QtCore.QThreadPool.globalInstance()
        self._task: Optional[_Task] = None
        self._cancel = False
        self._installing = False

        status_row = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("Checking default location…")
        self.status_label.setProperty("role", "body")
        self.status_label.setWordWrap(True)
        status_row.addWidget(self.status_label, 1)
        self.content.addLayout(status_row)

        path_row = QtWidgets.QHBoxLayout()
        path_row.setSpacing(8)
        label = QtWidgets.QLabel("INSTALL PATH")
        label.setProperty("role", "sublabel")
        label.setFixedWidth(110)
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setText(str(self._default_path()))
        self.path_edit.textChanged.connect(self._refresh_status)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        path_row.addWidget(label)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        self.content.addLayout(path_row)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self.install_btn = QtWidgets.QPushButton("Install Here")
        self.install_btn.setProperty("role", "primary")
        self.install_btn.clicked.connect(self._start_install)
        self.use_btn = QtWidgets.QPushButton("Use This Path")
        self.use_btn.clicked.connect(self._use_path)
        btn_row.addWidget(self.install_btn)
        btn_row.addWidget(self.use_btn)
        btn_row.addStretch(1)
        self.content.addLayout(btn_row)

        # mac/linux helper line
        if platform.system() != "Windows":
            note = QtWidgets.QLabel(
                "macOS / Linux: auto-install isn't bundled. Clone "
                "github.com/comfyanonymous/ComfyUI, install its requirements "
                "into a venv, then point the path above at that folder and "
                "click <i>Use This Path</i>."
            )
            note.setProperty("role", "hint")
            note.setOpenExternalLinks(True)
            note.setWordWrap(True)
            self.content.addWidget(note)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setObjectName("wizardLog")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(160)
        self.log.setVisible(False)
        self.content.addWidget(self.log, 1)

        self._refresh_status()

    @staticmethod
    def _default_path() -> Path:
        return ComfyManager().install_dir

    def _browse(self) -> None:
        start = self.path_edit.text() or str(Path.home())
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select ComfyUI directory", start
        )
        if chosen:
            self.path_edit.setText(chosen)

    def _current_path(self) -> Path:
        return Path(self.path_edit.text()).expanduser()

    def _is_present(self, path: Path) -> bool:
        return (path / "main.py").exists()

    def _refresh_status(self) -> None:
        if self._installing:
            return
        path = self._current_path()
        if self._is_present(path):
            self.status_label.setText(
                f"Found a ComfyUI install at {path}. Click <b>Use This Path</b> to continue."
            )
            self.status_label.setProperty("role", "ok")
            self.install_btn.setEnabled(False)
            self.install_btn.setText("Already Installed")
            self.use_btn.setEnabled(True)
            self.state_changed.emit(True)
        else:
            os_name = platform.system()
            if os_name == "Windows":
                self.status_label.setText(
                    f"No ComfyUI at {path}. Click <b>Install Here</b> to download and "
                    "set it up (~5–15 min, ~5 GB)."
                )
            else:
                self.status_label.setText(
                    f"No ComfyUI at {path}. Install it manually (see note below), "
                    "then point this path at it."
                )
            self.status_label.setProperty("role", "body")
            self.install_btn.setEnabled(os_name == "Windows")
            self.install_btn.setText("Install Here")
            self.use_btn.setEnabled(False)
            self.state_changed.emit(False)
        # Re-apply role change for repaint.
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _use_path(self) -> None:
        self.commit()
        self.state_changed.emit(True)

    def commit(self) -> None:
        """Persist the current path if it points at a real install."""
        path = self._current_path()
        if self._is_present(path):
            import maya.cmds as cmds
            cmds.optionVar(sv=("shoot_comfy_dir", str(path)))

    def _append_log(self, line: str) -> None:
        self.log.appendPlainText(line)
        # Auto-scroll
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _start_install(self) -> None:
        if self._installing:
            return
        dest = self._current_path()
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Cheap up-front check, before spawning the worker.
        if not installer.git_available():
            QtWidgets.QMessageBox.warning(
                self,
                "Git not found",
                "`git` isn't on PATH. Install Git from "
                "https://git-scm.com/download/win, restart Maya, and retry.",
            )
            return
        if not installer.system_python_available():
            QtWidgets.QMessageBox.warning(
                self,
                "Python not found",
                "No system Python found on PATH (mayapy doesn't count). "
                "Install Python 3.10+ from python.org, restart Maya, and retry.",
            )
            return

        self._installing = True
        self._cancel = False
        self.log.clear()
        self.log.setVisible(True)
        self.install_btn.setText("Installing…")
        self.install_btn.setEnabled(False)
        self.use_btn.setEnabled(False)
        self.path_edit.setEnabled(False)
        self.status_label.setText(f"Installing ComfyUI into {dest}.  Streaming log below.")
        self.state_changed.emit(False)

        def fn(signals: _TaskSignals):
            installer.install_comfyui(
                dest,
                status_cb=lambda s: signals.status.emit(s),
                cancelled=lambda: self._cancel,
            )
            return dest

        self._task = _Task(fn)
        self._task.signals.status.connect(self._append_log)
        self._task.signals.failed.connect(self._on_install_failed)
        self._task.signals.result.connect(self._on_install_ok)
        self._task.signals.finished.connect(self._on_install_finished)
        self._pool.start(self._task)

    def _on_install_ok(self, dest: object) -> None:
        import maya.cmds as cmds

        cmds.optionVar(sv=("shoot_comfy_dir", str(dest)))
        self._append_log(f"\nOK — saved comfy_dir = {dest}")

    def _on_install_failed(self, msg: str) -> None:
        self._append_log(f"\nFAILED: {msg}")

    def _on_install_finished(self) -> None:
        self._installing = False
        self._task = None
        self.path_edit.setEnabled(True)
        self._refresh_status()

    def request_cancel(self) -> None:
        self._cancel = True


class TokenStep(_StepBase):
    """Optional HuggingFace token entry."""

    def __init__(self, parent=None):
        super().__init__(3, 4, "HuggingFace Token (optional)", parent)
        body = QtWidgets.QLabel(
            "The FLUX.2 Klein UNet is a <i>gated</i> model on HuggingFace. To download "
            "it from this plugin you need a read-scoped access token. The other two "
            "model files are ungated and don't need a token.<br><br>"
            f'1.&nbsp;&nbsp;Visit <a style="color:{FG_2};" '
            'href="https://huggingface.co/black-forest-labs/FLUX.2-klein-9b-kv-fp8">'
            "huggingface.co/black-forest-labs/FLUX.2-klein-9b-kv-fp8</a> "
            "and accept the license.<br>"
            f'2.&nbsp;&nbsp;Create a token at <a style="color:{FG_2};" '
            'href="https://huggingface.co/settings/tokens">'
            "huggingface.co/settings/tokens</a> (role: read).<br>"
            "3.&nbsp;&nbsp;Paste it below."
        )
        body.setProperty("role", "body")
        body.setTextFormat(QtCore.Qt.RichText)
        body.setOpenExternalLinks(True)
        body.setWordWrap(True)
        self.content.addWidget(body)

        row = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel("HF TOKEN")
        label.setProperty("role", "sublabel")
        label.setFixedWidth(110)
        self.token = QtWidgets.QLineEdit()
        self.token.setEchoMode(QtWidgets.QLineEdit.Password)
        self.token.setPlaceholderText("hf_…")
        try:
            import maya.cmds as cmds
            if cmds.optionVar(exists="shoot_hf_token"):
                self.token.setText(cmds.optionVar(q="shoot_hf_token"))
        except Exception:
            pass
        row.addWidget(label)
        row.addWidget(self.token, 1)
        self.content.addLayout(row)

        hint = QtWidgets.QLabel(
            "You can skip this and add the token from the Models tab later."
        )
        hint.setProperty("role", "hint")
        self.content.addWidget(hint)
        self.content.addStretch(1)

    def commit(self) -> None:
        import maya.cmds as cmds

        cmds.optionVar(sv=("shoot_hf_token", self.token.text().strip()))


class _MiniModelRow(QtWidgets.QWidget):
    download_requested = QtCore.Signal(str)

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setStyleSheet(f"_MiniModelRow {{ border-top: 1px solid {RULE_SOFT}; }}")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(12)

        self.name = QtWidgets.QLabel(spec.display_name)
        self.name.setProperty("role", "body")
        self.name.setWordWrap(True)
        self.state = QtWidgets.QLabel("CHECKING")
        self.state.setProperty("role", "sublabel")
        self.state.setFixedWidth(92)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setFixedWidth(140)
        self.button = QtWidgets.QPushButton("Download")
        self.button.setFixedWidth(110)
        self.button.clicked.connect(lambda: self.download_requested.emit(spec.key))

        layout.addWidget(self.name, 1)
        layout.addWidget(self.state)
        layout.addWidget(self.progress)
        layout.addWidget(self.button)

    def set_ready(self, ready: bool) -> None:
        self.progress.setVisible(False)
        self.button.setEnabled(not ready)
        self.state.setText("READY" if ready else "MISSING")
        self.button.setText("Ready" if ready else "Download")

    def set_busy(self) -> None:
        self.state.setText("DOWNLOADING")
        self.progress.setVisible(True)
        self.button.setEnabled(False)

    def set_progress(self, done: int, total: int) -> None:
        self.progress.setVisible(True)
        if total:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(done * 100 / total))
        else:
            self.progress.setRange(0, 0)


class ModelsStep(_StepBase):
    """Download the three required weights."""

    state_changed = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(4, 4, "Model Weights", parent)
        self._pool = QtCore.QThreadPool.globalInstance()
        self._downloading: set[str] = set()
        self._queue: list[str] = []

        intro = QtWidgets.QLabel(
            "Three files, about 17 GB total. They land in the ComfyUI <code>models/</code> "
            "subfolders. Downloads resume if interrupted."
        )
        intro.setProperty("role", "body")
        intro.setWordWrap(True)
        self.content.addWidget(intro)

        self.rows: dict[str, _MiniModelRow] = {}
        # Only show models needed for the default Klein flow — secondary modes
        # (Flux2 dev, multi-angle) the user can fetch from the Models tab later.
        for spec in MODELS:
            row = _MiniModelRow(spec)
            row.download_requested.connect(self._enqueue)
            self.rows[spec.key] = row
            self.content.addWidget(row)

        btn_row = QtWidgets.QHBoxLayout()
        self.download_all_btn = QtWidgets.QPushButton("Download All Missing")
        self.download_all_btn.setProperty("role", "primary")
        self.download_all_btn.clicked.connect(self._download_all)
        btn_row.addWidget(self.download_all_btn)
        btn_row.addStretch(1)
        self.content.addLayout(btn_row)

        self.content.addStretch(1)

        self.refresh()

    def _comfy_dir(self) -> Optional[Path]:
        import maya.cmds as cmds
        if cmds.optionVar(exists="shoot_comfy_dir"):
            return Path(cmds.optionVar(q="shoot_comfy_dir")).expanduser()
        return ComfyManager().install_dir

    def _hf_token(self) -> Optional[str]:
        import maya.cmds as cmds
        if cmds.optionVar(exists="shoot_hf_token"):
            t = cmds.optionVar(q="shoot_hf_token").strip()
            return t or None
        return None

    def refresh(self) -> None:
        comfy = self._comfy_dir()
        if not comfy:
            for row in self.rows.values():
                row.set_ready(False)
            self.state_changed.emit(False)
            return
        all_ready = True
        for key, row in self.rows.items():
            present = model_present(MODELS_BY_KEY[key], comfy)
            row.set_ready(present)
            if not present:
                all_ready = False
        self.download_all_btn.setEnabled(not all_ready and not self._downloading)
        self.state_changed.emit(all_ready)

    def _enqueue(self, key: str) -> None:
        if key in self._downloading or key in self._queue:
            return
        self._queue.append(key)
        self._pump()

    def _download_all(self) -> None:
        comfy = self._comfy_dir()
        if not comfy:
            return
        for key, row in self.rows.items():
            spec = MODELS_BY_KEY[key]
            if not model_present(spec, comfy):
                self._enqueue(key)

    def _pump(self) -> None:
        if self._downloading or not self._queue:
            return
        key = self._queue.pop(0)
        self._start_download(key)

    def _start_download(self, key: str) -> None:
        comfy = self._comfy_dir()
        if not comfy:
            return
        spec = MODELS_BY_KEY[key]
        row = self.rows[key]
        row.set_busy()
        self._downloading.add(key)
        self.download_all_btn.setEnabled(False)
        token = self._hf_token()

        def fn(signals: _TaskSignals):
            download_model(
                spec,
                comfy,
                hf_token=token,
                progress_cb=lambda d, t: signals.progress.emit(d, t),
                status_cb=lambda s: signals.status.emit(s),
            )
            return key

        task = _Task(fn)
        task.signals.progress.connect(row.set_progress)
        task.signals.failed.connect(lambda msg, k=key: self._on_failed(k, msg))
        task.signals.result.connect(lambda _r, k=key: self._on_done(k))
        task.signals.finished.connect(lambda k=key: self._on_finished(k))
        self._pool.start(task)

    def _on_done(self, key: str) -> None:
        self.rows[key].set_ready(True)

    def _on_failed(self, key: str, msg: str) -> None:
        QtWidgets.QMessageBox.warning(
            self,
            "Download failed",
            f"{MODELS_BY_KEY[key].display_name}\n\n{msg}",
        )
        self.rows[key].set_ready(False)

    def _on_finished(self, key: str) -> None:
        self._downloading.discard(key)
        self.refresh()
        self._pump()


# ── The wizard itself ─────────────────────────────────────────────────────────


class OnboardingWizard(QtWidgets.QDialog):
    """Modal first-launch setup. Returns True from exec() if completed
    (or explicitly skipped); the caller marks `shoot_onboarded`.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("shootWizard")
        self.setWindowTitle("Set up Shoot")
        self.setModal(True)
        self.setMinimumSize(720, 560)
        self.resize(820, 640)
        self.setStyleSheet(WIZARD_QSS)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        self.stack = QtWidgets.QStackedWidget()
        root.addWidget(self.stack, 1)

        self.welcome = WelcomeStep()
        self.comfy   = ComfyStep()
        self.token   = TokenStep()
        self.models  = ModelsStep()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.comfy)
        self.stack.addWidget(self.token)
        self.stack.addWidget(self.models)

        # Footer with nav buttons
        rule = QtWidgets.QFrame()
        rule.setProperty("role", "rule")
        root.addWidget(rule)

        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(8)
        self.back_btn = QtWidgets.QPushButton("Back")
        self.back_btn.clicked.connect(self._on_back)
        self.skip_btn = QtWidgets.QPushButton("Skip")
        self.skip_btn.clicked.connect(self._on_skip)
        self.next_btn = QtWidgets.QPushButton("Next")
        self.next_btn.setProperty("role", "primary")
        self.next_btn.clicked.connect(self._on_next)
        footer.addWidget(self.back_btn)
        footer.addStretch(1)
        footer.addWidget(self.skip_btn)
        footer.addWidget(self.next_btn)
        root.addLayout(footer)

        self.stack.currentChanged.connect(self._sync_buttons)
        self._sync_buttons()

    # ── Step transitions ─────────────────────────────────────────────────────

    def _index(self) -> int:
        return self.stack.currentIndex()

    def _on_next(self) -> None:
        idx = self._index()
        current = self.stack.currentWidget()
        commit = getattr(current, "commit", None)
        if callable(commit):
            commit()
        # Token step changes hf_token; let the next step (Models) re-evaluate.
        if idx == 2:
            self.models.refresh()
        if idx == self.stack.count() - 1:
            self.accept()
        else:
            self.stack.setCurrentIndex(idx + 1)

    def _on_back(self) -> None:
        idx = self._index()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)

    def _on_skip(self) -> None:
        idx = self._index()
        if idx == self.stack.count() - 1:
            self.accept()
        else:
            self.stack.setCurrentIndex(idx + 1)

    def _sync_buttons(self) -> None:
        idx = self._index()
        last = idx == self.stack.count() - 1
        self.back_btn.setEnabled(idx > 0)
        # Welcome step: no skip; final step: "Finish" instead of "Next"
        self.skip_btn.setVisible(idx > 0 and not last)
        self.next_btn.setText("Finish" if last else "Next")
        # Reset to default enabled; per-step signals may toggle it.
        self.next_btn.setEnabled(True)

    # ── Cancel ───────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        # Any path out of the dialog (Esc, [X], accept, reject) must cancel
        # an in-flight ComfyUI install — otherwise the worker keeps emitting
        # signals into a destroyed widget tree.
        self.comfy.request_cancel()
        super().closeEvent(event)
