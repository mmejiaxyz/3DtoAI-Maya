# Shoot

Autodesk Maya 2027 plugin that sends the active viewport to a local
ComfyUI server running FLUX.2 Klein 9B Distilled, and displays the
generated image in a docked panel.

![Shoot — viewport-to-still example: a stylized stone character in a mossy forest](docs/screenshots/hero-forest.png)

- **Maya:** 2027 (PySide6, Python 3.11)
- **Backend:** ComfyUI (local, HTTP on `127.0.0.1:8188`)
- **Model:** FLUX.2 Klein 9B Distilled FP8 + Qwen 3 8B text encoder
- **Platform:** Windows 11, CUDA. Tested on a 12 GB GPU.
- **Docs:** https://mmejiaxyz.github.io/3DtoAI-Maya/

---

## Example

The viewport snap on the left, the generated still on the right. The
plugin uses the snap as a reference and the prompt to describe the new
environment; the character's silhouette and material are preserved.

![Maya viewport on the left, FLUX.2 Klein render on the right](docs/screenshots/viewport-to-render.jpg)

---

## Requirements

| Component   | Version / Notes                                                    |
|-------------|--------------------------------------------------------------------|
| Maya        | 2027 (the plugin uses the `maya.api` 2.0 API and PySide6)          |
| Python      | mayapy — bundled with Maya 2027 (3.11)                             |
| ComfyUI     | Any recent build with FLUX.2 nodes (`Flux2Scheduler`, `EmptyFlux2LatentImage`, `ReferenceLatent`, `CFGGuider`) |
| Disk        | ~18 GB for the three model files                                   |
| GPU         | NVIDIA, 12 GB VRAM minimum recommended                             |
| HF token    | Required only for the gated FLUX.2 Klein UNet                      |

---

## Install

Pick one of the three paths below. All three end at the same place:
`shoot.mod` written to Maya's modules dir, `huggingface_hub` installed
into mayapy, and the **Shoot** panel open.

### Option A — drag into Maya (easiest, no terminal)

1. Download or `git clone` this repo somewhere.
2. Launch Maya 2027.
3. From your OS file explorer, drag **`DRAG_INTO_MAYA.py`** onto a Maya
   viewport.

That's it. The panel opens immediately and the plugin auto-loads on
future Maya launches. On Windows, if the file was downloaded as part
of a ZIP you may need to right-click > Properties > **Unblock** first.

### Option B — one-line installer (terminal)

```sh
git clone https://github.com/mmejiaxyz/3DtoAI-Maya.git
cd 3DtoAI-Maya
python install.py
```

`install.py` writes the `.mod` file and installs `huggingface_hub`
into mayapy. Then in Maya:

```python
import maya.cmds as cmds; cmds.loadPlugin("shoot"); cmds.shootOpen()
```

Flags: `--no-deps` skips the pip install, `--uninstall` removes the
`.mod` file.

### Option C — manual

If you'd rather not run the installer:

```sh
git clone https://github.com/mmejiaxyz/3DtoAI-Maya.git ^
  "%USERPROFILE%\Documents\maya\2027\modules\shoot"

"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" -m pip install ^
  "huggingface_hub>=0.20"
```

The repo's `shoot.mod` adds `shoot/` to `MAYA_PLUG_IN_PATH`. Load the
plugin from the Plug-in Manager or the Script Editor as in Option B.

### ComfyUI

The first time the panel opens, a **setup wizard** walks you through:

1. Detecting (or installing) ComfyUI.
2. Saving a HuggingFace read token.
3. Downloading the three FLUX.2 weights.

On Windows the wizard can install ComfyUI itself — it runs
`git clone` + `python -m venv` + `pip install -r requirements.txt`
into the path you pick, and saves it as the active `shoot_comfy_dir`.
You need `git` and a system Python (3.10+) on PATH; if either is
missing the wizard tells you what to install. On macOS / Linux the
wizard skips auto-install and asks you to point it at an existing
clone.

Skip any step to configure it later from the **Models** tab. The
wizard re-runs only on first launch; reset it by clearing the
`shoot_onboarded` Maya optionVar.

---

## Models

| Key            | Filename                                       | Size     | HF repo                                                    | Gated |
|----------------|------------------------------------------------|----------|------------------------------------------------------------|-------|
| `unet`         | `flux-2-klein-9b-kv-fp8.safetensors`           | ~9 GB    | `black-forest-labs/FLUX.2-klein-9b-kv-fp8`                 | yes   |
| `text_encoder` | `qwen_3_8b_fp8mixed.safetensors`               | ~8 GB    | `Comfy-Org/vae-text-encorder-for-flux-klein-9b`            | no    |
| `vae`          | `full_encoder_small_decoder.safetensors`       | ~335 MB  | `Comfy-Org/vae-text-encorder-for-flux-klein-9b`            | no    |

Files go to `<comfy_dir>/models/diffusion_models/`,
`<comfy_dir>/models/text_encoders/`, and `<comfy_dir>/models/vae/`
respectively. The **Models** tab in the panel downloads all three with
resume support via `huggingface_hub`.

For the gated UNet, accept the license at
[huggingface.co/black-forest-labs/FLUX.2-klein-9b-kv-fp8](https://huggingface.co/black-forest-labs/FLUX.2-klein-9b-kv-fp8)
and paste a read-scoped HF access token into the **HF Token** field.

---

## Usage

1. Open the Shoot panel (`Shoot → Open Shoot Panel`).
2. **Models** tab: confirm the ComfyUI path, download missing models.
3. **Shoot** tab: click **Start Server** to launch ComfyUI as a subprocess.
   Wait for the status dot to brighten.
4. Frame the camera in Maya's viewport.
5. Click **Snap Viewport**. The PNG appears in the *Viewport Snap* pane.
6. Type a prompt. Adjust **Aspect** and **Seed** if needed.
7. Click **Generate**. Klein runs in 4 sampling steps at `cfg=1`; on a
   12 GB card, expect ~40 s end-to-end.
8. **Save Result** writes the PNG to disk.

### The panel

Three tabs — **Shoot**, **Models**, and **Log**. Strictly monochromatic,
monospaced, hairline-ruled.

| Shoot | Models | Log |
|:-----:|:------:|:---:|
| ![Shoot tab](docs/screenshots/panel-shoot.png) | ![Models tab](docs/screenshots/panel-models.png) | ![Log tab](docs/screenshots/panel-log.png) |
| Prompt, aspect, seed, snap, generate. | Configure ComfyUI path and HF token, download the three FLUX.2 weights. | Live tail of `%TEMP%\shoot_comfy_<port>.log` — ComfyUI's stdout and stderr as it runs. |

### Kill Server

Always enabled when something is listening on port 8188. Works:

- During an in-flight generation (the polling task fails on the next
  `/history` request and the busy state clears).
- Against ComfyUI processes Shoot did not start — the manager falls
  back to `netstat -ano` (Windows) / `lsof` (Unix) to find the PID by
  port.

---

## Settings

Settings are read from environment variables first
(`SHOOT_<KEY>`), then Maya `optionVar`. The relevant keys:

| optionVar / env                  | Default                                       |
|----------------------------------|-----------------------------------------------|
| `shoot_comfy_dir` / `SHOOT_COMFY_DIR` | `%USERPROFILE%\ComfyUI`                  |
| `shoot_comfy_host` / `SHOOT_COMFY_HOST` | `127.0.0.1`                            |
| `shoot_comfy_port` / `SHOOT_COMFY_PORT` | `8188`                                 |
| `shoot_comfy_model_unet`         | `flux-2-klein-9b-fp8.safetensors`             |
| `shoot_comfy_model_text_encoder` | `qwen_3_8b_fp8mixed.safetensors`              |
| `shoot_comfy_model_vae`          | `full_encoder_small_decoder.safetensors`      |
| `shoot_comfy_steps` / `SHOOT_COMFY_STEPS` | `4`                                  |
| `shoot_comfy_guidance` / `SHOOT_COMFY_GUIDANCE` | `1.0`                          |
| `shoot_hf_token`                 | (none — required for gated UNet)              |
| `shoot_prompt`, `shoot_seed`, `shoot_lock_seed` | persisted from panel state     |

---

## Architecture

| Path                          | Role                                                                                          |
|-------------------------------|-----------------------------------------------------------------------------------------------|
| `shoot/shoot.py`              | Maya 2.0 API plugin shell. Registers `shootOpen` and a deferred-build menu item. The Plug-in Manager lists it as **shoot**. |
| `shoot/capture/viewport.py`   | `snapshot_active_view()` — reads the `M3dView` back buffer via `MImage`. Falls back to a single-frame `cmds.playblast` on driver refusal. Defensive `_active_model_panel()` for Maya 2027 panel-focus quirks. |
| `shoot/comfy/client.py`       | REST client over `urllib`. `upload_image`, `queue_prompt`, `wait_for_image` with `/history` polling and a 30-min default timeout. No third-party HTTP deps. |
| `shoot/comfy/manager.py`      | Lifecycle for the local ComfyUI subprocess. `start`, `start_and_wait`, `stop`, `kill`. Hides the console on Windows via `STARTUPINFO`. `kill()` falls back to PID-by-port lookup so externally-started servers can still be terminated. |
| `shoot/comfy/workflow.py`     | `build_flux2_workflow()` returns the FLUX.2 Klein workflow as a Python dict matching the official subgraph: 19 nodes, `ConditioningZeroOut` for negative, `EmptyFlux2LatentImage`, `Flux2Scheduler`, Euler sampler, `cfg=1`, 4 steps. |
| `shoot/comfy/downloader.py`   | `huggingface_hub` wrapper with a staging dir, byte-level progress polling on a background thread, and resume on `urllib` fallback URLs. |
| `shoot/inference/comfy.py`    | `generate(req, status_cb)` — uploads the reference, queues the workflow, polls, returns the PNG bytes. |
| `shoot/ui/shoot_panel.py`     | PySide6 panel with two tabs (Shoot, Models) on a `QThreadPool`. Maya commands that need the main thread (viewport capture, `getPanel`) run synchronously. |
| `shoot/settings.py`           | `get_setting(key, default)` reads env then `optionVar`. `get_comfy_dir()` is separate.        |

### Threading

ComfyUI calls run on `QThreadPool` workers; their status / result /
failed signals marshal back to the main thread. Anything that touches
`cmds.*` runs on the main thread directly — `cmds.getPanel(withFocus=True)`
in particular raises `"Flag withFocus must be passed a boolean argument"`
when called off-thread, despite the literal `True` being a boolean.

### Workflow node graph

```
LoadImage → ImageScaleToTotalPixels → GetImageSize
                                    ↘ VAEEncode ──→ ReferenceLatent (positive)
                                                  ↘ ReferenceLatent (negative)
CLIPTextEncode → ConditioningZeroOut → ReferenceLatent (negative)
              ↘ ReferenceLatent (positive)
                                      ↘ CFGGuider (cfg=1)
EmptyFlux2LatentImage + Flux2Scheduler + KSamplerSelect(euler) + RandomNoise
                                      → SamplerCustomAdvanced → VAEDecode → SaveImage
```

Reference scale target is 1 megapixel (`ImageScaleToTotalPixels` with
`megapixels: 1`). Output dimensions are derived from `GetImageSize` on
the scaled reference, so aspect follows the snap.

---

## Troubleshooting

**`cmds.loadPlugin("shoot")` fails with "not found on MAYA_PLUG_IN_PATH"**
The module file `shoot.mod` must be in a directory Maya scans. Default:
`%USERPROFILE%\Documents\maya\2027\modules\`. Restart Maya after
placing the module.

**Plugin loads but UI is stale after editing files**
Maya caches imported Python modules. Reload from the Script Editor:

```python
import sys, maya.cmds as cmds
for name in list(sys.modules):
    if name.startswith("shoot"):
        del sys.modules[name]
if cmds.pluginInfo("shoot", q=True, loaded=True):
    cmds.unloadPlugin("shoot")
cmds.loadPlugin("shoot")
cmds.shootOpen()
```

The panel prints `[shoot.ui.shoot_panel] loaded vN-...` on import — use
that to confirm which version is live.

**`"Flag withFocus must be passed a boolean argument"` during capture**
Means a Maya command was called from a background thread. All capture
code runs on the main thread now; if you see this, a custom workflow
is calling `snapshot_active_view()` or `get_viewport_angle()` from a
`QRunnable`.

**ComfyUI: `KSampler` error / model not found**
Verify the three model files exist at the paths in the **Models** tab.
The filenames must match exactly — the workflow references them by
filename. Override defaults via `SHOOT_COMFY_MODEL_UNET` etc.

**Stuck Comfy process Shoot can't see**
The **Kill Server** button falls back to port-PID lookup. If that also
fails:

```powershell
Get-NetTCPConnection -LocalPort 8188 -State Listen `
  | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## Limitations

- No multi-angle / orbit context. Earlier versions had this; the
  results were inconsistent so it was removed.
- FLUX.2 Klein is distilled. LoRAs trained for the full-step FLUX.2
  release are not guaranteed to work — none are wired in.
- Tested only on Windows 11 + CUDA. macOS / Linux paths are coded for
  but unverified.

---

Created by [mmejia.xyz](https://mmejia.xyz) — a creative technologist
based in Berlin.
