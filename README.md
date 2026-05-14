# Shoot — Maya 2026 plugin

Native Maya plugin that "shoots" the active 3D viewport through Gemini
2.5 Flash Image (nano-banana). Same idea as the Three.js prototype: use
a rough 3D scene as compositional reference for AI image generation —
but inside Maya, on your real scenes.

## Install

```sh
python install.py
```

This:
- writes `~/Library/Preferences/Autodesk/maya/2026/modules/shoot.mod`
  pointing at this repo
- installs `google-genai` and `Pillow` into Maya's `mayapy`

Then in Maya 2026:

```python
import maya.cmds as cmds
cmds.loadPlugin("plugin.py")
cmds.shootOpen()
```

A **Shoot** menu also appears in the main menu bar.

## Use

1. Frame a shot in any viewport (set your active camera).
2. Open the Shoot panel.
3. Set Gemini API key — either `GEMINI_API_KEY` env var, or paste it
   into the panel and click **Save Key** (persists in Maya `optionVar`).
4. **Snap Viewport** captures the active 3D view.
5. Write a prompt, click **Shoot**. Result shows in the right pane.

## Layout

```
shoot/
  plugin.py            Maya plugin entry — registers menu + shootOpen cmd
  settings.py          API key + model resolution
  capture/viewport.py  M3dView readback, playblast fallback
  inference/gemini.py  google-genai image-to-image
  ui/shoot_panel.py    PySide6 panel (QThreadPool for async generation)
```

## Uninstall

```sh
python install.py --uninstall
```
