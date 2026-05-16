# Shoot setup

## Requirements

- Maya 2027
- A working ComfyUI install
- Python dependencies from `requirements.txt`
- Enough disk/VRAM for FLUX.2 Klein 9B KV FP8

## ComfyUI

Install ComfyUI somewhere local, for example `~/ComfyUI`, and make sure this works:

```sh
python main.py
```

Open `http://127.0.0.1:8188` once to confirm ComfyUI starts.

## Maya plugin

From this repo:

```sh
python install.py
```

In Maya:

```python
import maya.cmds as cmds
cmds.loadPlugin("plugin.py")
cmds.shootOpen()
```

## Models

Open the Shoot panel, go to **Models**, set the ComfyUI path, paste a HuggingFace
read token if needed, then click **Download All Missing**.

The compact flow uses only:

- `flux-2-klein-9b-kv-fp8.safetensors`
- `qwen_3_8b_fp8mixed.safetensors`
- `full_encoder_small_decoder.safetensors`

## Daily flow

1. Frame the active Maya viewport.
2. Click **Snap Viewport**.
3. Write a prompt and optionally click **Optimize Prompt**.
4. Click **Generate Image**.
5. Save the result from inside Maya.
