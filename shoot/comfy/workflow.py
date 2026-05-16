"""ComfyUI API workflow for FLUX.2 Klein 9B Distilled image editing.

Matches the official 'Image Edit (Flux.2 Klein 9B Distilled)' subgraph exactly.
Single reference image → single output image.
"""
from __future__ import annotations

import random


def build_flux2_workflow(
    prompt: str,
    image_filename: str,
    steps: int = 4,
    guidance: float = 1.0,
    seed: int = -1,
    unet_name: str = "flux-2-klein-9b-fp8.safetensors",
    text_encoder: str = "qwen_3_8b_fp8mixed.safetensors",
    vae_name: str = "full_encoder_small_decoder.safetensors",
) -> dict:
    if seed < 0:
        seed = random.randint(0, 2**32 - 1)

    return {
        "1": {
            "class_type": "UNETLoader",
            "_meta": {"title": "Load Diffusion Model"},
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "_meta": {"title": "Load CLIP"},
            "inputs": {"clip_name": text_encoder, "type": "flux2", "device": "default"},
        },
        "3": {
            "class_type": "VAELoader",
            "_meta": {"title": "Load VAE"},
            "inputs": {"vae_name": vae_name},
        },
        "4": {
            "class_type": "LoadImage",
            "_meta": {"title": "Load Image"},
            "inputs": {"image": image_filename},
        },
        "5": {
            "class_type": "ImageScaleToTotalPixels",
            "_meta": {"title": "Scale Reference"},
            "inputs": {
                "image": ["4", 0],
                "upscale_method": "nearest-exact",
                "megapixels": 1,
                "resolution_steps": 1,
            },
        },
        "6": {
            "class_type": "GetImageSize",
            "_meta": {"title": "Get Image Size"},
            "inputs": {"image": ["5", 0]},
        },
        "7": {
            "class_type": "VAEEncode",
            "_meta": {"title": "VAE Encode"},
            "inputs": {"pixels": ["5", 0], "vae": ["3", 0]},
        },
        "8": {
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Positive Prompt"},
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        "9": {
            "class_type": "ConditioningZeroOut",
            "_meta": {"title": "Negative (zero out)"},
            "inputs": {"conditioning": ["8", 0]},
        },
        "10": {
            "class_type": "ReferenceLatent",
            "_meta": {"title": "Positive Reference"},
            "inputs": {"conditioning": ["8", 0], "latent": ["7", 0]},
        },
        "11": {
            "class_type": "ReferenceLatent",
            "_meta": {"title": "Negative Reference"},
            "inputs": {"conditioning": ["9", 0], "latent": ["7", 0]},
        },
        "12": {
            "class_type": "CFGGuider",
            "_meta": {"title": "CFG Guider"},
            "inputs": {
                "model": ["1", 0],
                "positive": ["10", 0],
                "negative": ["11", 0],
                "cfg": guidance,
            },
        },
        "13": {
            "class_type": "EmptyFlux2LatentImage",
            "_meta": {"title": "Empty Latent"},
            "inputs": {"width": ["6", 0], "height": ["6", 1], "batch_size": 1},
        },
        "14": {
            "class_type": "Flux2Scheduler",
            "_meta": {"title": "Flux 2 Scheduler"},
            "inputs": {"steps": steps, "width": ["6", 0], "height": ["6", 1]},
        },
        "15": {
            "class_type": "KSamplerSelect",
            "_meta": {"title": "Sampler"},
            "inputs": {"sampler_name": "euler"},
        },
        "16": {
            "class_type": "RandomNoise",
            "_meta": {"title": "Noise"},
            "inputs": {"noise_seed": seed},
        },
        "17": {
            "class_type": "SamplerCustomAdvanced",
            "_meta": {"title": "Sample"},
            "inputs": {
                "noise": ["16", 0],
                "guider": ["12", 0],
                "sampler": ["15", 0],
                "sigmas": ["14", 0],
                "latent_image": ["13", 0],
            },
        },
        "18": {
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"},
            "inputs": {"samples": ["17", 0], "vae": ["3", 0]},
        },
        "19": {
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image"},
            "inputs": {"images": ["18", 0], "filename_prefix": "Shoot"},
        },
    }
