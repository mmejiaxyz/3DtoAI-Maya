"""Local ComfyUI image-edit inference for Shoot.

Single-image generation: one viewport snapshot → one output image.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from shoot.comfy.client import ComfyClient
from shoot.comfy.workflow import build_flux2_workflow
from shoot.settings import get_setting as _settings_get


@dataclass
class ShotRequest:
    prompt: str
    reference_png: bytes
    width: int = 1024
    height: int = 1024
    aspect_ratio: str = "16:9"
    seed: int = -1


@dataclass
class ShotResult:
    png: bytes
    mime: str = "image/png"


def generate(
    req: ShotRequest,
    status_cb: Optional[Callable[[str], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> ShotResult:
    client = _client()
    _assert_alive(client)

    if status_cb:
        status_cb("Uploading reference...")
    image_filename = client.upload_image(req.reference_png, "shoot_ref.png")

    workflow = build_flux2_workflow(
        image_filename=image_filename,
        prompt=req.prompt.strip(),
        **_model_kwargs(),
        seed=req.seed,
    )

    if status_cb:
        status_cb("Generating...")
    prompt_id = client.queue_prompt(workflow)
    png = client.wait_for_image(
        prompt_id,
        status_cb=status_cb,
        cancelled=cancelled,
    )
    return ShotResult(png=png)


def _client() -> ComfyClient:
    host = _settings_get("COMFY_HOST", "127.0.0.1")
    port = int(_settings_get("COMFY_PORT", 8188))
    return ComfyClient(host=host, port=port)


def _assert_alive(client: ComfyClient) -> None:
    if not client.is_alive():
        raise RuntimeError(
            "ComfyUI is not running. Click Start ComfyUI, or run "
            "`python main.py` inside your ComfyUI directory."
        )


def _model_kwargs() -> dict:
    return dict(
        unet_name=_settings_get("COMFY_MODEL_UNET", "flux-2-klein-9b-kv-fp8.safetensors"),
        text_encoder=_settings_get("COMFY_MODEL_TEXT_ENCODER", "qwen_3_8b_fp8mixed.safetensors"),
        vae_name=_settings_get("COMFY_MODEL_VAE", "full_encoder_small_decoder.safetensors"),
        steps=int(_settings_get("COMFY_STEPS", 4)),
        guidance=float(_settings_get("COMFY_GUIDANCE", 1.0)),
    )
