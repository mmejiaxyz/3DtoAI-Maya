"""Plugin settings: API key, model names, defaults.

Reads from environment first, then Maya optionVar so users can persist
the key inside Maya without leaking it into a .env beside the scene.
"""
from __future__ import annotations

import os
from typing import Optional

OPTVAR_API_KEY = "shoot_gemini_api_key"
OPTVAR_MODEL = "shoot_gemini_model"

DEFAULT_MODEL = "gemini-2.5-flash-image"


def get_api_key() -> Optional[str]:
    env = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if env:
        return env
    try:
        from maya import cmds
        if cmds.optionVar(exists=OPTVAR_API_KEY):
            return cmds.optionVar(q=OPTVAR_API_KEY) or None
    except Exception:
        pass
    return None


def set_api_key(key: str) -> None:
    from maya import cmds
    cmds.optionVar(sv=(OPTVAR_API_KEY, key))


def get_model() -> str:
    try:
        from maya import cmds
        if cmds.optionVar(exists=OPTVAR_MODEL):
            return cmds.optionVar(q=OPTVAR_MODEL) or DEFAULT_MODEL
    except Exception:
        pass
    return DEFAULT_MODEL
