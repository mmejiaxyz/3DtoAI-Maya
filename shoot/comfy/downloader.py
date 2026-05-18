"""Model downloader for Shoot.

Downloads FLUX.1 Kontext FP8 and its accessories directly into the
ComfyUI models/ folder tree.

For HuggingFace-hosted models the downloader uses ``huggingface_hub``
which transparently handles XET storage, resumable transfers, and gated
repos.  A plain ``urllib`` fallback is kept for any direct-URL model.

HuggingFace gated models (e.g. the FLUX.1 dev VAE) require:
  1. Accept the model license on huggingface.co.
  2. A HuggingFace access token (Settings → Access Tokens → New token,
     role: Read).

The token is stored in Maya's optionVar under "shoot_hf_token".
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


# ── Model catalogue ───────────────────────────────────────────────────────────

@dataclass
class ModelSpec:
    key:          str
    display_name: str
    filename:     str
    subfolder:    str           # relative to ComfyUI install dir
    url:          str           # direct URL (used when hf_repo_id is empty)
    size_bytes:   int           # approximate; 0 = unknown
    gated:        bool = False  # True = needs HF token
    hf_repo_id:  str = ""       # e.g. "Comfy-Org/flux1-kontext-dev_ComfyUI"
    hf_file:     str = ""       # path of the file within the HF repo

    @property
    def size_label(self) -> str:
        if self.size_bytes <= 0:
            return "?"
        gb = self.size_bytes / 1_073_741_824
        if gb >= 1:
            return f"{gb:.1f} GB"
        return f"{self.size_bytes / 1_048_576:.0f} MB"

    def dest_path(self, comfy_dir: Path) -> Path:
        return comfy_dir / self.subfolder / self.filename


# Canonical model lists.
#
#  • MODELS               — required for the default Klein flow (auto-DL).
#  • MODELS_FLUX2_DEV     — for the Flux 2 dev mode (high-quality alternate).
#  • MODELS_MULTIANGLE    — for the Qwen multi-angle mode (camera-driven).
#
# All are exposed via MODELS_ALL in the Models tab — the panel groups them
# but they share the same presence-check + download code paths. HF repo
# IDs are best-effort; if a repo path drifts, override the filename via
# the SHOOT_COMFY_MODEL_* env vars, or drop the file in manually.
MODELS: list[ModelSpec] = [
    ModelSpec(
        key="unet",
        display_name="FLUX.2 Klein 9B KV FP8  (UNet, ~9 GB)  ⚠ BFL license",
        filename="flux-2-klein-9b-kv-fp8.safetensors",
        subfolder="models/diffusion_models",
        url="",
        size_bytes=9_000_000_000,
        gated=True,
        hf_repo_id="black-forest-labs/FLUX.2-klein-9b-kv-fp8",
        hf_file="flux-2-klein-9b-kv-fp8.safetensors",
    ),
    ModelSpec(
        key="text_encoder",
        display_name="Qwen 3 8B FP8  (text encoder, ~8 GB)",
        filename="qwen_3_8b_fp8mixed.safetensors",
        subfolder="models/text_encoders",
        url="",
        size_bytes=8_000_000_000,
        gated=False,
        hf_repo_id="Comfy-Org/vae-text-encorder-for-flux-klein-9b",
        hf_file="split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors",
    ),
    ModelSpec(
        key="vae",
        display_name="FLUX.2 Klein VAE full_encoder_small_decoder  (~335 MB)",
        filename="full_encoder_small_decoder.safetensors",
        subfolder="models/vae",
        url="",
        size_bytes=335_000_000,
        gated=False,
        hf_repo_id="Comfy-Org/vae-text-encorder-for-flux-klein-9b",
        hf_file="split_files/vae/full_encoder_small_decoder.safetensors",
    ),
]


# ── FLUX.2 dev (high-quality mode) ─────────────────────────────────────────────
# Shares the FLUX.2 Klein VAE; only the UNet, CLIP, and Turbo LoRA are new.
MODELS_FLUX2_DEV: list[ModelSpec] = [
    ModelSpec(
        key="flux2_dev_unet",
        display_name="FLUX.2 dev FP8 mixed  (UNet, ~12 GB)  ⚠ BFL license",
        filename="flux2_dev_fp8mixed.safetensors",
        subfolder="models/diffusion_models",
        url="",
        size_bytes=12_000_000_000,
        gated=True,
        hf_repo_id="Comfy-Org/FLUX.2-dev_ComfyUI",
        hf_file="split_files/diffusion_models/flux2_dev_fp8mixed.safetensors",
    ),
    ModelSpec(
        key="flux2_dev_clip",
        display_name="Mistral 3 Small (FLUX.2 dev CLIP, bf16, ~12 GB)",
        filename="mistral_3_small_flux2_bf16.safetensors",
        subfolder="models/text_encoders",
        url="",
        size_bytes=12_000_000_000,
        gated=False,
        hf_repo_id="Comfy-Org/FLUX.2-dev_ComfyUI",
        hf_file="split_files/text_encoders/mistral_3_small_flux2_bf16.safetensors",
    ),
    ModelSpec(
        key="flux2_turbo_lora",
        display_name="FLUX.2 Turbo LoRA (8 steps, ~600 MB)",
        filename="Flux_2-Turbo-LoRA_comfyui.safetensors",
        subfolder="models/loras",
        url="",
        size_bytes=600_000_000,
        gated=False,
        hf_repo_id="Comfy-Org/FLUX.2-dev_ComfyUI",
        hf_file="split_files/loras/Flux_2-Turbo-LoRA_comfyui.safetensors",
    ),
]


# ── Qwen multi-angle (camera-driven mode) ─────────────────────────────────────
MODELS_MULTIANGLE: list[ModelSpec] = [
    ModelSpec(
        key="qwen_edit_unet",
        display_name="Qwen-Image-Edit 2509 FP8 e4m3fn  (UNet, ~10 GB)",
        filename="qwen_image_edit_2509_fp8_e4m3fn.safetensors",
        subfolder="models/diffusion_models",
        url="",
        size_bytes=10_000_000_000,
        gated=False,
        hf_repo_id="Comfy-Org/Qwen-Image-Edit_ComfyUI",
        hf_file="split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors",
    ),
    ModelSpec(
        key="qwen_clip",
        display_name="Qwen 2.5-VL 7B FP8 scaled  (CLIP, ~8 GB)",
        filename="qwen_2.5_vl_7b_fp8_scaled.safetensors",
        subfolder="models/text_encoders",
        url="",
        size_bytes=8_000_000_000,
        gated=False,
        hf_repo_id="Comfy-Org/Qwen-Image_ComfyUI",
        hf_file="split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
    ),
    ModelSpec(
        key="qwen_vae",
        display_name="Qwen Image VAE  (~250 MB)",
        filename="qwen_image_vae.safetensors",
        subfolder="models/vae",
        url="",
        size_bytes=250_000_000,
        gated=False,
        hf_repo_id="Comfy-Org/Qwen-Image_ComfyUI",
        hf_file="split_files/vae/qwen_image_vae.safetensors",
    ),
    ModelSpec(
        key="qwen_lightning_lora",
        display_name="Qwen-Edit 2509 Lightning 4-step LoRA  (~700 MB)",
        filename="Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors",
        subfolder="models/loras",
        url="",
        size_bytes=700_000_000,
        gated=False,
        hf_repo_id="lightx2v/Qwen-Image-Edit-2509-Lightning",
        hf_file="Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors",
    ),
    ModelSpec(
        key="qwen_multiangle_lora",
        display_name="Qwen-Edit 2509 Multiple-Angles LoRA  (~700 MB)",
        filename="Qwen-Edit-2509-Multiple-angles.safetensors",
        subfolder="models/loras",
        url="",
        size_bytes=700_000_000,
        gated=False,
        hf_repo_id="dx8152/Qwen-Edit-2509-Multiple-angles",
        hf_file="Qwen-Edit-2509-Multiple-angles.safetensors",
    ),
]


MODELS_ALL: list[ModelSpec] = MODELS + MODELS_FLUX2_DEV + MODELS_MULTIANGLE
MODELS_BY_KEY: dict[str, ModelSpec] = {m.key: m for m in MODELS_ALL}


# ── Status check ──────────────────────────────────────────────────────────────

def model_present(spec: ModelSpec, comfy_dir: Path) -> bool:
    p = spec.dest_path(comfy_dir)
    return p.exists() and p.stat().st_size > 1_000_000  # >1 MB = not a stub


def all_present(comfy_dir: Path) -> bool:
    return all(model_present(m, comfy_dir) for m in MODELS)


# ── Errors ────────────────────────────────────────────────────────────────────

class DownloadError(RuntimeError):
    pass


class TokenRequiredError(DownloadError):
    """Raised when a HuggingFace token is needed but not provided."""
    pass


# ── Download implementations ──────────────────────────────────────────────────

def _largest_file_in(directory: Path) -> int:
    """Return the size in bytes of the largest file currently in *directory*."""
    largest = 0
    try:
        for p in directory.rglob("*"):
            if p.is_file():
                try:
                    largest = max(largest, p.stat().st_size)
                except OSError:
                    pass
    except OSError:
        pass
    return largest


def _download_hf(
    spec: ModelSpec,
    comfy_dir: Path,
    hf_token: Optional[str],
    progress_cb: Optional[Callable[[int, int], None]],
    status_cb: Optional[Callable[[str], None]],
    cancelled: Optional[Callable[[], bool]],
) -> None:
    """Download via huggingface_hub (handles XET storage, gating, resuming).

    Runs hf_hub_download in a daemon thread and polls the staging directory
    every second to report real byte-level progress via *progress_cb*.
    """
    import threading
    import time

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise DownloadError(
            "huggingface_hub is not installed.\n"
            "Run:  mayapy -m pip install 'huggingface_hub>=0.20'"
        )

    dest = spec.dest_path(comfy_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)

    staging = dest.parent / ".hf_staging"
    staging.mkdir(parents=True, exist_ok=True)

    if status_cb:
        status_cb(f"Connecting… {spec.display_name}")

    # ── Run hf_hub_download in a background thread ────────────────────
    _result: list = [None]
    _error:  list = [None]

    def _worker():
        try:
            try:
                _result[0] = hf_hub_download(
                    repo_id=spec.hf_repo_id,
                    filename=spec.hf_file,
                    token=hf_token or None,
                    local_dir=str(staging),
                    local_dir_use_symlinks=False,
                )
            except TypeError:
                # huggingface_hub >= 0.25 removed local_dir_use_symlinks
                _result[0] = hf_hub_download(
                    repo_id=spec.hf_repo_id,
                    filename=spec.hf_file,
                    token=hf_token or None,
                    local_dir=str(staging),
                )
        except Exception as exc:
            _error[0] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    # ── Poll staging dir for real progress ────────────────────────────
    expected = spec.size_bytes  # may be 0 if unknown
    while thread.is_alive():
        if cancelled and cancelled():
            # hf_hub_download has no cancel API. The worker is a daemon
            # thread, so it will keep writing until it finishes (or Maya
            # exits). DO NOT rmtree the staging dir here — wiping it while
            # the worker still holds open handles corrupts state on Windows
            # and races with the worker's own writes. Leave staging on
            # disk; the next download attempt will resume from cache.
            raise DownloadError(
                "Download cancelled. The HuggingFace client cannot be "
                "interrupted mid-chunk; the background transfer will stop "
                "on the next file boundary or when Maya exits."
            )

        downloaded = _largest_file_in(staging)
        if progress_cb:
            progress_cb(float(downloaded), float(expected))
        elif status_cb and downloaded > 0:
            status_cb(f"{downloaded / 1_073_741_824:.2f} GB…")

        time.sleep(1.0)

    thread.join()

    # ── Handle errors ─────────────────────────────────────────────────
    if _error[0] is not None:
        exc = _error[0]
        shutil.rmtree(str(staging), ignore_errors=True)
        msg = str(exc).lower()
        if any(k in msg for k in ("401", "403", "gated", "forbidden", "unauthorized", "access")):
            raise TokenRequiredError(
                f"{spec.display_name} requires a HuggingFace token.\n"
                "Accept the model license on huggingface.co and paste your "
                "token in the Models tab."
            ) from exc
        raise DownloadError(f"HuggingFace download failed: {exc}") from exc

    # Move from staging tree to the intended destination.
    # hf_hub_download places the file at staging / spec.hf_file,
    # which may include sub-directories (e.g. split_files/diffusion_models/…).
    cached_path = Path(_result[0])
    if cached_path.resolve() != dest.resolve():
        shutil.move(str(cached_path), str(dest))

    # Clean up staging dir (may contain .huggingface metadata folders)
    shutil.rmtree(str(staging), ignore_errors=True)

    if status_cb:
        status_cb(f"{spec.display_name} — done.")


def _download_urllib(
    spec: ModelSpec,
    comfy_dir: Path,
    hf_token: Optional[str],
    progress_cb: Optional[Callable[[int, int], None]],
    cancelled: Optional[Callable[[], bool]],
) -> None:
    """Download via urllib for plain direct URLs."""
    import urllib.request
    import urllib.error

    dest = spec.dest_path(comfy_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)

    tmp = dest.with_suffix(dest.suffix + ".part")

    headers: dict[str, str] = {"User-Agent": "shoot-maya-plugin/0.1"}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    resume_from = tmp.stat().st_size if tmp.exists() else 0
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"

    req = urllib.request.Request(spec.url, headers=headers)

    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise TokenRequiredError(
                f"{spec.display_name} is a gated model. "
                "Accept the license at huggingface.co and enter your HF access token."
            ) from exc
        raise DownloadError(f"HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(f"Network error: {exc.reason}") from exc

    # If we asked for a range but the server replied 200 (full body),
    # appending would corrupt the file by stitching old partial bytes
    # to a fresh full body. Restart from scratch instead.
    server_honored_range = resume_from > 0 and getattr(response, "status", 200) == 206
    if resume_from > 0 and not server_honored_range:
        resume_from = 0

    raw_total = response.headers.get("Content-Length") or response.headers.get("content-length")
    if raw_total:
        total = int(raw_total) + resume_from  # Range responses report remaining bytes
    else:
        total = 0

    downloaded = resume_from
    chunk_size = 1 << 20  # 1 MB

    mode = "ab" if resume_from else "wb"
    with open(tmp, mode) as fh:
        while True:
            if cancelled and cancelled():
                raise DownloadError("Download cancelled.")
            chunk = response.read(chunk_size)
            if not chunk:
                break
            fh.write(chunk)
            downloaded += len(chunk)
            if progress_cb:
                progress_cb(downloaded, total)

    if spec.size_bytes > 0:
        ratio = downloaded / spec.size_bytes
        if ratio < 0.90:
            tmp.unlink(missing_ok=True)
            raise DownloadError(
                f"{spec.display_name}: download too small "
                f"({downloaded / 1e9:.2f} GB, expected ~{spec.size_bytes / 1e9:.2f} GB)."
            )

    tmp.rename(dest)


# ── Public entry point ────────────────────────────────────────────────────────

def download_model(
    spec: ModelSpec,
    comfy_dir: Path,
    hf_token: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Download *spec* into the correct ComfyUI subfolder.

    Uses huggingface_hub when ``spec.hf_repo_id`` is set — this handles
    XET-backed large files transparently.  Falls back to plain urllib for
    direct-URL models.

    Parameters
    ----------
    spec        : ModelSpec to download.
    comfy_dir   : ComfyUI install directory.
    hf_token    : HuggingFace access token (required for gated models).
    progress_cb : Called with (bytes_done, total_bytes) — urllib path only.
    cancelled   : Callable returning True to abort — urllib path only.
    status_cb   : Called with a status string — HF path, shown in the panel.
    """
    if spec.hf_repo_id:
        _download_hf(spec, comfy_dir, hf_token, progress_cb, status_cb, cancelled)
    else:
        _download_urllib(spec, comfy_dir, hf_token, progress_cb, cancelled)
