"""ComfyUI API workflows: FLUX.2 Klein, FLUX.2 dev, and Qwen Edit multi-angle.

All three workflows take a single reference image and produce a single
output image — the panel never fans out to a batch.

  • Klein  — distilled, 4 steps, CFGGuider, cheap. Default fast mode.
  • Dev    — full Flux 2, BasicGuider + FluxGuidance, optional Turbo
             LoRA for 8-step inference (default) instead of 20.
  • Qwen   — Qwen-Image-Edit-2509 + Lightning 4-step LoRA + Multiple-Angles
             LoRA. Used by the multi-angle flow where the camera-delta
             vs the anchor is encoded as the prompt.
"""
from __future__ import annotations

import random


def build_flux2_workflow(
    prompt: str,
    image_filename: str,
    steps: int = 4,
    guidance: float = 1.0,
    seed: int = -1,
    unet_name: str = "flux-2-klein-9b-kv-fp8.safetensors",
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


def build_flux2_dev_workflow(
    prompt: str,
    image_filename: str,
    use_turbo_lora: bool = True,
    steps_turbo: int = 8,
    steps_full: int = 20,
    guidance: float = 4.0,
    seed: int = -1,
    unet_name: str = "flux2_dev_fp8mixed.safetensors",
    turbo_lora_name: str = "Flux_2-Turbo-LoRA_comfyui.safetensors",
    text_encoder: str = "mistral_3_small_flux2_bf16.safetensors",
    vae_name: str = "full_encoder_small_decoder.safetensors",
) -> dict:
    """FLUX.2 dev image-edit graph.

    Mirrors the official Flux 2 dev image-edit subgraph:
      • UNETLoader (+ optional Turbo LoRA on the model branch)
      • CLIPLoader (Mistral 3 Small) → CLIPTextEncode → FluxGuidance(=4)
      • Reference VAEEncode → ReferenceLatent (positive only — no negative,
        BasicGuider is single-conditioning)
      • Flux2Scheduler / EmptyFlux2LatentImage drive shape and sigmas
      • SamplerCustomAdvanced(euler) → VAEDecode → SaveImage

    With ``use_turbo_lora=True`` (default) inference runs at 8 steps; flip
    off for full-quality 20-step inference.
    """
    if seed < 0:
        seed = random.randint(0, 2**32 - 1)
    steps = steps_turbo if use_turbo_lora else steps_full

    # Node "20" is the LoRA-loaded model branch when turbo is on; the rest
    # of the graph reads from "20" so flipping turbo only rewires one edge.
    model_branch_source = "20" if use_turbo_lora else "1"

    workflow: dict = {
        "1": {
            "class_type": "UNETLoader",
            "_meta": {"title": "Load Diffusion Model (Flux 2 dev)"},
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "_meta": {"title": "Load CLIP (Mistral 3 Small)"},
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
            "_meta": {"title": "Scale Reference (1 MP, lanczos)"},
            "inputs": {
                "image": ["4", 0],
                "upscale_method": "lanczos",
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
            "_meta": {"title": "VAE Encode (reference)"},
            "inputs": {"pixels": ["5", 0], "vae": ["3", 0]},
        },
        "8": {
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Positive Prompt"},
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        "9": {
            "class_type": "FluxGuidance",
            "_meta": {"title": "Flux Guidance"},
            "inputs": {"guidance": guidance, "conditioning": ["8", 0]},
        },
        "10": {
            "class_type": "ReferenceLatent",
            "_meta": {"title": "Positive Reference"},
            "inputs": {"conditioning": ["9", 0], "latent": ["7", 0]},
        },
        "11": {
            "class_type": "BasicGuider",
            "_meta": {"title": "Basic Guider"},
            "inputs": {
                "model": [model_branch_source, 0],
                "conditioning": ["10", 0],
            },
        },
        "12": {
            "class_type": "EmptyFlux2LatentImage",
            "_meta": {"title": "Empty Latent"},
            "inputs": {"width": ["6", 0], "height": ["6", 1], "batch_size": 1},
        },
        "13": {
            "class_type": "Flux2Scheduler",
            "_meta": {"title": "Flux 2 Scheduler"},
            "inputs": {"steps": steps, "width": ["6", 0], "height": ["6", 1]},
        },
        "14": {
            "class_type": "KSamplerSelect",
            "_meta": {"title": "Sampler"},
            "inputs": {"sampler_name": "euler"},
        },
        "15": {
            "class_type": "RandomNoise",
            "_meta": {"title": "Noise"},
            "inputs": {"noise_seed": seed},
        },
        "16": {
            "class_type": "SamplerCustomAdvanced",
            "_meta": {"title": "Sample"},
            "inputs": {
                "noise": ["15", 0],
                "guider": ["11", 0],
                "sampler": ["14", 0],
                "sigmas": ["13", 0],
                "latent_image": ["12", 0],
            },
        },
        "17": {
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"},
            "inputs": {"samples": ["16", 0], "vae": ["3", 0]},
        },
        "18": {
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image"},
            "inputs": {"images": ["17", 0], "filename_prefix": "Shoot_Flux2"},
        },
    }

    if use_turbo_lora:
        workflow["20"] = {
            "class_type": "LoraLoaderModelOnly",
            "_meta": {"title": "Flux 2 Turbo LoRA (8 steps)"},
            "inputs": {
                "lora_name": turbo_lora_name,
                "strength_model": 1.0,
                "model": ["1", 0],
            },
        }

    return workflow


def build_qwen_multiangle_workflow(
    angle_prompt: str,
    image_filename: str,
    seed: int = -1,
    steps: int = 4,
    unet_name: str = "qwen_image_edit_2509_fp8_e4m3fn.safetensors",
    text_encoder: str = "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    vae_name: str = "qwen_image_vae.safetensors",
    multiangle_lora: str = "Qwen-Edit-2509-Multiple-angles.safetensors",
    lightning_lora: str = "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors",
    multiangle_strength: float = 1.0,
    lightning_strength: float = 1.0,
) -> dict:
    """Single-branch Qwen-Image-Edit 2509 graph with the Multiple-Angles LoRA.

    Mirrors one branch of the 1-click multi-angle template, but with a
    *continuous-degree* prompt (e.g. "Rotate the camera 37 degrees to the
    right and tilt 12 degrees up.") instead of one of the 8 trained presets.
    The LoRA stack is base → Lightning 4-step → Multiple-Angles, wrapped in
    ModelSamplingAuraFlow(shift=3) + CFGNorm(strength=1). The reference
    image is fed into TextEncodeQwenImageEditPlus as image1 (both positive
    and negative branches), and re-used as the VAE-encoded latent.
    """
    if seed < 0:
        seed = random.randint(0, 2**32 - 1)

    return {
        "1": {
            "class_type": "UNETLoader",
            "_meta": {"title": "Load Diffusion Model (Qwen Edit 2509)"},
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "LoraLoaderModelOnly",
            "_meta": {"title": "Lightning 4-step LoRA"},
            "inputs": {
                "lora_name": lightning_lora,
                "strength_model": lightning_strength,
                "model": ["1", 0],
            },
        },
        "3": {
            "class_type": "LoraLoaderModelOnly",
            "_meta": {"title": "Multiple-Angles LoRA"},
            "inputs": {
                "lora_name": multiangle_lora,
                "strength_model": multiangle_strength,
                "model": ["2", 0],
            },
        },
        "4": {
            "class_type": "ModelSamplingAuraFlow",
            "_meta": {"title": "ModelSamplingAuraFlow"},
            "inputs": {"shift": 3, "model": ["3", 0]},
        },
        "5": {
            "class_type": "CFGNorm",
            "_meta": {"title": "CFGNorm"},
            "inputs": {"strength": 1, "model": ["4", 0]},
        },
        "6": {
            "class_type": "CLIPLoader",
            "_meta": {"title": "Load CLIP (Qwen 2.5-VL)"},
            "inputs": {"clip_name": text_encoder, "type": "qwen_image", "device": "default"},
        },
        "7": {
            "class_type": "VAELoader",
            "_meta": {"title": "Load Qwen Image VAE"},
            "inputs": {"vae_name": vae_name},
        },
        "8": {
            "class_type": "LoadImage",
            "_meta": {"title": "Load Image"},
            "inputs": {"image": image_filename},
        },
        "9": {
            "class_type": "ImageScaleToTotalPixels",
            "_meta": {"title": "Scale Reference (1 MP)"},
            "inputs": {
                "image": ["8", 0],
                "upscale_method": "nearest-exact",
                "megapixels": 1,
                "resolution_steps": 1,
            },
        },
        "10": {
            "class_type": "VAEEncode",
            "_meta": {"title": "VAE Encode"},
            "inputs": {"pixels": ["9", 0], "vae": ["7", 0]},
        },
        "11": {
            "class_type": "TextEncodeQwenImageEditPlus",
            "_meta": {"title": "Positive (camera-delta prompt)"},
            "inputs": {
                "prompt": angle_prompt,
                "clip": ["6", 0],
                "vae": ["7", 0],
                "image1": ["9", 0],
            },
        },
        "12": {
            "class_type": "TextEncodeQwenImageEditPlus",
            "_meta": {"title": "Negative (empty)"},
            "inputs": {
                "prompt": "",
                "clip": ["6", 0],
                "vae": ["7", 0],
                "image1": ["9", 0],
            },
        },
        "13": {
            "class_type": "KSampler",
            "_meta": {"title": "KSampler"},
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["5", 0],
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["10", 0],
            },
        },
        "14": {
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"},
            "inputs": {"samples": ["13", 0], "vae": ["7", 0]},
        },
        "15": {
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image"},
            "inputs": {"images": ["14", 0], "filename_prefix": "Shoot_MultiAngle"},
        },
    }
