"""
startup_hook.py — runs inside the Blender GUI when tools/start.py launches it.

    blender --python blender/startup_hook.py

Two jobs, both best-effort and both logged to Blender's system console:

  1. Start the MCP add-on's server if one is installed, so an assistant session
     can reconnect to this Blender. Operator names differ between MCP add-ons,
     so this looks for any operator under a module containing "mcp" whose name
     contains "start" and calls it.
  2. If DAYBREAK_OPEN_LAST=1 is set and a lineup .blend exists in jobs/renders,
     open the newest one once the UI is up — the last thing built is usually
     the thing you want to look at.
"""

import glob
import os

import bpy

ROOT = os.environ.get("DAYBREAK_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def start_mcp():
    started = []
    for mod_name in dir(bpy.ops):
        if "mcp" not in mod_name.lower():
            continue
        mod = getattr(bpy.ops, mod_name)
        for op_name in dir(mod):
            if "start" in op_name.lower():
                try:
                    getattr(mod, op_name)()
                    started.append(f"bpy.ops.{mod_name}.{op_name}()")
                except Exception as exc:
                    print(f"[daybreak] {mod_name}.{op_name} raised: {exc}")
    if started:
        print(f"[daybreak] MCP server started via {', '.join(started)}")
    else:
        print("[daybreak] no MCP start operator found — enable the add-on's server by hand if you want an assistant connected")
    return None


def open_last():
    blends = sorted(glob.glob(os.path.join(ROOT, "jobs", "renders", "*.blend")), key=os.path.getmtime)
    if blends:
        try:
            bpy.ops.wm.open_mainfile(filepath=blends[-1])
            print(f"[daybreak] opened {os.path.relpath(blends[-1], ROOT)}")
        except Exception as exc:
            print(f"[daybreak] could not open last lineup: {exc}")
    return None


# defer until the window and add-ons exist; a --python script runs very early
bpy.app.timers.register(start_mcp, first_interval=1.5)
if os.environ.get("DAYBREAK_OPEN_LAST") == "1":
    bpy.app.timers.register(open_last, first_interval=2.5)
