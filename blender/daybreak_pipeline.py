"""
daybreak_pipeline.py — the Blender end of the Daybreak Mills pipeline.

Reads job files exported by daybreak-studio.html and builds a real carton for
each one: correct box size, the artwork texture mapped through the Dieline UV,
outdoor HDRI lighting, ground plane and a framed camera.

A job is a pair of files sitting in the same folder:

    daybreak_regular_golden_job.json    the spec (size, flavour, copy, brief)
    daybreak_regular_golden_4096.png    the artwork, named by the job's
                                        "texture" field

--------------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------------

Inside Blender (Scripting tab): set JOBS_DIR below, press Run Script.

Headless:
    blender --background --python daybreak_pipeline.py -- \
        --jobs /path/to/cereal_box/jobs \
        --hdri /path/to/kloofendal_48d_partly_cloudy_puresky_4k.hdr \
        --save /path/to/daybreak_lineup.blend \
        --render

    --one <name>   build only the job whose filename contains <name>
    --spacing 0.3  metres between boxes in the lineup
    --hero         single job only: frame it as a hero shot instead of a lineup

The box mesh, the Dieline UV and the sun-matching are the same code as
cereal_box_generator.py, so a carton built here is identical to one built there.

Tested on Blender 4.2 - 5.1.
"""

import argparse
import glob
import json
import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

# ==============================================================================
# CONFIG — used when running from Blender's Text Editor
# ==============================================================================

CONFIG = {
    "jobs_dir": "",             # REQUIRED: folder holding *_job.json + textures
    "one": "",                  # substring filter; "" builds every job found
    "hdri": "",                 # .hdr/.exr; "" falls back to a Blender built-in
    "builtin_hdri": "forest",
    "sky_strength": 1.0,
    "sky_rotation": -35.0,
    "sun_energy": 3.2,
    "exposure": -0.65,
    "spacing": 0.30,            # metres between boxes, centre to centre
    "hero": False,              # frame a single box close instead of a lineup
    "bevel": 0.0018,
    "ground_size": 8.0,
    "resolution": (1920, 1080),
    "samples": 96,
    "save": "",
    "render": False,
}

IN = 0.0254
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_version():
    try:
        with open(os.path.join(ROOT, "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "unknown"


# ==============================================================================
# Shared helpers (kept byte-identical in intent to cereal_box_generator.py)
# ==============================================================================

def pick_engine(scene):
    avail = [i.identifier for i in scene.render.bl_rna.properties["engine"].enum_items]
    for c in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if c in avail:
            scene.render.engine = c
            return


def set_in(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def builtin_hdri(name):
    folder = bpy.utils.system_resource("DATAFILES", path="studiolights/world")
    p = os.path.join(folder, os.path.splitext(name)[0] + ".exr")
    if os.path.isfile(p):
        return p
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(".exr"):
            return os.path.join(folder, f)
    raise FileNotFoundError("No built-in world HDRIs found")


def reset_scene(cfg):
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    scene.name = "DaybreakMills"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "CENTIMETERS"

    pick_engine(scene)
    scene.render.resolution_x, scene.render.resolution_y = cfg["resolution"]
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.exposure = cfg["exposure"]

    ee = scene.eevee
    for attr, val in (("taa_render_samples", cfg["samples"]), ("taa_samples", 16),
                      ("use_raytracing", True), ("use_shadows", True)):
        if hasattr(ee, attr):
            try:
                setattr(ee, attr, val)
            except Exception:
                pass
    return scene


def add_matched_sun(scene, image, rot_z, energy):
    """Brightest pixel in the HDRI becomes a real sun lamp, so EEVEE gets a crisp
    shadow instead of the soft blob a world alone gives."""
    w, h = image.size
    if w == 0 or h == 0:
        return None
    px = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, 4)
    lum = px[:, :, 0] * 0.2126 + px[:, :, 1] * 0.7152 + px[:, :, 2] * 0.0722
    row, col = divmod(int(np.argmax(lum)), w)

    u = (col + 0.5) / w
    v = (row + 0.5) / h
    az = (0.5 - u) * 2.0 * math.pi
    th = (v - 0.5) * math.pi
    d = Vector((math.cos(th) * math.cos(az), math.cos(th) * math.sin(az), math.sin(th)))
    d = (Matrix.Rotation(rot_z, 3, "Z") @ d).normalized()

    elev = math.asin(max(-1.0, min(1.0, d.z)))
    azim = math.atan2(d.y, d.x)

    data = bpy.data.lights.new("Sun", "SUN")
    data.energy = energy
    data.angle = math.radians(0.526)
    sun = bpy.data.objects.new("Sun", data)
    sun.rotation_euler = (math.pi / 2.0 - elev, 0.0, azim + math.pi / 2.0)
    scene.collection.objects.link(sun)
    print(f"  sun matched to HDRI: elevation {math.degrees(elev):.1f} deg, "
          f"azimuth {math.degrees(azim):.1f} deg")
    return sun


def build_world(scene, cfg):
    path = bpy.path.abspath(cfg["hdri"]) if cfg["hdri"] else builtin_hdri(cfg["builtin_hdri"])
    if not os.path.isfile(path):
        raise FileNotFoundError(f"HDRI not found: {path}")

    world = bpy.data.worlds.new("Outdoor_Sky")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld");     out.location = (600, 0)
    bg = nt.nodes.new("ShaderNodeBackground");       bg.location = (350, 0)
    env = nt.nodes.new("ShaderNodeTexEnvironment");  env.location = (0, 0)
    mapping = nt.nodes.new("ShaderNodeMapping");     mapping.location = (-280, 0)
    texco = nt.nodes.new("ShaderNodeTexCoord");      texco.location = (-480, 0)

    env.image = bpy.data.images.load(path, check_existing=True)
    bg.inputs["Strength"].default_value = cfg["sky_strength"]
    rot_z = math.radians(cfg["sky_rotation"])
    mapping.inputs["Rotation"].default_value = (0, 0, rot_z)

    L = nt.links.new
    L(texco.outputs["Generated"], mapping.inputs["Vector"])
    L(mapping.outputs["Vector"], env.inputs["Vector"])
    L(env.outputs["Color"], bg.inputs["Color"])
    L(bg.outputs["Background"], out.inputs["Surface"])

    if cfg["sun_energy"] > 0:
        add_matched_sun(scene, env.image, rot_z, cfg["sun_energy"])
    return path


def build_ground(scene, size):
    s = size / 2.0
    me = bpy.data.meshes.new("Ground")
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    me.update()
    ob = bpy.data.objects.new("Ground", me)
    scene.collection.objects.link(ob)
    mat = bpy.data.materials.new("Ground_Concrete")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.27, 0.265, 0.255, 1.0)
    b.inputs["Roughness"].default_value = 0.7
    me.materials.append(mat)
    return ob


# ==============================================================================
# Box mesh + the two UV maps
# ==============================================================================

def build_box_mesh(name, W, D, H):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(W, D, H), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, H / 2.0), verts=bm.verts)

    uv_cube = bm.loops.layers.uv.new("CubeProject")
    uv_die = bm.loops.layers.uv.new("Dieline")

    size = max(W, D, H)
    centre = Vector((0.0, 0.0, H / 2.0))
    total_w = 2 * W + 2 * D
    total_h = H + 2 * D
    s = 1.0 / max(total_w, total_h)
    offx = (1.0 - total_w * s) / 2.0
    offy = (1.0 - total_h * s) / 2.0

    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in f.loops:
            co = loop.vert.co
            c = co - centre
            if ax == 0:
                u, v = (c.y if n.x > 0 else -c.y), c.z
            elif ax == 1:
                u, v = (-c.x if n.y > 0 else c.x), c.z
            else:
                u, v = c.x, (c.y if n.z > 0 else -c.y)
            loop[uv_cube].uv = (u / size + 0.5, v / size + 0.5)

            x, y, z = co.x, co.y, co.z
            if ax == 1 and n.y < 0:    du, dv = (x + W / 2), D + z
            elif ax == 0 and n.x > 0:  du, dv = W + (y + D / 2), D + z
            elif ax == 1 and n.y > 0:  du, dv = (W + D) + (W / 2 - x), D + z
            elif ax == 0 and n.x < 0:  du, dv = (2 * W + D) + (D / 2 - y), D + z
            elif ax == 2 and n.z > 0:  du, dv = (x + W / 2), (D + H) + (y + D / 2)
            else:                      du, dv = (x + W / 2), (D / 2 - y)
            loop[uv_die].uv = (offx + du * s, offy + dv * s)

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(None)
    me.uv_layers["Dieline"].active_render = True     # artwork rides the net
    me.update()
    return me, {"offx": offx, "offy": offy, "scale": s}


def verify_uvs(me, job):
    """Cross-check the mesh we just built against the UV rects the browser
    exported. If these ever disagree, the art lands in the wrong place."""
    if "dieline_uv" not in job:
        return None
    uvl = me.uv_layers["Dieline"]
    got = {}
    for poly in me.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        if ax == 1:   key = "BACK" if n.y > 0 else "FRONT"
        elif ax == 0: key = "RIGHT" if n.x > 0 else "LEFT"
        else:         key = "TOP" if n.z > 0 else "BOTTOM"
        us = [uvl.uv[li].vector[0] for li in poly.loop_indices]
        vs = [uvl.uv[li].vector[1] for li in poly.loop_indices]
        got[key] = (min(us), max(us), min(vs), max(vs))

    worst, where = 0.0, ""
    for key, want in job["dieline_uv"].items():
        if key not in got:
            continue
        pairs = zip(got[key], (want["u0"], want["u1"], want["v0"], want["v1"]))
        for a, b in pairs:
            if abs(a - b) > worst:
                worst, where = abs(a - b), key
    return worst, where


def make_material(name, tex_path, flavour):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial");  out.location = (620, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (320, 0)
    tex = nt.nodes.new("ShaderNodeTexImage");        tex.location = (-40, 60)
    uvm = nt.nodes.new("ShaderNodeUVMap");           uvm.location = (-330, 60)
    bump = nt.nodes.new("ShaderNodeBump");           bump.location = (60, -300)
    noise = nt.nodes.new("ShaderNodeTexNoise");      noise.location = (-200, -300)
    texco = nt.nodes.new("ShaderNodeTexCoord");      texco.location = (-420, -300)

    uvm.uv_map = "Dieline"                       # <- the flattened net
    if tex_path and os.path.isfile(tex_path):
        img = bpy.data.images.load(tex_path, check_existing=True)
        img.colorspace_settings.name = "sRGB"    # Blender guesses Non-Color sometimes
        tex.image = img
        tex.extension = "EXTEND"
    else:
        print(f"  [warn] texture missing, falling back to flat field colour: {tex_path}")

    # printed carton: a little coat for the print varnish, fine paper grain
    set_in(bsdf, "Roughness", 0.42)
    set_in(bsdf, "Metallic", 0.0)
    set_in(bsdf, "Coat Weight", 0.28)
    set_in(bsdf, "Coat Roughness", 0.12)
    set_in(bsdf, "Sheen Weight", 0.06)

    noise.inputs["Scale"].default_value = 380.0
    noise.inputs["Detail"].default_value = 8.0
    bump.inputs["Strength"].default_value = 0.07
    bump.inputs["Distance"].default_value = 0.0004

    L = nt.links.new
    L(uvm.outputs["UV"], tex.inputs["Vector"])
    if tex.image:
        L(tex.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        set_in(bsdf, "Base Color", hex_to_linear(flavour.get("field", "#C3A377")))
    L(texco.outputs["Object"], noise.inputs["Vector"])
    L(noise.outputs["Fac"], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def hex_to_linear(hexstr):
    h = hexstr.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], 1.0)


# ==============================================================================
# Jobs
# ==============================================================================

FLAVOUR_ORDER = ["golden", "cocoa", "berry", "honey", "frosted", "bran"]
SIZE_ORDER = ["Mega", "Family", "Regular", "Mini"]        # tallest at the back


def load_manifest(folder):
    """A range zip carries range.json — the authoritative order for the lineup."""
    p = os.path.join(folder, "range.json")
    if not os.path.isfile(p):
        return None
    with open(p) as f:
        return json.load(f)


def find_jobs(folder, one=""):
    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(folder):
        raise NotADirectoryError(f"Jobs folder does not exist: {folder}")
    manifest = load_manifest(folder)
    if manifest and not one:
        ordered = [os.path.join(folder, j["job"]) for j in manifest.get("jobs", [])]
        files = [f for f in ordered if os.path.isfile(f)]
        if files:
            return files
    files = sorted(glob.glob(os.path.join(folder, "*_job.json")))
    if not files:
        files = sorted(glob.glob(os.path.join(folder, "*.json")))
    if one:
        files = [f for f in files if one.lower() in os.path.basename(f).lower()]
    return files


def load_job(path):
    with open(path) as f:
        job = json.load(f)
    fmt = job.get("format", "")
    if not fmt.startswith("daybreak-job/"):
        print(f"  [warn] {os.path.basename(path)} has no daybreak-job format tag; "
              f"trying anyway")
    job["_path"] = path
    job["_dir"] = os.path.dirname(path)
    tex = job.get("texture", "")
    job["_texture"] = os.path.join(job["_dir"], tex) if tex else ""
    return job


def build_job(scene, job, cfg, index, collection):
    box = job["box"]
    inch = box["inches"]
    W, D, H = inch["W"] * IN, inch["D"] * IN, inch["H"] * IN
    label = f"{box['size']}_{job['flavour']['key']}"

    me, net = build_box_mesh(f"Box_{label}", W, D, H)

    drift = verify_uvs(me, job)
    if drift:
        worst, where = drift
        if worst > 1e-4:
            print(f"  [FAIL] Dieline UVs disagree with the job file by {worst:.6f} "
                  f"at {where} — the artwork would land misaligned. Skipping.")
            return None
        print(f"  UV check: max drift {worst:.2e} vs the browser's rects — aligned")

    mat = make_material(f"Art_{label}", job.get("_texture", ""), job.get("flavour", {}))
    ob = bpy.data.objects.new(f"Box_{label}", me)
    collection.objects.link(ob)
    ob.material_slots[0].link = "OBJECT"
    ob.material_slots[0].material = mat

    b = ob.modifiers.new("Carton Edge", "BEVEL")
    b.width = cfg["bevel"]
    b.segments = 2
    b.limit_method = "ANGLE"
    b.angle_limit = math.radians(30)

    ob.location = (index * cfg["spacing"], 0.0, 0.0)   # re-laid-out by arrange()
    ob.rotation_euler = (0.0, 0.0, math.radians(-4.0))

    for k in ("size",):
        ob[f"box_{k}"] = box[k]
    ob["flavour"] = job["flavour"]["name"]
    ob["flavour_key"] = job["flavour"].get("key", "")
    ob["claim"] = job.get("copy", {}).get("claim", "")
    ob["brief"] = json.dumps(job.get("brief", {}))
    return ob


def arrange(boxes, cfg, order=None):
    """Flavours across, sizes back to front. One size becomes a single row;
    the full matrix becomes a 6 x 4 grid with the tallest cartons at the back
    so nothing is hidden. `order` is the manifest's flavour list — a custom
    brand has its own keys, which FLAVOUR_ORDER cannot know; without it the
    columns of an unknown range would come out in set-iteration order."""
    global FLAVOUR_ORDER
    if order:
        FLAVOUR_ORDER = [str(k).lower() for k in order] + [k for k in FLAVOUR_ORDER if k not in order]
    def key_flavour(o):
        k = str(o.get("flavour_key", "")).lower()
        return FLAVOUR_ORDER.index(k) if k in FLAVOUR_ORDER else 99
    def key_size(o):
        s = str(o.get("box_size", ""))
        return SIZE_ORDER.index(s) if s in SIZE_ORDER else 99

    sizes = sorted({str(o.get("box_size", "")) for o in boxes}, key=lambda s: SIZE_ORDER.index(s) if s in SIZE_ORDER else 99)
    flavours = sorted({str(o.get("flavour_key", "")).lower() for o in boxes},
                      key=lambda k: FLAVOUR_ORDER.index(k) if k in FLAVOUR_ORDER else 99)
    col_step = cfg["spacing"]
    row_step = cfg["spacing"] * 0.95
    for o in boxes:
        c = flavours.index(str(o.get("flavour_key", "")).lower()) if len(flavours) > 1 else 0
        r = sizes.index(str(o.get("box_size", ""))) if len(sizes) > 1 else 0
        o.location = ((c - (len(flavours) - 1) / 2.0) * col_step,
                      ((len(sizes) - 1) / 2.0 - r) * row_step,
                      0.0)
    return len(flavours), len(sizes)


def build_camera(scene, boxes, cfg):
    """Frame whatever got built, so one box and eight both come out composed."""
    xs = [o.location.x for o in boxes]
    ys = [o.location.y for o in boxes]
    heights = [max(v.co.z for v in o.data.vertices) for o in boxes]
    widths = [max(v.co.x for v in o.data.vertices) * 2 for o in boxes]
    cx = (min(xs) + max(xs)) / 2.0
    depth = (max(ys) - min(ys))
    span = (max(xs) - min(xs)) + max(widths) + 0.06 + depth * 0.35   # a deep grid needs more room
    top = max(heights) + depth * 0.15

    target = bpy.data.objects.new("CamTarget", None)
    target.empty_display_size = 0.06
    target.location = (cx, (min(ys) + max(ys)) / 2.0, top * 0.52)
    scene.collection.objects.link(target)

    data = bpy.data.cameras.new("Camera")
    hero = cfg["hero"] and len(boxes) == 1
    data.lens = 65.0 if hero else 45.0
    data.dof.use_dof = True
    data.dof.focus_object = target
    data.dof.aperture_fstop = 3.5 if hero else 7.1

    cam = bpy.data.objects.new("Camera", data)
    # Pull back far enough for BOTH axes to fit. A single tall carton is limited
    # by its height, a wide lineup by its span — solve each and take the larger.
    aspect = scene.render.resolution_y / max(1, scene.render.resolution_x)
    h_half = math.atan(18.0 / data.lens)                 # 36 mm sensor across
    v_half = math.atan(18.0 * aspect / data.lens)
    need_w = (span / 2.0) / math.tan(h_half)
    need_h = ((top * 1.15 + depth * 0.6) / 2.0) / math.tan(v_half)
    dist = max(0.45, max(need_w, need_h) * 1.15)
    # A product-shot camera sits low. Fine for one row; with four rows the
    # Regular row hid Mega and Family completely. Climb with the grid's depth
    # so every row shows — the 24-box matrix ends up looking down at ~20°.
    lift = depth * 1.1
    cam.location = (cx + dist * 0.30, -dist * 0.90, top * (0.55 if hero else 0.80) + lift)
    scene.collection.objects.link(cam)
    scene.camera = cam

    c = cam.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    return cam


def look_through_camera():
    for window in getattr(bpy.context.window_manager, "windows", []):
        screen = getattr(window, "screen", None)
        if not screen:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.region_3d.view_perspective = "CAMERA"
                    space.shading.type = "MATERIAL"


# ==============================================================================
# Orchestration
# ==============================================================================

def run(cfg):
    if not cfg["jobs_dir"]:
        raise ValueError("jobs_dir is not set — point it at the folder holding "
                         "the *_job.json files exported from daybreak-studio.html")

    jobs = find_jobs(cfg["jobs_dir"], cfg["one"])
    if not jobs:
        raise FileNotFoundError(f"No *_job.json found in {cfg['jobs_dir']}")

    print(f"\n=== daybreak_pipeline v{repo_version()} ===")
    print(f"jobs folder : {os.path.abspath(cfg['jobs_dir'])}")
    print(f"jobs found  : {len(jobs)}")

    scene = reset_scene(cfg)
    hdri = build_world(scene, cfg)
    print(f"hdri        : {hdri}")
    build_ground(scene, cfg["ground_size"])

    coll = bpy.data.collections.new("DaybreakBoxes")
    scene.collection.children.link(coll)

    built = []
    for i, path in enumerate(jobs):
        job = load_job(path)
        print(f"\n[{i+1}/{len(jobs)}] {os.path.basename(path)}")
        print(f"  {job['box']['size']} · {job['flavour']['name']} · "
              f"\"{job.get('copy',{}).get('claim','')}\"")
        if job.get("brief"):
            print(f"  brief: {', '.join(f'{k}={v}' for k, v in job['brief'].items())}")
        tex = job.get("_texture", "")
        print(f"  texture: {os.path.basename(tex) if tex else '(none)'}"
              f"{'' if os.path.isfile(tex) else '  [MISSING]'}")
        ob = build_job(scene, job, cfg, len(built), coll)
        if ob:
            built.append(ob)

    if not built:
        raise RuntimeError("No boxes were built")

    manifest = load_manifest(os.path.abspath(cfg["jobs_dir"]))
    cols, rows = arrange(built, cfg, (manifest or {}).get("flavours"))
    if manifest:
        scene.name = manifest.get("name", scene.name)[:60]
    print(f"\nlayout      : {cols} across x {rows} deep")

    shelf = (manifest or {}).get('shelf')
    if shelf:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from shelf_scene import build_shelf
        built = build_shelf(scene, built, shelf)
    else:
        build_camera(scene, built, cfg)
    look_through_camera()

    out_dir = os.path.join(os.path.abspath(cfg["jobs_dir"]), "renders")
    os.makedirs(out_dir, exist_ok=True)
    scene.render.filepath = os.path.join(out_dir, "daybreak_")

    print(f"\nboxes built : {len(built)}")
    print(f"render path : {scene.render.filepath}")

    if cfg["save"]:
        p = os.path.abspath(os.path.expanduser(cfg["save"]))
        bpy.ops.wm.save_as_mainfile(filepath=p)
        print(f"saved       : {p}")

    if cfg["render"]:
        bpy.ops.render.render(write_still=True)
        print("rendered    : done")

    return scene


def build_argparser():
    p = argparse.ArgumentParser(prog="daybreak_pipeline")
    p.add_argument("--jobs", dest="jobs_dir", type=str)
    p.add_argument("--one", type=str)
    p.add_argument("--hdri", type=str)
    p.add_argument("--builtin-hdri", type=str)
    p.add_argument("--sky-strength", type=float)
    p.add_argument("--sky-rotation", type=float)
    p.add_argument("--sun-energy", type=float)
    p.add_argument("--exposure", type=float)
    p.add_argument("--spacing", type=float)
    p.add_argument("--hero", action="store_true", default=None)
    p.add_argument("--bevel", type=float)
    p.add_argument("--ground-size", type=float)
    p.add_argument("--resolution", type=int, nargs=2, metavar=("W", "H"))
    p.add_argument("--samples", type=int)
    p.add_argument("--save", type=str)
    p.add_argument("--render", action="store_true", default=None)
    return p


def config_from_cli(cfg):
    argv = sys.argv
    if "--" not in argv:
        return cfg
    args = build_argparser().parse_args(argv[argv.index("--") + 1:])
    merged = dict(cfg)
    for k, v in vars(args).items():
        if v is not None:
            merged[k] = tuple(v) if k == "resolution" else v
    return merged


if __name__ == "__main__":
    run(config_from_cli(CONFIG))
