"""One-shot ComfyUI installer for the onboarding wizard.

Performs the same three steps a user would do manually:

  1. `git clone https://github.com/comfyanonymous/ComfyUI.git <dest>`
  2. `<system python> -m venv <dest>/venv`
  3. `<venv python> -m pip install -r <dest>/requirements.txt`

Streams subprocess output via a status callback. Cancellable: the
runner thread polls the cancel callable between phases and after each
line read from the subprocess. Cancellation terminates the active
subprocess; partially-cloned/installed directories are left in place
for the user to either retry into or delete manually.

Windows-only by intent — the wizard only invokes this on Windows.
The code itself is platform-agnostic, but the README's "tested only
on Windows 11 + CUDA" caveat applies.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

StatusCb = Callable[[str], None]
CancelCb = Callable[[], bool]


COMFYUI_REPO = "https://github.com/comfyanonymous/ComfyUI.git"


# ── Environment probes ───────────────────────────────────────────────────────


def git_available() -> bool:
    return shutil.which("git") is not None


def _system_python() -> Optional[str]:
    """Return a Python executable that is NOT mayapy."""
    system = platform.system()
    names = ["python", "python3", "py"] if system == "Windows" else ["python3", "python"]
    for name in names:
        path = shutil.which(name)
        if path and "maya" not in path.lower():
            return path
    return None


def system_python_available() -> bool:
    return _system_python() is not None


def _venv_python(comfy_dir: Path) -> Path:
    if platform.system() == "Windows":
        return comfy_dir / "venv" / "Scripts" / "python.exe"
    return comfy_dir / "venv" / "bin" / "python"


# ── Subprocess helper ────────────────────────────────────────────────────────


class _Cancelled(RuntimeError):
    pass


def _run_streaming(
    cmd: list[str],
    cwd: Optional[Path],
    status_cb: StatusCb,
    cancelled: Optional[CancelCb],
    label: str,
) -> None:
    """Run *cmd*, stream stdout+stderr to status_cb line-by-line.

    Raises subprocess.CalledProcessError on non-zero exit, or
    _Cancelled if the caller signalled cancel mid-stream.
    """
    status_cb(f"$ {label}")

    # Inherit env but force unbuffered Python output for pip/venv runs.
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    creationflags = 0
    if platform.system() == "Windows":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        creationflags=creationflags,
    )

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                status_cb(line)
            if cancelled and cancelled():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise _Cancelled()
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


# ── Phases ───────────────────────────────────────────────────────────────────


def _clone(dest: Path, status_cb: StatusCb, cancelled: Optional[CancelCb]) -> None:
    if (dest / ".git").exists():
        status_cb(f"[1/3] Clone — skipped, {dest} already a git repo")
        return
    status_cb(f"[1/3] Cloning ComfyUI into {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run_streaming(
        ["git", "clone", "--depth", "1", COMFYUI_REPO, str(dest)],
        cwd=None,
        status_cb=status_cb,
        cancelled=cancelled,
        label=f"git clone {COMFYUI_REPO} {dest}",
    )


def _create_venv(dest: Path, status_cb: StatusCb, cancelled: Optional[CancelCb]) -> None:
    venv_py = _venv_python(dest)
    if venv_py.exists():
        status_cb(f"[2/3] Venv — already present at {venv_py.parent.parent}")
        return
    py = _system_python()
    if not py:
        raise RuntimeError(
            "No system Python found on PATH. Install Python 3.10+ from python.org, "
            "then re-run the wizard."
        )
    status_cb(f"[2/3] Creating venv with {py}")
    _run_streaming(
        [py, "-m", "venv", "venv"],
        cwd=dest,
        status_cb=status_cb,
        cancelled=cancelled,
        label=f"{py} -m venv venv",
    )


def _install_requirements(
    dest: Path, status_cb: StatusCb, cancelled: Optional[CancelCb]
) -> None:
    venv_py = _venv_python(dest)
    if not venv_py.exists():
        raise RuntimeError(f"Venv python not found at {venv_py}.")
    req = dest / "requirements.txt"
    if not req.exists():
        raise RuntimeError(f"requirements.txt missing in {dest}.")
    status_cb("[3/3] Upgrading pip")
    _run_streaming(
        [str(venv_py), "-m", "pip", "install", "--upgrade", "pip"],
        cwd=dest,
        status_cb=status_cb,
        cancelled=cancelled,
        label=f"{venv_py} -m pip install --upgrade pip",
    )
    status_cb("[3/3] Installing ComfyUI requirements (this can take 5–15 minutes)")
    _run_streaming(
        [str(venv_py), "-m", "pip", "install", "-r", str(req)],
        cwd=dest,
        status_cb=status_cb,
        cancelled=cancelled,
        label=f"{venv_py} -m pip install -r requirements.txt",
    )


# ── Public entry point ───────────────────────────────────────────────────────


def install_comfyui(
    dest: Path,
    status_cb: StatusCb,
    cancelled: Optional[CancelCb] = None,
) -> Path:
    """Install ComfyUI into *dest*. Returns *dest* on success.

    Raises:
        RuntimeError: missing git, missing system python, or other
            structural failure (with a user-actionable message).
        subprocess.CalledProcessError: a phase exited non-zero.
        _Cancelled: caller signalled cancellation mid-run.
    """
    dest = Path(dest).expanduser().resolve()

    if not git_available():
        raise RuntimeError(
            "`git` is not on PATH. Install Git from https://git-scm.com/download/win "
            "(restart your shell after), then retry."
        )

    _clone(dest, status_cb, cancelled)
    if cancelled and cancelled():
        raise _Cancelled()
    _create_venv(dest, status_cb, cancelled)
    if cancelled and cancelled():
        raise _Cancelled()
    _install_requirements(dest, status_cb, cancelled)

    status_cb(f"ComfyUI installed at {dest}.")
    return dest


# Re-export so callers can catch cancellation without importing the private name.
Cancelled = _Cancelled
