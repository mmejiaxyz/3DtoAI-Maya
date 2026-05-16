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
import urllib.request
from pathlib import Path
from typing import Callable, Optional


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _state_dir() -> Path:
    """Per-user, non-world-writable directory for pid/log files.

    Avoids the shared system temp dir, where a predictable name like
    `shoot_comfy_8188.pid` would let another local user trick the Kill
    button into terminating an arbitrary process owned by this user, or
    truncate-via-symlink arbitrary files this user can write.
    """
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    d = base / "Shoot"
    d.mkdir(parents=True, exist_ok=True)
    if platform.system() != "Windows":
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
    return d


def _find_listening_pid(port: int) -> Optional[int]:
    """Return the PID currently bound to *port* on localhost, or None.

    Single source of truth used both by the kill path and by the pid-file
    verifier — if the stored pid doesn't match what's actually serving the
    port, the stored pid is stale or tampered with and must be ignored.
    """
    system = platform.system()
    try:
        if system == "Windows":
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
            output = subprocess.run(
                ["lsof", "-tiTCP:%d" % port, "-sTCP:LISTEN"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if output:
                return int(output.splitlines()[0])
    except Exception:
        pass
    return None


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


def _venv_python(install_dir: Path) -> Optional[str]:
    """Return the python executable inside ComfyUI's venv, if one exists.

    ComfyUI almost always lives in its own venv with a pinned torch build,
    so launching it with a generic system python usually fails on import.
    """
    if platform.system() == "Windows":
        rels = [Path("venv") / "Scripts" / "python.exe",
                Path(".venv") / "Scripts" / "python.exe"]
    else:
        rels = [Path("venv") / "bin" / "python",
                Path(".venv") / "bin" / "python"]
    for rel in rels:
        p = install_dir / rel
        if p.exists():
            return str(p)
    return None


def _system_python() -> str:
    """Return a usable system python executable (not mayapy)."""
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
        state = _state_dir()
        self._pid_file = state / f"comfy_{port}.pid"
        # ComfyUI prints a lot during startup (model scanning, VRAM load).
        # If stdout/stderr are PIPE and nothing reads them, the OS pipe
        # buffer (~64 KB on Windows) fills, the child blocks on write,
        # and the HTTP server never starts — `is_running()` then stays
        # False forever. Redirect to a log file instead.
        self._log_path = state / f"comfy_{port}.log"
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

        python = _venv_python(self.install_dir) or _system_python()
        cmd = [
            python,
            str(self.install_dir / "main.py"),
            "--port", str(self.port),
            "--preview-method", "none",
        ]

        # Truncate / re-open the log file each start. O_NOFOLLOW on Unix
        # prevents a pre-planted symlink in the state dir from redirecting
        # the truncate. (No effect on Windows; the state dir there is
        # already user-private under %LOCALAPPDATA%.)
        log_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            log_flags |= os.O_NOFOLLOW
        try:
            log_fd = os.open(str(self._log_path), log_flags, 0o600)
        except OSError:
            # Path is a symlink (or otherwise unsafe) — refuse and bail.
            raise RuntimeError(
                f"Refusing to open log file at {self._log_path}: not a regular file."
            )
        self._log_file = os.fdopen(log_fd, "wb", buffering=0)

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
            # New process group so a Ctrl+C delivered to Maya's console
            # doesn't propagate to ComfyUI. Note: this does NOT fully
            # detach — if Maya is force-killed, the OS will usually clean
            # up the child too. Use DETACHED_PROCESS if you want true
            # outliving-Maya behaviour.
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        self._proc = subprocess.Popen(cmd, **kwargs)
        # Same NOFOLLOW guard on the pid file.
        pid_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            pid_flags |= os.O_NOFOLLOW
        try:
            pid_fd = os.open(str(self._pid_file), pid_flags, 0o600)
            with os.fdopen(pid_fd, "w") as fh:
                fh.write(str(self._proc.pid))
        except OSError:
            # Non-fatal: kill still works via port discovery.
            pass

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
        return _find_listening_pid(port)

    def _read_saved_pid(self) -> Optional[int]:
        """Return the saved pid only if it is actually serving our port.

        The pid file is now in a per-user dir, but cross-checking the port
        is still the authoritative test: it rejects stale pids after a
        crash/reboot, and prevents Kill from ever terminating a process
        that isn't ComfyUI on this port.
        """
        try:
            if not self._pid_file.exists():
                return None
            saved = int(self._pid_file.read_text().strip())
        except Exception:
            return None
        listening = self._find_pid_on_port(self.port)
        if listening is not None and listening == saved:
            return saved
        return None

    def _terminate_pid(self, pid: int) -> None:
        """Terminate *pid* only if it is the process currently bound to our port.

        Defence in depth: callers already pre-verify via `_read_saved_pid`
        or `_find_pid_on_port`, but a race window exists between those
        checks and the actual kill. Re-checking here closes it.
        """
        listening = self._find_pid_on_port(self.port)
        if listening is None or listening != pid:
            return
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
