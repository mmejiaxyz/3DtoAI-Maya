"""Gemini 2.5 Flash Image (nano-banana) image-to-image client.

Takes a viewport snapshot + a text prompt, returns the generated image
as PNG bytes. Synchronous; the UI runs it off the main thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shoot.settings import get_api_key, get_model


@dataclass
class ShotRequest:
    prompt: str
    reference_png: bytes
    aspect_ratio: str = "16:9"       # informational; sent in prompt
    focal_length_mm: Optional[int] = 35
    aperture: Optional[float] = 2.8


@dataclass
class ShotResult:
    png: bytes
    mime: str = "image/png"


def _compose_prompt(req: ShotRequest) -> str:
    lens_bits = []
    if req.focal_length_mm:
        lens_bits.append(f"{req.focal_length_mm}mm lens")
    if req.aperture:
        lens_bits.append(f"f/{req.aperture}")
    lens = ", ".join(lens_bits)
    aspect = f"{req.aspect_ratio} aspect ratio"
    suffix = f"Photographic. {aspect}. {lens}." if lens else f"Photographic. {aspect}."
    return f"{req.prompt.strip()}\n\nUse the attached image strictly as the compositional layout and camera angle. {suffix}"


def generate(req: ShotRequest) -> ShotResult:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "No Gemini API key set. Set GEMINI_API_KEY or use the panel's settings."
        )

    from google import genai
    from google.genai import types as gtypes

    client = genai.Client(api_key=api_key)

    parts = [
        gtypes.Part.from_bytes(data=req.reference_png, mime_type="image/png"),
        gtypes.Part.from_text(_compose_prompt(req)),
    ]

    response = client.models.generate_content(
        model=get_model(),
        contents=parts,
    )

    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            inline = getattr(part, "inline_data", None)
            if inline and inline.data:
                return ShotResult(png=inline.data, mime=inline.mime_type or "image/png")

    raise RuntimeError("Gemini returned no image in response")
