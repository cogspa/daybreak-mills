"""
make_dielines.py — build labelled dieline artwork templates for the cereal boxes.

Emits, per box size:
    dieline_<Size>.svg   layered, panels on named layers, editable in
                         Illustrator / Affinity / Figma / Inkscape
    dieline_<Size>.png   flat guide at texture resolution, to drop straight into
                         Blender's UV editor as a background or onto the box

The panel rectangles are the EXACT Dieline UVs baked into cereal_boxes.blend.
They are recomputed here from the box dimensions and then asserted against the
values read back out of the .blend, so the templates cannot silently drift
from the mesh.
"""

import json
import os

from PIL import Image, ImageDraw, ImageFont

OUT = "/home/claude/templates"
PX = 4096                     # texture resolution the templates are drawn at
IN = 0.0254
SAFE_MM = 4.0                 # keep live matter this far off every fold and trim

FONT_DIR = "/usr/share/fonts/truetype"
F_BOLD = f"{FONT_DIR}/dejavu/DejaVuSans-Bold.ttf"
F_REG = f"{FONT_DIR}/dejavu/DejaVuSans.ttf"
F_MONO = f"{FONT_DIR}/dejavu/DejaVuSansMono.ttf"

# name: (height, width, depth) in inches — as sold
SIZES = {
    "Regular": (12.0, 7.75, 2.50),
    "Family":  (13.0, 7.75, 3.00),
    "Mega":    (13.5, 9.50, 3.15),
    "Mini":    (6.5,  4.00, 1.50),
}

# read back out of cereal_boxes.blend — the source of truth
BLEND_UVS = {
  "Regular": {"FRONT": (0.0,0.378049,0.207317,0.792683), "RIGHT": (0.378049,0.5,0.207317,0.792683),
              "BACK": (0.5,0.878049,0.207317,0.792683), "LEFT": (0.878049,1.0,0.207317,0.792683),
              "TOP": (0.0,0.378049,0.792683,0.914634), "BOTTOM": (0.0,0.378049,0.085366,0.207317)},
  "Family":  {"FRONT": (0.0,0.360465,0.197674,0.802326), "RIGHT": (0.360465,0.5,0.197674,0.802326),
              "BACK": (0.5,0.860465,0.197674,0.802326), "LEFT": (0.860465,1.0,0.197674,0.802326),
              "TOP": (0.0,0.360465,0.802326,0.94186), "BOTTOM": (0.0,0.360465,0.05814,0.197674)},
  "Mega":    {"FRONT": (0.0,0.375494,0.233202,0.766798), "RIGHT": (0.375494,0.5,0.233202,0.766798),
              "BACK": (0.5,0.875494,0.233202,0.766798), "LEFT": (0.875494,1.0,0.233202,0.766798),
              "TOP": (0.0,0.375494,0.766798,0.891304), "BOTTOM": (0.0,0.375494,0.108696,0.233202)},
  "Mini":    {"FRONT": (0.0,0.363636,0.204545,0.795455), "RIGHT": (0.363636,0.5,0.204545,0.795455),
              "BACK": (0.5,0.863636,0.204545,0.795455), "LEFT": (0.863636,1.0,0.204545,0.795455),
              "TOP": (0.0,0.363636,0.795455,0.931818), "BOTTOM": (0.0,0.363636,0.068182,0.204545)},
}

INK      = "#171a1f"
PAPER    = "#f3f1ec"
MARGIN   = "#e3e0d8"
FOLD     = "#8d96a5"
SAFE     = "#c8543a"
GRIDLINE = "#b9c2cf"

PANEL_FILL = {
    "FRONT":  "#ffffff",
    "BACK":   "#faf8f4",
    "RIGHT":  "#eef1f5",
    "LEFT":   "#eef1f5",
    "TOP":    "#e8eef0",
    "BOTTOM": "#e8eef0",
}
PANEL_ROLE = {
    "FRONT":  "hero panel — logo, flavour, product shot",
    "BACK":   "activity / story panel",
    "RIGHT":  "nutrition facts + ingredients",
    "LEFT":   "brand story, recipe, claims",
    "TOP":    "flap — brand mark only",
    "BOTTOM": "flap — barcode, batch code",
}


def dieline_uvs(W, D, H):
    """Recompute the same net the Blender mesh uses, so the two cannot drift."""
    total_w = 2 * W + 2 * D
    total_h = H + 2 * D
    s = 1.0 / max(total_w, total_h)
    offx = (1.0 - total_w * s) / 2.0
    offy = (1.0 - total_h * s) / 2.0

    def rect(u0, u1, v0, v1):
        return (offx + u0 * s, offx + u1 * s, offy + v0 * s, offy + v1 * s)

    return {
        "FRONT":  rect(0,           W,           D,     D + H),
        "RIGHT":  rect(W,           W + D,       D,     D + H),
        "BACK":   rect(W + D,       2 * W + D,   D,     D + H),
        "LEFT":   rect(2 * W + D,   2 * W + 2 * D, D,   D + H),
        "TOP":    rect(0,           W,           D + H, D + H + D),
        "BOTTOM": rect(0,           W,           0,     D),
    }, s


def build(size_name, verbose=True):
    h_in, w_in, d_in = SIZES[size_name]
    W, D, H = w_in * IN, d_in * IN, h_in * IN
    uvs, s = dieline_uvs(W, D, H)

    # --- guard: the template must match what is actually in the .blend ---
    for panel, got in uvs.items():
        want = BLEND_UVS[size_name][panel]
        for a, b in zip(got, want):
            assert abs(a - b) < 1e-5, f"{size_name}/{panel} drifted from the .blend: {got} vs {want}"

    px_per_m = PX * s
    px_per_mm = px_per_m / 1000.0
    safe_px = SAFE_MM * px_per_mm
    front_dpi = (uvs["FRONT"][1] - uvs["FRONT"][0]) * PX / (W / IN)

    def to_px(u0, u1, v0, v1):
        """UV -> pixels. v runs bottom-up in UV space, y runs top-down in images."""
        return (u0 * PX, (1.0 - v1) * PX, u1 * PX, (1.0 - v0) * PX)

    rects = {k: to_px(*v) for k, v in uvs.items()}
    mm = {"FRONT": (W, H), "BACK": (W, H), "RIGHT": (D, H),
          "LEFT": (D, H), "TOP": (W, D), "BOTTOM": (W, D)}

    os.makedirs(OUT, exist_ok=True)
    write_png(size_name, rects, mm, safe_px, px_per_mm, front_dpi)
    write_svg(size_name, rects, mm, safe_px, px_per_mm, front_dpi, (h_in, w_in, d_in))

    if verbose:
        f = rects["FRONT"]
        print(f"{size_name:8s} front panel {int(f[2]-f[0])} x {int(f[3]-f[1])} px "
              f"| {front_dpi:.0f} DPI | safe inset {safe_px:.0f} px ({SAFE_MM} mm)")
    return {"size": size_name, "front_px": [int(rects['FRONT'][2]-rects['FRONT'][0]),
                                            int(rects['FRONT'][3]-rects['FRONT'][1])],
            "dpi": round(front_dpi, 1), "px_per_mm": round(px_per_mm, 3),
            "safe_px": round(safe_px, 1)}


def write_png(name, rects, mm, safe_px, px_per_mm, dpi):
    img = Image.new("RGB", (PX, PX), MARGIN)
    d = ImageDraw.Draw(img)

    def font(path, size):
        return ImageFont.truetype(path, max(8, int(size)))

    big = font(F_BOLD, PX * 0.020)
    med = font(F_REG, PX * 0.0105)
    small = font(F_MONO, PX * 0.0082)
    tiny = font(F_MONO, PX * 0.0068)

    for panel, (x0, y0, x1, y1) in rects.items():
        d.rectangle([x0, y0, x1, y1], fill=PANEL_FILL[panel])

    # design grid on the front panel: 12 columns, 16 rows
    fx0, fy0, fx1, fy1 = rects["FRONT"]
    for i in range(1, 12):
        x = fx0 + (fx1 - fx0) * i / 12.0
        d.line([x, fy0, x, fy1], fill=GRIDLINE, width=1)
    for i in range(1, 16):
        y = fy0 + (fy1 - fy0) * i / 16.0
        d.line([fx0, y, fx1, y], fill=GRIDLINE, width=1)

    # safe area, dashed
    for panel, (x0, y0, x1, y1) in rects.items():
        dash(d, x0 + safe_px, y0 + safe_px, x1 - safe_px, y1 - safe_px, SAFE, 3, 26, 20)

    # fold lines between panels
    for panel, (x0, y0, x1, y1) in rects.items():
        d.rectangle([x0, y0, x1, y1], outline=FOLD, width=3)

    for panel, (x0, y0, x1, y1) in rects.items():
        w_m, h_m = mm[panel]
        label = panel
        sub = f"{w_m*1000:.0f} x {h_m*1000:.0f} mm"
        sub2 = f"{int(x1-x0)} x {int(y1-y0)} px"
        role = PANEL_ROLE[panel]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        use_big = (x1 - x0) > PX * 0.2
        fnt = big if use_big else font(F_BOLD, PX * 0.011)
        centre(d, cx, cy - (60 if use_big else 34), label, fnt, INK)
        centre(d, cx, cy + (18 if use_big else 4), sub, med if use_big else tiny, "#5b6472")
        centre(d, cx, cy + (66 if use_big else 30), sub2, small if use_big else tiny, "#8d96a5")
        if use_big:
            centre(d, cx, cy + 118, role, med, "#8d96a5")

    # title block: the clear margin to the right of the TOP flap, above the
    # right/back/left strip. Sits in dead UV space so it never covers artwork.
    tx, ty = rects["FRONT"][2] + PX * 0.022, PX * 0.030
    d.text((tx, ty), f"CEREAL BOX DIELINE — {name.upper()}", font=font(F_BOLD, PX * 0.0135), fill=INK)
    lines = [
        f"UV map: 'Dieline'   canvas {PX} x {PX} px",
        f"front panel {int(rects['FRONT'][2]-rects['FRONT'][0])} x "
        f"{int(rects['FRONT'][3]-rects['FRONT'][1])} px  =  {dpi:.0f} DPI at final size",
        f"scale {px_per_mm:.3f} px/mm    safe area {SAFE_MM:.0f} mm ({safe_px:.0f} px) inset, dashed red",
        "grey rules = fold lines   ·   light blue = 12x16 design grid on the front panel",
        "art must bleed to the panel edge; keep live matter inside the dashed line",
    ]
    for i, ln in enumerate(lines):
        d.text((tx, ty + PX * 0.026 + i * PX * 0.0125), ln, font=small, fill="#5b6472")

    img.save(f"{OUT}/dieline_{name}.png", optimize=True)


def dash(d, x0, y0, x1, y1, colour, width, on, off):
    def seg(ax, ay, bx, by):
        import math
        dist = math.hypot(bx - ax, by - ay)
        if dist <= 0:
            return
        step = on + off
        t = 0.0
        while t < dist:
            t2 = min(t + on, dist)
            d.line([ax + (bx - ax) * t / dist, ay + (by - ay) * t / dist,
                    ax + (bx - ax) * t2 / dist, ay + (by - ay) * t2 / dist],
                   fill=colour, width=width)
            t += step
    seg(x0, y0, x1, y0); seg(x1, y0, x1, y1); seg(x1, y1, x0, y1); seg(x0, y1, x0, y0)


def centre(d, cx, cy, text, font, fill):
    box = d.textbbox((0, 0), text, font=font)
    d.text((cx - (box[2] - box[0]) / 2.0, cy - (box[3] - box[1]) / 2.0), text, font=font, fill=fill)


def write_svg(name, rects, mm, safe_px, px_per_mm, dpi, inches):
    h_in, w_in, d_in = inches
    P = []
    A = P.append
    A(f'<?xml version="1.0" encoding="UTF-8"?>')
    A(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
      f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
      f'width="{PX}" height="{PX}" viewBox="0 0 {PX} {PX}">')
    A(f'  <title>Cereal box dieline — {name}</title>')
    A(f'  <desc>Matches the "Dieline" UV map in cereal_boxes.blend. '
      f'{w_in}" x {d_in}" x {h_in}" (W x D x H). {px_per_mm:.4f} px/mm at {PX}px. '
      f'Front panel resolves to {dpi:.0f} DPI at final printed size.</desc>')

    A(f'  <g id="background" inkscape:groupmode="layer" inkscape:label="00 background">')
    A(f'    <rect x="0" y="0" width="{PX}" height="{PX}" fill="{MARGIN}"/>')
    A(f'  </g>')

    A(f'  <g id="panels" inkscape:groupmode="layer" inkscape:label="01 panels">')
    for panel, (x0, y0, x1, y1) in rects.items():
        A(f'    <rect id="panel-{panel.lower()}" x="{x0:.2f}" y="{y0:.2f}" '
          f'width="{x1-x0:.2f}" height="{y1-y0:.2f}" fill="{PANEL_FILL[panel]}"/>')
    A(f'  </g>')

    fx0, fy0, fx1, fy1 = rects["FRONT"]
    A(f'  <g id="grid" inkscape:groupmode="layer" inkscape:label="02 front grid 12x16" '
      f'stroke="{GRIDLINE}" stroke-width="1">')
    for i in range(1, 12):
        x = fx0 + (fx1 - fx0) * i / 12.0
        A(f'    <line x1="{x:.2f}" y1="{fy0:.2f}" x2="{x:.2f}" y2="{fy1:.2f}"/>')
    for i in range(1, 16):
        y = fy0 + (fy1 - fy0) * i / 16.0
        A(f'    <line x1="{fx0:.2f}" y1="{y:.2f}" x2="{fx1:.2f}" y2="{y:.2f}"/>')
    A(f'  </g>')

    A(f'  <g id="folds" inkscape:groupmode="layer" inkscape:label="03 fold lines" '
      f'fill="none" stroke="{FOLD}" stroke-width="3">')
    for panel, (x0, y0, x1, y1) in rects.items():
        A(f'    <rect x="{x0:.2f}" y="{y0:.2f}" width="{x1-x0:.2f}" height="{y1-y0:.2f}"/>')
    A(f'  </g>')

    A(f'  <g id="safe-area" inkscape:groupmode="layer" inkscape:label="04 safe area {SAFE_MM:.0f}mm" '
      f'fill="none" stroke="{SAFE}" stroke-width="3" stroke-dasharray="26 20">')
    for panel, (x0, y0, x1, y1) in rects.items():
        A(f'    <rect x="{x0+safe_px:.2f}" y="{y0+safe_px:.2f}" '
          f'width="{x1-x0-2*safe_px:.2f}" height="{y1-y0-2*safe_px:.2f}"/>')
    A(f'  </g>')

    A(f'  <g id="labels" inkscape:groupmode="layer" inkscape:label="05 labels" '
      f'font-family="Helvetica, Arial, sans-serif" text-anchor="middle">')
    for panel, (x0, y0, x1, y1) in rects.items():
        w_m, h_m = mm[panel]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        big = (x1 - x0) > PX * 0.2
        fs = PX * 0.020 if big else PX * 0.011
        A(f'    <text x="{cx:.1f}" y="{cy - (fs*0.9 if big else fs*0.8):.1f}" '
          f'font-size="{fs:.1f}" font-weight="700" fill="{INK}">{panel}</text>')
        A(f'    <text x="{cx:.1f}" y="{cy + (fs*0.35 if big else fs*0.55):.1f}" '
          f'font-size="{PX*0.0105 if big else PX*0.0068:.1f}" fill="#5b6472">'
          f'{w_m*1000:.0f} × {h_m*1000:.0f} mm</text>')
        A(f'    <text x="{cx:.1f}" y="{cy + (fs*1.1 if big else fs*1.3):.1f}" '
          f'font-size="{PX*0.0082 if big else PX*0.0068:.1f}" fill="#8d96a5">'
          f'{int(x1-x0)} × {int(y1-y0)} px</text>')
        if big:
            A(f'    <text x="{cx:.1f}" y="{cy + fs*2.0:.1f}" font-size="{PX*0.0105:.1f}" '
              f'fill="#8d96a5">{PANEL_ROLE[panel]}</text>')
    A(f'  </g>')

    tx, ty = fx1 + PX * 0.022, PX * 0.048
    A(f'  <g id="title-block" inkscape:groupmode="layer" inkscape:label="06 title block" '
      f'font-family="Helvetica, Arial, sans-serif">')
    A(f'    <text x="{tx:.0f}" y="{ty:.0f}" font-size="{PX*0.0135:.1f}" font-weight="700" '
      f'fill="{INK}">CEREAL BOX DIELINE — {name.upper()}</text>')
    info = [
        f"UV map: &apos;Dieline&apos;   canvas {PX} × {PX} px",
        f"front panel {int(fx1-fx0)} × {int(fy1-fy0)} px  =  {dpi:.0f} DPI at final size",
        f"scale {px_per_mm:.3f} px/mm    safe area {SAFE_MM:.0f} mm ({safe_px:.0f} px) inset, dashed red",
        "grey rules = fold lines   ·   light blue = 12×16 design grid on the front panel",
        "art must bleed to the panel edge; keep live matter inside the dashed line",
    ]
    for i, ln in enumerate(info):
        A(f'    <text x="{tx:.0f}" y="{ty + PX*0.026 + i*PX*0.0125:.0f}" '
          f'font-size="{PX*0.0082:.1f}" fill="#5b6472">{ln}</text>')
    A(f'  </g>')
    A('</svg>')

    with open(f"{OUT}/dieline_{name}.svg", "w") as f:
        f.write("\n".join(P))


if __name__ == "__main__":
    summary = [build(n) for n in ("Regular", "Family", "Mega", "Mini")]
    print("\nall four templates verified against the .blend UVs")
    print(json.dumps(summary, indent=2))
