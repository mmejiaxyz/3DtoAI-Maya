"""ComfyUI server lifecycle manager.

Handles detecting, starting, and stopping a local ComfyUI instance from
inside Maya.  Does NOT install ComfyUI — see SETUP.md for that one-time step.
"""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _default_comfy_dir() -> Path:
    try:
        from shoot.settings import get_comfy_dir

        configured = get_comfy_dir()
        if configured:
            return Path(configured).expanduser()
    except Exception:
        pass

    home = Path.home()
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("USERPROFILE", str(home))) / "ComfyUI"
    return home / "ComfyUI"


def _system_python() -> str:
    """Return a usable system python executable (not mayapy)."""
    # Prefer explicit venv inside ComfyUI if present
    candidates = []
    system = platform.system()
    if system == "Windows":
        candidates = ["python", "python3", "py"]
    else:
        candidates = ["python3", "python"]
    for name in candidates:
        path = shutil.which(name)
        if path and "maya" not in path.lower():
            return path
    return sys.executable  # last resort


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _api_alive(host: str, port: int, timeout: float = 2.0) -> bool:
    if not _port_open(host, port, timeout=timeout):
        return False
    try:
        req = urllib.request.Request(f"http://{host}:{port}/system_stats")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ------------------------------------------------------------------
# Manager
# ------------------------------------------------------------------

class ComfyManager:
    """
    Manages a local ComfyUI server process.

    Usage from Maya:
        manager = ComfyManager()
        if not manager.is_running():
            manager.start_and_wait(status_cb=lambda s: print(s))
        # ... use ComfyClient ...
        manager.stop()
    """

    def __init__(
        self,
        install_dir: Optional[Path] = None,
        host: str = "127.0.0.1",
        port: int = 8188,
    ):
        self.install_dir = Path(install_dir) if install_dir else _default_comfy_dir()
        self.host = host
        self.port = port
        self._proc: Optional[subprocess.Popen] = None
        self._pid_file = Path(tempfile.gettempdir()) / f"shoot_comfy_{port}.pid"

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_installed(self) -> bool:
        return (self.install_dir / "main.py").exists()

    def is_running(self, timeout: float = 2.0) -> bool:
        return _api_alive(self.host, self.port, timeout=timeout)

    def can_stop(self) -> bool:
        return (self._proc and self._proc.poll() is None) or self._read_saved_pid() is not None

    def status_text(self, timeout: float = 2.0) -> str:
        if not self.is_installed():
            return f"ComfyUI not found at {self.install_dir}"
        if self.is_running(timeout=timeout):
            return f"Running  ({self.host}:{self.port})"
        return "Installed - not running"

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch ComfyUI as a background subprocess.  Returns immediately."""
        if not self.is_installed():
            raise RuntimeError(
                f"ComfyUI not found at {self.install_dir}. "
                "See SETUP.md for installation instructions."
            )
        if self.is_running(timeout=0.5):
            return

        python = _system_python()
        cmd = [
            python,
            str(self.install_dir / "main.py"),
            "--port", str(self.port),
            "--preview-method", "none",
        ]

        kwargs: dict = {
            "cwd": str(self.install_dir),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }

        # Hide console window on Windows
        if platform.system() == "Windows":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si

        self._proc = subprocess.Popen(cmd, **kwargs)
        self._pid_file.write_text(str(self._proc.pid))

    def start_and_wait(
        self,
        timeout: float = 90.0,
        poll: float = 1.0,
        status_cb: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Start ComfyUI and block until the API responds or timeout expires."""
        self.start()
        deadline = time.time() + timeout
        start = time.time()

        while time.time() < deadline:
            if self.is_running(timeout=1.0):
                return
            # Surface subprocess crash early
            if self._proc and self._proc.poll() is not None:
                stderr = b""
                if self._proc.stderr:
                    stderr = self._proc.stderr.read(2000)
                raise RuntimeError(
                    f"ComfyUI process exited with code {self._proc.returncode}.\n"
                    + stderr.decode("utf-8", errors="replace")
                )
            elapsed = int(time.time() - start)
            if status_cb:
                status_cb(f"Starting ComfyUI… {elapsed}s (loading FLUX into VRAM)")
            time.sleep(poll)

        raise RuntimeError(
            f"ComfyUI did not respond within {int(timeout)}s. "
            "Check CUDA drivers and ComfyUI dependencies (see SETUP.md)."
        )

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Terminate the ComfyUI process that Shoot started."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._pid_file.unlink(missing_ok=True)
            self._proc = None
            return

        pid = self._read_saved_pid()
        if pid:
            self._terminate_pid(pid)
            self._pid_file.unlink(missing_ok=True)
        self._proc = None

    def kill(self) -> bool:
        """Force-kill ComfyUI listening on self.port, regardless of who started it.

        Returns True if a process was killed, False if none was found.
        Used by the panel's red 'Kill' button so the user can stop a runaway
        generation or a Comfy they started outside Shoot.
        """
        # First try the normal path — handles the Shoot-launched case cleanly.
        if self.can_stop():
            self.stop()
            return True

        # Fall back to PID-by-port discovery for externally-started servers.
        pid = self._find_pid_on_port(self.port)
        if pid:
            self._terminate_pid(pid)
            self._pid_file.unlink(missing_ok=True)
            self._proc = None
            return True
        return False

    def _find_pid_on_port(self, port: int) -> Optional[int]:
        """Return the PID of the process listening on *port*, or None."""
        system = platform.system()
        try:
            if system == "Windows":
                # netstat -ano emits lines ending with the PID.
                output = subprocess.run(
                    ["netstat", "-ano", "-p", "TCP"],
                    capture_output=True, text=True, timeout=5,
                ).stdout
                needle = f":{port} "
                for line in output.splitlines():
                    if "LISTENING" in line and needle in line:
                        parts = line.split()
                        try:
                            return int(parts[-1])
                        except ValueError:
                            continue
            else:
                # lsof is the most portable cross-Unix option.
                output = subprocess.run(
                    ["lsof", "-tiTCP:%d" % port, "-sTCP:LISTEN"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip()
                if output:
                    return int(output.splitlines()[0])
        except Exception:
            pass
        return None

    def _read_saved_pid(self) -> Optional[int]:
        try:
            if self._pid_file.exists():
                return int(self._pid_file.read_text().strip())
        except Exception:
            pass
        return None

    def _terminate_pid(self, pid: int) -> None:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
        try:
            os.kill(pid, 15)
        except OSError:
            pass

    def __del__(self):
        pass
