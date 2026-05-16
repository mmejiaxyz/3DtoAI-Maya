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
COMFY_MODEL_UNET         = "flux-2-klein-9b-fp8.safetensors"
COMFY_MODEL_VAE          = "full_encoder_small_decoder.safetensors"
COMFY_MODEL_TEXT_ENCODER = "qwen_3_8b_fp8mixed.safetensors"

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
            return str(cmds.optionVar(q=ov_key) or default)
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
