"""Drag this file onto a Maya 2027 viewport to install Shoot.

When Maya receives a dropped .py file, it executes the file and then
calls `onMayaDroppedPythonFile(obj)` if defined. This:

  1. Writes shoot.mod into Maya's modules directory so Maya auto-loads
     the plugin on future launches.
  2. Installs huggingface_hub into mayapy (only if missing).
  3. Wires the plugin path for the current session, so no Maya restart
     is needed.
  4. Loads the plugin and opens the Shoot panel.

Drag from your OS file explorer (not from a browser). On Windows the
file must be unblocked — right-click > Properties > Unblock if it was
downloaded as a ZIP.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

MAYA_VERSION = "2027"
REPO = Path(__file__).resolve().parent


def _maya_user_dir() -> Path:
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return home / "Library" / "Preferences" / "Autodesk" / "maya" / MAYA_VERSION
    if system == "Windows":
        return Path(os.environ.get("USERPROFILE", str(home))) / "Documents" / "maya" / MAYA_VERSION
    return home / "maya" / MAYA_VERSION


def _write_mod_file() -> Path:
    modules_dir = _maya_user_dir() / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)
    mod = modules_dir / "shoot.mod"
    mod.write_text(
        f"+ shoot 1.0 {REPO}\nscripts: {REPO}\nplug-ins: {REPO / 'shoot'}\n"
    )
    return mod


def _ensure_huggingface_hub() -> None:
    try:
        import huggingface_hub  # noqa: F401
        return
    except ImportError:
        pass
    print("[shoot] installing huggingface_hub into mayapy...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "huggingface_hub>=0.20.0"]
        )
    except subprocess.CalledProcessError as e:
        print(
            f"[shoot] pip install failed ({e}). "
            "Re-run from a terminal: "
            f'"{sys.executable}" -m pip install huggingface_hub>=0.20.0'
        )


def _wire_session_paths() -> None:
    plugin_dir = str(REPO / "shoot")
    current = os.environ.get("MAYA_PLUG_IN_PATH", "")
    if plugin_dir not in current.split(os.pathsep):
        os.environ["MAYA_PLUG_IN_PATH"] = (
            f"{plugin_dir}{os.pathsep}{current}" if current else plugin_dir
        )
    repo_str = str(REPO)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


def onMayaDroppedPythonFile(_obj):  # noqa: N802 — Maya-required name
    import maya.cmds as cmds

    mod = _write_mod_file()
    print(f"[shoot] wrote {mod}")

    _ensure_huggingface_hub()
    _wire_session_paths()

    if cmds.pluginInfo("shoot", q=True, loaded=True):
        cmds.unloadPlugin("shoot")
    cmds.loadPlugin("shoot")
    cmds.shootOpen()
    print("[shoot] installed. Use Shoot > Open Shoot Panel from the menu bar.")
