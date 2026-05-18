"""Maya plugin entry for Shoot.

Loaded by Maya via `loadPlugin "shoot"` (or `shoot.py`). The Plug-in
Manager lists it as "shoot". Registers:
  - A command `shootOpen` that opens the dockable shoot panel.
  - A "Shoot" menu in Maya's main window.
"""
from __future__ import annotations

import sys

import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel


# Tell Maya to use the Python 2.0 API.
def maya_useNewAPI():
    pass


PLUGIN_NAME = "shoot"
PLUGIN_VERSION = "0.1.0"
PLUGIN_VENDOR = "3DtoAI"

CMD_OPEN = "shootOpen"
MENU_NAME = "shootMainMenu"


class ShootOpenCmd(om.MPxCommand):
    cmdName = CMD_OPEN

    def __init__(self):
        super().__init__()

    @staticmethod
    def creator():
        return ShootOpenCmd()

    def doIt(self, args):
        # Defer the heavy import so plugin load stays fast and a bad
        # PySide import doesn't kill plugin registration.
        from shoot.ui.shoot_panel import show_panel
        show_panel()


def _build_menu():
    main_window = mel.eval("$tmp = $gMainWindow")
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME)
    cmds.menu(MENU_NAME, label="Shoot", parent=main_window, tearOff=True)
    cmds.menuItem(
        label="Open Shoot Panel...",
        parent=MENU_NAME,
        command=lambda *_: cmds.shootOpen(),
    )


def _remove_menu():
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME)


def initializePlugin(plugin):
    fn = om.MFnPlugin(plugin, PLUGIN_VENDOR, PLUGIN_VERSION, "Any")
    try:
        fn.registerCommand(ShootOpenCmd.cmdName, ShootOpenCmd.creator)
    except Exception:
        sys.stderr.write(f"[{PLUGIN_NAME}] failed to register command\n")
        raise
    # Defer menu build until idle so $gMainWindow is ready on cold start.
    cmds.evalDeferred(_build_menu, lowestPriority=True)


def uninitializePlugin(plugin):
    fn = om.MFnPlugin(plugin)
    _remove_menu()
    try:
        fn.deregisterCommand(ShootOpenCmd.cmdName)
    except Exception:
        sys.stderr.write(f"[{PLUGIN_NAME}] failed to deregister command\n")
        raise
