"""Plugin settings: model names, defaults.

Reads from environment first, then Maya optionVar so users can persist
values inside Maya without leaking them into files beside the scene.
"""
from __future__ import annotations

import os
from typing import Optional

# ── ComfyUI ───────────────────────────────────────────────────────────────────

# Server
COMFY_HOST = "127.0.0.1"
COMFY_PORT = 8188

# Model filenames — must match what you placed in ComfyUI's models/ folders.
# Override per-machine via Maya optionVar (see SETUP.md).
COMFY_MODEL_UNET         = "flux-2-klein-9b-kv-fp8.safetensors"
COMFY_MODEL_VAE          = "full_encoder_small_decoder.safetensors"
COMFY_MODEL_TEXT_ENCODER = "qwen_3_8b_fp8mixed.safetensors"

# FLUX.2 dev (high-quality mode)
COMFY_MODEL_FLUX2_DEV_UNET   = "flux2_dev_fp8mixed.safetensors"
COMFY_MODEL_FLUX2_DEV_CLIP   = "mistral_3_small_flux2_bf16.safetensors"
COMFY_MODEL_FLUX2_TURBO_LORA = "Flux_2-Turbo-LoRA_comfyui.safetensors"
COMFY_FLUX2_DEV_STEPS_TURBO  = 8
COMFY_FLUX2_DEV_STEPS_FULL   = 20
COMFY_FLUX2_DEV_GUIDANCE     = 4.0

# Qwen multi-angle (camera-driven mode)
COMFY_MODEL_QWEN_EDIT_UNET       = "qwen_image_edit_2509_fp8_e4m3fn.safetensors"
COMFY_MODEL_QWEN_CLIP            = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
COMFY_MODEL_QWEN_VAE             = "qwen_image_vae.safetensors"
COMFY_MODEL_QWEN_MULTIANGLE_LORA = "Qwen-Edit-2509-Multiple-angles.safetensors"
COMFY_MODEL_QWEN_LIGHTNING_LORA  = "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors"
COMFY_QWEN_STEPS                 = 4

# Generation defaults
COMFY_STEPS = 4  # Distilled Klein runs in 4 steps


def get_setting(key: str, default: str = "") -> str:
    """Read a setting from environment or Maya optionVar."""
    env_key = f"SHOOT_{key}"
    env = os.environ.get(env_key)
    if env:
        return env

    try:
        from maya import cmds
        ov_key = f"shoot_{key.lower()}"
        if cmds.optionVar(exists=ov_key):
            # Preserve legitimate falsy values like 0 or "" — `or default`
            # would silently swap them for the default.
            value = cmds.optionVar(q=ov_key)
            if value is None:
                return default
            return str(value)
    except Exception:
        pass
    return default


def get_comfy_dir() -> Optional[str]:
    """Return the ComfyUI install directory."""
    try:
        from maya import cmds
        key = "shoot_comfy_dir"
        if cmds.optionVar(exists=key):
            return cmds.optionVar(q=key) or None
    except Exception:
        pass
    return None
