"""
cereal_box_generator.py
=======================

Builds a cereal-box scene in Blender: real-world box sizes, six printed-carton
shaders, box-projected UVs, an outdoor HDRI sky and a ground plane.

Two modes:

  grid    (default) every size x every shader laid out as a reference chart.
          4 sizes x 6 shaders = 24 boxes.

  random  scatters N boxes with a random size, shader, position and yaw -
          a shelf/pile generator rather than a chart.

Box dimensions are the real ones used by the big US brands (General Mills,
Kellogg's, Post), height x width x depth in inches:

    Regular   12.0 x 7.75 x 2.50    (~12 oz)
    Family    13.0 x 7.75 x 3.00    (~18 oz)
    Mega      13.5 x 9.50 x 3.15    (~27 oz)
    Mini       6.5 x 4.00 x 1.50    (variety pack)

Every box carries TWO UV maps:
    CubeProject  box / cube projection, one shared scale so all six faces keep
                 their true aspect ratio. This is the active one.
    Dieline      the same six faces unfolded as a flat carton net
                 (front-right-back-left in a strip, top and bottom flaps),
                 packed into 0-1 with no overlap. Better for painting artwork.

--------------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------------

A) Inside Blender: edit CONFIG below, press Run Script.

B) Headless:
   blender --background --python cereal_box_generator.py -- \
       --mode random --count 40 --hdri /path/to/sky.hdr \
       --save /path/to/out.blend --render

   Omit --hdri and it falls back to a Blender built-in world.

Tested on Blender 4.2 - 5.1.
"""

import argparse
import math
import os
import random
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

# ==============================================================================
# CONFIG
# ==============================================================================

CONFIG = {
    "mode": "grid",             # "grid" or "random"
    "count": 40,                # random mode only: how many boxes to scatter
    "area": (2.2, 1.4),         # random mode only: scatter footprint in metres

    "hdri": "",                 # path to an .hdr/.exr; "" uses a Blender built-in
    "builtin_hdri": "forest",   # fallback built-in (outdoor-ish: forest/sunrise/city)
    "sky_strength": 1.0,
    "sky_rotation": -35.0,      # degrees around Z
    "sun_energy": 3.2,          # 0 disables the matched sun
    "exposure": -0.65,

    "bevel": 0.0018,            # carton edge crease, metres
    "ground_size": 8.0,
    "seed": 7,

    "resolution": (1920, 1080),
    "samples": 96,
    "save": "",                 # .blend path; "" skips saving
    "render": False,
    "render_dir": "",
}

IN = 0.0254

# name, height, width, depth (inches)
SIZES = [
    ("Regular", 12.0, 7.75, 2.50),
    ("Family",  13.0, 7.75, 3.00),
    ("Mega",    13.5, 9.50, 3.15),
    ("Mini",     6.5, 4.00, 1.50),
]

# name, hex, roughness, coat weight
SHADERS = [
    ("Cereal_01_CornGold",     "#E9A32B", 0.34, 0.35),
    ("Cereal_02_CocoaBrown",   "#4B2A19", 0.45, 0.20),
    ("Cereal_03_BerryRed",     "#C21E3A", 0.30, 0.45),
    ("Cereal_04_HoneyOat",     "#D2A15E", 0.42, 0.25),
    ("Cereal_05_KidsBlue",     "#1560B8", 0.26, 0.55),
    ("Cereal_06_OrganicGreen", "#4C7A35", 0.55, 0.10),
]


# ==============================================================================
# Helpers
# ==============================================================================

def srgb_to_linear(hexstr):
    h = hexstr.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], 1.0)


def set_in(node, name, value):
    """Principled socket names moved between versions - skip what isn't there."""
    if name in node.inputs:
        node.inputs[name].default_value = value


def pick_engine(scene):
    avail = [i.identifier for i in scene.render.bl_rna.properties["engine"].enum_items]
    for c in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if c in avail:
            scene.render.engine = c
            return


def builtin_hdri(name):
    folder = bpy.utils.system_resource("DATAFILES", path="studiolights/world")
    path = os.path.join(folder, os.path.splitext(name)[0] + ".exr")
    if os.path.isfile(path):
        return path
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(".exr"):
            return os.path.join(folder, f)
    raise FileNotFoundError("No built-in world HDRIs found")


# ==============================================================================
# Scene
# ==============================================================================

def reset_scene(cfg):
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    scene.name = "CerealBoxes"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "CENTIMETERS"

    pick_engine(scene)
    scene.render.resolution_x, scene.render.resolution_y = cfg["resolution"]
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.exposure = cfg["exposure"]

    ee = scene.eevee
    for attr, val in (("taa_render_samples", cfg["samples"]),
                      ("taa_samples", 16),
                      ("use_raytracing", True),
                      ("use_shadows", True)):
        if hasattr(ee, attr):
            try:
                setattr(ee, attr, val)
            except Exception:
                pass
    return scene


def build_world(scene, cfg):
    path = cfg["hdri"] or builtin_hdri(cfg["builtin_hdri"])
    path = bpy.path.abspath(path)
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


def add_matched_sun(scene, image, rot_z, energy):
    """Find the brightest pixel in the HDRI and put a real sun lamp there, so
    EEVEE gets a crisp shadow instead of the soft blob a world alone produces."""
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
    d = (Matrix.Rotation(rot_z, 3, "Z") @ d).normalized()   # undo the mapping rotation

    elev = math.asin(max(-1.0, min(1.0, d.z)))
    azim = math.atan2(d.y, d.x)

    data = bpy.data.lights.new("Sun", "SUN")
    data.energy = energy
    data.angle = math.radians(0.526)          # the sun's real angular diameter
    sun = bpy.data.objects.new("Sun", data)
    sun.rotation_euler = (math.pi / 2.0 - elev, 0.0, azim + math.pi / 2.0)
    scene.collection.objects.link(sun)
    print(f"  sun matched to HDRI: elevation {math.degrees(elev):.1f} deg, "
          f"azimuth {math.degrees(azim):.1f} deg")
    return sun


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
# Materials
# ==============================================================================

def carton_material(name, hexcolor, roughness, coat,
                    grain_strength=0.09, grain_scale=380.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial");  out.location = (520, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (220, 0)
    bump = nt.nodes.new("ShaderNodeBump");           bump.location = (0, -240)
    noise = nt.nodes.new("ShaderNodeTexNoise");      noise.location = (-230, -240)
    rmap = nt.nodes.new("ShaderNodeMapRange");       rmap.location = (0, -60)
    texco = nt.nodes.new("ShaderNodeTexCoord");      texco.location = (-430, -240)

    noise.inputs["Scale"].default_value = grain_scale
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.55
    bump.inputs["Strength"].default_value = grain_strength
    bump.inputs["Distance"].default_value = 0.0004

    rmap.inputs["From Min"].default_value = 0.35
    rmap.inputs["From Max"].default_value = 0.65
    rmap.inputs["To Min"].default_value = max(0.0, roughness - 0.06)
    rmap.inputs["To Max"].default_value = min(1.0, roughness + 0.06)

    set_in(bsdf, "Base Color", srgb_to_linear(hexcolor))
    set_in(bsdf, "Metallic", 0.0)
    set_in(bsdf, "IOR", 1.5)
    set_in(bsdf, "Coat Weight", coat)
    set_in(bsdf, "Coat Roughness", 0.12)
    set_in(bsdf, "Sheen Weight", 0.06)

    L = nt.links.new
    L(texco.outputs["Object"], noise.inputs["Vector"])
    L(noise.outputs["Fac"], bump.inputs["Height"])
    L(noise.outputs["Fac"], rmap.inputs["Value"])
    L(rmap.outputs["Result"], bsdf.inputs["Roughness"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def uv_grid_material():
    img = bpy.data.images.new("UV_ColorGrid", 2048, 2048)
    img.generated_type = "COLOR_GRID"          # a property in 5.x, not a new() kwarg
    img.generated_width = 2048
    img.generated_height = 2048

    mat = bpy.data.materials.new("UV_ColorGrid")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (420, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (140, 0)
    tex = nt.nodes.new("ShaderNodeTexImage");        tex.location = (-200, 0)
    tex.image = img
    tex.interpolation = "Closest"
    set_in(bsdf, "Roughness", 0.5)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def build_materials():
    mats = [carton_material(*s) for s in SHADERS]
    carton_material("Carton_Plain", "#C3A377", 0.78, 0.0,
                    grain_strength=0.18, grain_scale=260.0)
    uv_grid_material()
    return mats


# ==============================================================================
# Box mesh + UVs
# ==============================================================================

def build_box_mesh(name, W, D, H):
    """Origin at the centre of the base, built at true size so object scale stays
    1.0 - which means bevel widths and UV density mean what they say."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(W, D, H), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, H / 2.0), verts=bm.verts)

    uv_cube = bm.loops.layers.uv.new("CubeProject")
    uv_die = bm.loops.layers.uv.new("Dieline")

    size = max(W, D, H)                       # one scale for all faces -> true aspect
    centre = Vector((0.0, 0.0, H / 2.0))

    total_w = 2 * W + 2 * D                   # the unfolded carton net
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
            if ax == 1 and n.y < 0:    du, dv = (x + W / 2), D + z                    # front
            elif ax == 0 and n.x > 0:  du, dv = W + (y + D / 2), D + z                # right
            elif ax == 1 and n.y > 0:  du, dv = (W + D) + (W / 2 - x), D + z          # back
            elif ax == 0 and n.x < 0:  du, dv = (2 * W + D) + (D / 2 - y), D + z      # left
            elif ax == 2 and n.z > 0:  du, dv = (x + W / 2), (D + H) + (y + D / 2)    # top
            else:                      du, dv = (x + W / 2), (D / 2 - y)              # bottom
            loop[uv_die].uv = (offx + du * s, offy + dv * s)

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(None)                 # one slot, overridden per object
    me.uv_layers["CubeProject"].active_render = True
    me.update()
    return me


def build_all_meshes():
    out = {}
    for name, h_in, w_in, d_in in SIZES:
        W, D, H = w_in * IN, d_in * IN, h_in * IN
        out[name] = (build_box_mesh(f"Box_{name}", W, D, H), W, D, H)
    return out


def place_box(collection, meshes, size_name, mat, location, yaw, bevel):
    me = meshes[size_name][0]
    ob = bpy.data.objects.new(f"Box_{size_name}_{mat.name.split('_')[-1]}", me)
    collection.objects.link(ob)
    ob.location = location
    ob.rotation_euler = (0.0, 0.0, yaw)

    ob.material_slots[0].link = "OBJECT"      # so all boxes can share one mesh
    ob.material_slots[0].material = mat

    if bevel > 0:
        b = ob.modifiers.new("Carton Edge", "BEVEL")
        b.width = bevel
        b.segments = 2
        b.limit_method = "ANGLE"
        b.angle_limit = math.radians(30)

    ob["box_size"] = size_name
    ob["box_shader"] = mat.name
    return ob


# ==============================================================================
# Layouts
# ==============================================================================

def layout_grid(scene, meshes, mats, cfg):
    """Every size x every shader. Tallest row at the back so nothing hides."""
    coll = bpy.data.collections.new("CerealBoxes")
    scene.collection.children.link(coll)

    order = sorted(SIZES, key=lambda s: -s[1])          # tallest first
    col_step, row_step = 0.34, 0.30
    rng = random.Random(cfg["seed"])

    for r, (size_name, _h, _w, _d) in enumerate(order):
        y = ((len(order) - 1) / 2.0 - r) * row_step
        for c, mat in enumerate(mats):
            x = (c - (len(mats) - 1) / 2.0) * col_step
            place_box(coll, meshes, size_name, mat, (x, y, 0.0),
                      math.radians(rng.uniform(-3.5, 3.5)), cfg["bevel"])
    return coll


def layout_random(scene, meshes, mats, cfg):
    """Random size, shader, position and yaw. Rejects overlaps so boxes don't
    intersect - footprints are compared as circles around each box's diagonal."""
    coll = bpy.data.collections.new("CerealBoxes")
    scene.collection.children.link(coll)

    rng = random.Random(cfg["seed"])
    half_x, half_y = cfg["area"][0] / 2.0, cfg["area"][1] / 2.0
    placed = []

    for i in range(cfg["count"]):
        size_name = rng.choice([s[0] for s in SIZES])
        _me, W, D, H = meshes[size_name]
        radius = math.hypot(W, D) / 2.0

        for _try in range(80):
            x = rng.uniform(-half_x, half_x)
            y = rng.uniform(-half_y, half_y)
            if all(math.hypot(x - px, y - py) > (radius + pr) * 1.02
                   for px, py, pr in placed):
                break
        else:
            continue                                    # no room left, stop adding

        placed.append((x, y, radius))
        place_box(coll, meshes, size_name, rng.choice(mats), (x, y, 0.0),
                  rng.uniform(0.0, math.tau), cfg["bevel"])

    print(f"  placed {len(placed)} of {cfg['count']} requested "
          f"(the rest had no room in the scatter area)")
    return coll


def build_camera(scene, cfg, mode):
    target = bpy.data.objects.new("CamTarget", None)
    target.empty_display_size = 0.08
    target.location = (0.0, 0.0, 0.17)
    scene.collection.objects.link(target)

    data = bpy.data.cameras.new("Camera")
    data.lens = 45.0
    data.dof.use_dof = True
    data.dof.focus_object = target
    data.dof.aperture_fstop = 8.0

    cam = bpy.data.objects.new("Camera", data)
    cam.location = (0.42, -2.80, 1.12) if mode == "grid" else (0.9, -2.6, 1.25)
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

def build(cfg):
    mode = cfg["mode"].lower()
    if mode not in ("grid", "random"):
        raise ValueError("mode must be 'grid' or 'random'")

    print("\n=== cereal_box_generator ===")
    scene = reset_scene(cfg)
    hdri = build_world(scene, cfg)
    print(f"hdri     : {hdri}")
    build_ground(scene, cfg["ground_size"])

    mats = build_materials()
    meshes = build_all_meshes()

    coll = (layout_grid if mode == "grid" else layout_random)(scene, meshes, mats, cfg)
    build_camera(scene, cfg, mode)
    look_through_camera()

    print(f"mode     : {mode}")
    print(f"boxes    : {len(coll.objects)}")
    print(f"sizes    : {len(meshes)} mesh datablocks (all boxes share them)")
    print(f"shaders  : {len(mats)} cereal + Carton_Plain + UV_ColorGrid")

    if cfg["save"]:
        path = os.path.abspath(os.path.expanduser(cfg["save"]))
        base = cfg["render_dir"] or os.path.join(os.path.dirname(path), "render")
        os.makedirs(base, exist_ok=True)
        scene.render.filepath = os.path.join(base, "cereal_")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        print(f"saved    : {path}")

    if cfg["render"]:
        bpy.ops.render.render(write_still=True)
        print(f"rendered : {scene.render.filepath}")

    return scene


def build_argparser():
    p = argparse.ArgumentParser(prog="cereal_box_generator")
    p.add_argument("--mode", choices=["grid", "random"])
    p.add_argument("--count", type=int)
    p.add_argument("--area", type=float, nargs=2, metavar=("X", "Y"))
    p.add_argument("--hdri", type=str)
    p.add_argument("--builtin-hdri", type=str)
    p.add_argument("--sky-strength", type=float)
    p.add_argument("--sky-rotation", type=float)
    p.add_argument("--sun-energy", type=float)
    p.add_argument("--exposure", type=float)
    p.add_argument("--bevel", type=float)
    p.add_argument("--ground-size", type=float)
    p.add_argument("--seed", type=int)
    p.add_argument("--resolution", type=int, nargs=2, metavar=("W", "H"))
    p.add_argument("--samples", type=int)
    p.add_argument("--save", type=str)
    p.add_argument("--render", action="store_true", default=None)
    p.add_argument("--render-dir", type=str)
    return p


def config_from_cli(cfg):
    argv = sys.argv
    if "--" not in argv:
        return cfg
    args = build_argparser().parse_args(argv[argv.index("--") + 1:])
    merged = dict(cfg)
    for k, v in vars(args).items():
        if v is not None:
            merged[k] = tuple(v) if k in ("resolution", "area") else v
    return merged


if __name__ == "__main__":
    build(config_from_cli(CONFIG))
