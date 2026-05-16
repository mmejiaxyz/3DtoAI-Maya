"""One-shot installer for the Shoot plugin.

Run with the system python (or mayapy):

    python install.py            # install
    python install.py --uninstall
    python install.py --no-deps  # skip pip install

What it does:
  1. Writes ~/Library/Preferences/Autodesk/maya/2027/modules/shoot.mod
     pointing at this repo, so Maya auto-loads it on next launch.
  2. Pip-installs requirements.txt into mayapy.

Tested on macOS, Maya 2027. The mod-file format is identical on all
platforms; the install path differs.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

MAYA_VERSION = "2027"
REPO = Path(__file__).resolve().parent


def maya_user_dir() -> Path:
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return home / "Library" / "Preferences" / "Autodesk" / "maya" / MAYA_VERSION
    if system == "Windows":
        return Path(os.environ.get("USERPROFILE", str(home))) / "Documents" / "maya" / MAYA_VERSION
    return home / "maya" / MAYA_VERSION  # linux


def mayapy_path() -> Path | None:
    system = platform.system()
    if system == "Darwin":
        p = Path(f"/Applications/Autodesk/maya{MAYA_VERSION}/Maya.app/Contents/bin/mayapy")
        return p if p.exists() else None
    if system == "Windows":
        p = Path(f"C:/Program Files/Autodesk/Maya{MAYA_VERSION}/bin/mayapy.exe")
        return p if p.exists() else None
    p = Path(f"/usr/autodesk/maya{MAYA_VERSION}/bin/mayapy")
    return p if p.exists() else None


def write_mod_file() -> Path:
    modules_dir = maya_user_dir() / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)
    mod = modules_dir / "shoot.mod"
    contents = f"+ shoot 1.0 {REPO}\nscripts: {REPO}\nplug-ins: {REPO / 'shoot'}\n"
    mod.write_text(contents)
    return mod


def remove_mod_file() -> Path | None:
    mod = maya_user_dir() / "modules" / "shoot.mod"
    if mod.exists():
        mod.unlink()
        return mod
    return None


def install_deps() -> None:
    py = mayapy_path()
    if py is None:
        print("! mayapy not found — install deps manually with:")
        print(f"    <mayapy> -m pip install -r {REPO / 'requirements.txt'}")
        return
    print(f"Installing deps into {py}")
    subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(py), "-m", "pip", "install", "-r", str(REPO / "requirements.txt")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--no-deps", action="store_true")
    args = ap.parse_args()

    if args.uninstall:
        removed = remove_mod_file()
        if removed:
            print(f"Removed {removed}")
        else:
            print("Nothing to remove.")
        return

    mod = write_mod_file()
    print(f"Wrote {mod}")
    if not args.no_deps:
        install_deps()
    print()
    print("Done. Next steps:")
    print(f"  1. Launch Maya {MAYA_VERSION}.")
    print("  2. Window > Settings/Preferences > Plug-in Manager > load `plugin.py`.")
    print("  3. Or run in the script editor:")
    print("       import maya.cmds as cmds; cmds.loadPlugin('plugin.py'); cmds.shootOpen()")


if __name__ == "__main__":
    main()
