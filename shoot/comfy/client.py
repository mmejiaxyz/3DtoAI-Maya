"""ComfyUI HTTP API client.

No third-party dependencies — uses only urllib so it works inside mayapy
without any extra pip installs.
"""
from __future__ import annotations

import json
import time
import uuid
import urllib.request
import urllib.parse
import urllib.error
from typing import Callable, Optional


class ComfyClient:
    """Thin wrapper around ComfyUI's REST API (localhost:8188 by default)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8188):
        self.base = f"http://{host}:{port}"
        self.client_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def is_alive(self, timeout: float = 2.0) -> bool:
        """Return True if the ComfyUI API is responding."""
        try:
            req = urllib.request.Request(f"{self.base}/system_stats")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Image upload
    # ------------------------------------------------------------------

    def upload_image(self, png_bytes: bytes, filename: str = "shoot_ref.png") -> str:
        """POST png_bytes to /upload/image. Returns the filename ComfyUI stored it as."""
        boundary = "ShootBound" + uuid.uuid4().hex
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + png_bytes + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            f"{self.base}/upload/image",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["name"]

    # ------------------------------------------------------------------
    # Prompt queue
    # ------------------------------------------------------------------

    def queue_prompt(self, workflow: dict) -> str:
        """POST a workflow to /prompt. Returns the prompt_id string."""
        payload = json.dumps(
            {"client_id": self.client_id, "prompt": workflow}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/prompt",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())["prompt_id"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ComfyUI rejected the workflow: HTTP {exc.code} {body}") from exc

    # ------------------------------------------------------------------
    # Result polling
    # ------------------------------------------------------------------

    def _get_history(self, prompt_id: str) -> Optional[dict]:
        try:
            url = f"{self.base}/history/{urllib.parse.quote(prompt_id)}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            return data.get(prompt_id)
        except Exception:
            return None

    def _fetch_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        params = urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": folder_type}
        )
        with urllib.request.urlopen(f"{self.base}/view?{params}", timeout=60) as resp:
            return resp.read()

    def wait_for_image(
        self,
        prompt_id: str,
        poll_interval: float = 3.0,
        timeout: float = 1800.0,   # 30 min — FLUX.2 on 12 GB VRAM can take 10-15 min
        status_cb: Optional[Callable[[str], None]] = None,
    ) -> bytes:
        """Block until the queued prompt finishes. Returns the first output image as PNG bytes."""
        deadline = time.time() + timeout
        start = time.time()

        while time.time() < deadline:
            entry = self._get_history(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("completed"):
                    for node_output in entry.get("outputs", {}).values():
                        for img in node_output.get("images", []):
                            return self._fetch_image(
                                img["filename"],
                                img.get("subfolder", ""),
                                img.get("type", "output"),
                            )
                    raise RuntimeError("Job completed but no images in output — check ComfyUI logs.")
                # Report any execution error surfaced in status
                if status.get("status_str") == "error":
                    msgs = [
                        m.get("details", "") or m.get("message", "")
                        for m in status.get("messages", [])
                        if m.get("type") == "execution_error"
                    ]
                    raise RuntimeError("ComfyUI execution error: " + "; ".join(msgs))

            elapsed = int(time.time() - start)
            mins, secs = divmod(elapsed, 60)
            if status_cb:
                status_cb(f"Generating… {mins}m {secs:02d}s")
            time.sleep(poll_interval)

        raise RuntimeError(f"ComfyUI job timed out after {int(timeout // 60)} min.")
