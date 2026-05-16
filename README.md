# Shoot

> A small Autodesk Maya 2026 plugin that turns the active 3D viewport
> into a generated still — locally, in monochrome, without leaving the
> scene.

```
YEAR        2026
FORMAT      MAYA 2026 PLUGIN
RUNTIME     MAYAPY · PYSIDE6 · COMFYUI
MODEL       FLUX.2 KLEIN 9B FP8
AUTHOR      MANUEL MEJIA
DOCUMENTATION   https://mejia37.github.io/3DtoAI-Maya/
```

---

## Practice

Manuel Mejia is a creative technologist and filmmaker whose work sits at
the intersection of collective identity, political memory, and the
technologies that mediate both. Shoot is a small instrument in that
practice — a way to keep the staging of an image inside the same room
where the image is made.

The plugin makes one small claim: that the 3D viewport, the prompt, and
the generated still belong on the same surface. Maya is where the
composition is decided; the model should not require a separate window,
a separate workflow, or an external API call to honour that decision.
The viewport is snapped, the prompt is written, the ComfyUI server
replies — all without leaving the scene.

---

## Install

The plugin is distributed as a Maya module. There is no installer.

### One — place the module

Clone the repository into a directory Maya scans for modules. On Windows
the default is below; substitute your username.

```sh
git clone https://github.com/Mejia37/3DtoAI-Maya.git ^
  "%USERPROFILE%\Documents\maya\2026\modules\shoot"
```

### Two — install Python dependencies into mayapy

A HuggingFace client is required for the FLUX.2 weights download.
Maya ships its own Python (`mayapy.exe`); install into that, not the
system Python.

```sh
"C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pip install ^
  "huggingface_hub>=0.20"
```

### Three — install ComfyUI

Shoot does not bundle ComfyUI. Install it once, anywhere on the machine.
The default expected path is `%USERPROFILE%\ComfyUI`; edit the path in
the plugin's **Models** tab to point elsewhere.

### Four — load the plugin

Open Maya. In the Plug-in Manager, load `plugin.py`. A *Shoot* menu
appears in the main menu bar; choose **Open Shoot Panel**.

```python
import maya.cmds as cmds
cmds.loadPlugin("plugin.py")
cmds.shootOpen()
```

---

## Use

### Models

Open the **Models** tab and download the three files Shoot requires.
The UNet is gated; accepting the FLUX.2 Klein license on huggingface.co
and pasting a HuggingFace token into the panel is required before that
file can be retrieved. The text encoder and VAE are public.

| File          | Size       | Source                                                          |
|---------------|------------|-----------------------------------------------------------------|
| UNET          | ~9 GB      | `black-forest-labs/FLUX.2-klein-9b-kv-fp8` *(gated)*            |
| TEXT ENCODER  | ~8 GB      | `Comfy-Org/vae-text-encorder-for-flux-klein-9b`                 |
| VAE           | ~335 MB    | `Comfy-Org/vae-text-encorder-for-flux-klein-9b`                 |

### Generating a still

In the **Shoot** tab, start the ComfyUI server with the button in the
header. Frame the camera in the viewport. Press **Snap Viewport**; the
captured frame appears in the *Viewport Snap* pane. Write a prompt in
the field at the top of the panel — third-person, archival, no
marketing verbs — and press **Generate**. Klein is a four-step
distilled model; the result returns in roughly forty seconds on a
twelve-gigabyte card, faster on more.

### Killing the server

The red **Kill ComfyUI** button is always available when a Comfy
process is listening on the configured port — including mid-generation,
and including processes Shoot did not itself start. The button falls
back to a port-PID lookup when the manager has no tracked subprocess,
so a Comfy launched from a terminal earlier in the day is still
reachable.

---

## Architecture

Shoot is intentionally small. Five top-level modules, none of which
depend on a framework beyond Maya and the Python standard library.

| Path                          | Purpose                                                                                          |
|-------------------------------|--------------------------------------------------------------------------------------------------|
| `shoot/plugin.py`             | Maya 2.0 API plugin shell — registers `shootOpen` and the menu item                              |
| `shoot/capture/viewport.py`   | Reads the active `M3dView` back-buffer; falls back to a one-frame playblast when the driver refuses |
| `shoot/comfy/client.py`       | Thin REST client over `urllib` — no third-party HTTP dependency                                  |
| `shoot/comfy/manager.py`      | Starts, stops, and kills the local ComfyUI server (PID-by-port fallback)                         |
| `shoot/comfy/workflow.py`     | Emits the FLUX.2 Klein workflow as a Python dict (matches the official subgraph)                 |
| `shoot/comfy/downloader.py`   | Wraps `huggingface_hub` for gated weights and resumable downloads                                |
| `shoot/inference/comfy.py`    | A single function, `generate()` — upload, queue, poll, return                                    |
| `shoot/ui/shoot_panel.py`     | The PySide6 panel — two tabs (*Shoot*, *Models*) on a `QThreadPool`                              |

### The FLUX.2 workflow

The workflow Shoot emits matches the official *Image Edit (Flux.2 Klein
9B Distilled)* subgraph published by Black Forest Labs and Comfy-Org.
Nineteen nodes, one reference image, one prompt; `ConditioningZeroOut`
for negative, `cfg = 1`, four sampling steps, the Euler sampler. No
LoRAs. No multi-angle context. The single-image discipline is
deliberate.

### What is intentionally absent

Earlier drafts of Shoot orbited temporary cameras around the scene to
give the model multiple reference angles, and ran an additional pass to
extract clean backgrounds for reuse across angles. Both were removed.
The orbit version produced inconsistent results and added two buttons
to a UI that should ask the user for one decision at a time. The
current shape — snap, prompt, generate — is the one that survived.

---

## Design

The plugin's surface follows the rules of the
[`Manuel Mejia` design system](https://mejia37.github.io/3DtoAI-Maya/):
monochromatic, monospaced, hairline-ruled, no rounded corners, no
icons. The Maya panel renders on an *ink* surface — paper text over
near-black — because Maya itself is dark by default and the system's
opacity ladder reads correctly inverted. There are no drop-shadows,
anywhere.

---

## Caveats

FLUX.2 Klein is a distilled model released weeks before this writing;
the broader ecosystem of LoRAs and conditioning tools has not yet
caught up to it. Multi-angle consistency, in particular, relies on
prompting alone — there is no multi-angle LoRA for FLUX.2 at the time
of release. The model will arrive, and Shoot will inherit it; the
plugin's current shape does not assume that arrival.

The plugin is tested on Windows 11, Maya 2026, and an NVIDIA
twelve-gigabyte card. Other configurations are likely to work and have
not been verified.

---

© Manuel Mejia · 2026
