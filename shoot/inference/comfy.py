"""Local ComfyUI image-edit inference for Shoot.

One snap → one output image, dispatched to one of three workflows
based on ``ShotRequest.mode``:

  • ``"klein"``      — FLUX.2 Klein 9B Distilled (default, fast)
  • ``"flux2_dev"``  — FLUX.2 dev (high quality, optional Turbo LoRA)
  • ``"multiangle"`` — Qwen-Image-Edit 2509 + Multiple-Angles LoRA;
                      the prompt is a continuous-degree imperative
                      encoding the camera-delta vs the anchor pose.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from shoot.comfy.client import ComfyClient
from shoot.comfy.workflow import (
    build_flux2_workflow,
    build_flux2_dev_workflow,
    build_qwen_multiangle_workflow,
)
from shoot.settings import get_setting as _settings_get


MODE_KLEIN      = "klein"
MODE_FLUX2_DEV  = "flux2_dev"
MODE_MULTIANGLE = "multiangle"

# Friendly labels for the UI dropdown. Keep order stable — the panel
# stores selection as an integer index.
MODES_ORDERED = [
    (MODE_KLEIN,      "FLUX 2 Klein (fast, 4 steps)"),
    (MODE_FLUX2_DEV,  "FLUX 2 dev (high quality)"),
    (MODE_MULTIANGLE, "Multi-angle (camera-driven)"),
]


@dataclass
class ShotRequest:
    prompt:         str
    reference_png:  bytes
    width:          int = 1024
    height:         int = 1024
    aspect_ratio:   str = "16:9"
    seed:           int = -1
    mode:           str = MODE_KLEIN
    # Only used when mode == MODE_FLUX2_DEV. When True the workflow loads
    # the Flux 2 Turbo LoRA and runs 8 steps; when False it runs 20 steps.
    use_turbo_lora: bool = True


@dataclass
class ShotResult:
    png:  bytes
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

    if req.mode == MODE_FLUX2_DEV:
        workflow = build_flux2_dev_workflow(
            image_filename=image_filename,
            prompt=req.prompt.strip(),
            use_turbo_lora=req.use_turbo_lora,
            seed=req.seed,
            **_dev_model_kwargs(),
        )
    elif req.mode == MODE_MULTIANGLE:
        workflow = build_qwen_multiangle_workflow(
            image_filename=image_filename,
            angle_prompt=req.prompt.strip(),
            seed=req.seed,
            **_multiangle_model_kwargs(),
        )
    else:
        workflow = build_flux2_workflow(
            image_filename=image_filename,
            prompt=req.prompt.strip(),
            **_klein_model_kwargs(),
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


def _klein_model_kwargs() -> dict:
    return dict(
        unet_name=_settings_get("COMFY_MODEL_UNET", "flux-2-klein-9b-kv-fp8.safetensors"),
        text_encoder=_settings_get("COMFY_MODEL_TEXT_ENCODER", "qwen_3_8b_fp8mixed.safetensors"),
        vae_name=_settings_get("COMFY_MODEL_VAE", "full_encoder_small_decoder.safetensors"),
        steps=int(_settings_get("COMFY_STEPS", 4)),
        guidance=float(_settings_get("COMFY_GUIDANCE", 1.0)),
    )


def _dev_model_kwargs() -> dict:
    return dict(
        unet_name=_settings_get("COMFY_MODEL_FLUX2_DEV_UNET", "flux2_dev_fp8mixed.safetensors"),
        turbo_lora_name=_settings_get(
            "COMFY_MODEL_FLUX2_TURBO_LORA",
            "Flux_2-Turbo-LoRA_comfyui.safetensors",
        ),
        text_encoder=_settings_get(
            "COMFY_MODEL_FLUX2_DEV_CLIP",
            "mistral_3_small_flux2_bf16.safetensors",
        ),
        vae_name=_settings_get("COMFY_MODEL_VAE", "full_encoder_small_decoder.safetensors"),
        steps_turbo=int(_settings_get("COMFY_FLUX2_DEV_STEPS_TURBO", 8)),
        steps_full=int(_settings_get("COMFY_FLUX2_DEV_STEPS_FULL", 20)),
        guidance=float(_settings_get("COMFY_FLUX2_DEV_GUIDANCE", 4.0)),
    )


def _multiangle_model_kwargs() -> dict:
    return dict(
        unet_name=_settings_get(
            "COMFY_MODEL_QWEN_EDIT_UNET",
            "qwen_image_edit_2509_fp8_e4m3fn.safetensors",
        ),
        text_encoder=_settings_get(
            "COMFY_MODEL_QWEN_CLIP",
            "qwen_2.5_vl_7b_fp8_scaled.safetensors",
        ),
        vae_name=_settings_get("COMFY_MODEL_QWEN_VAE", "qwen_image_vae.safetensors"),
        multiangle_lora=_settings_get(
            "COMFY_MODEL_QWEN_MULTIANGLE_LORA",
            "Qwen-Edit-2509-Multiple-angles.safetensors",
        ),
        lightning_lora=_settings_get(
            "COMFY_MODEL_QWEN_LIGHTNING_LORA",
            "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors",
        ),
        steps=int(_settings_get("COMFY_QWEN_STEPS", 4)),
    )
