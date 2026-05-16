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
        # ComfyUI prints a lot during startup (model scanning, VRAM load).
        # If stdout/stderr are PIPE and nothing reads them, the OS pipe
        # buffer (~64 KB on Windows) fills, the child blocks on write,
        # and the HTTP server never starts — `is_running()` then stays
        # False forever. Redirect to a log file instead.
        self._log_path = (
            Path(tempfile.gettempdir()) / f"shoot_comfy_{port}.log"
        )
        self._log_file = None  # type: Optional[object]

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

        # Truncate / re-open the log file each start.
        self._log_file = open(self._log_path, "wb", buffering=0)

        kwargs: dict = {
            "cwd": str(self.install_dir),
            "stdout": self._log_file,
            "stderr": subprocess.STDOUT,
            "stdin":  subprocess.DEVNULL,
        }

        if platform.system() == "Windows":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si
            # DETACHED_PROCESS so killing Maya doesn't take the server with it
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        self._proc = subprocess.Popen(cmd, **kwargs)
        self._pid_file.write_text(str(self._proc.pid))

    def log_path(self) -> Path:
        """Return the log file path so the panel can offer 'open log' on errors."""
        return self._log_path

    def _tail_log(self, max_bytes: int = 4096) -> str:
        try:
            if not self._log_path.exists():
                return ""
            size = self._log_path.stat().st_size
            with open(self._log_path, "rb") as f:
                if size > max_bytes:
                    f.seek(-max_bytes, 2)
                return f.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    def start_and_wait(
        self,
        timeout: float = 240.0,
        poll: float = 1.0,
        status_cb: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Start ComfyUI and block until the API responds or timeout expires.

        Default timeout is 4 minutes — cold-start with FLUX.2 models in VRAM
        takes ~60-120s on a 12 GB card after model scanning.
        """
        self.start()
        deadline = time.time() + timeout
        start = time.time()

        while time.time() < deadline:
            if self.is_running(timeout=1.0):
                return
            # Surface subprocess crash early
            if self._proc and self._proc.poll() is not None:
                tail = self._tail_log()
                raise RuntimeError(
                    f"ComfyUI exited with code {self._proc.returncode}.\n"
                    f"Log tail ({self._log_path}):\n{tail}"
                )
            elapsed = int(time.time() - start)
            if status_cb:
                status_cb(f"Starting ComfyUI… {elapsed}s")
            time.sleep(poll)

        tail = self._tail_log(2048)
        raise RuntimeError(
            f"ComfyUI did not respond on port {self.port} within {int(timeout)}s.\n"
            f"Log: {self._log_path}\nTail:\n{tail}"
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
            self._close_log()
            return

        pid = self._read_saved_pid()
        if pid:
            self._terminate_pid(pid)
            self._pid_file.unlink(missing_ok=True)
        self._proc = None
        self._close_log()

    def _close_log(self) -> None:
        try:
            if self._log_file is not None:
                self._log_file.close()
        except Exception:
            pass
        self._log_file = None

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
