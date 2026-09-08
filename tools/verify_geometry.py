#!/usr/bin/env python3
"""
verify_geometry.py — the guard rail for this whole system.

The dieline is computed independently in four places:

    app/daybreak-studio.html        JavaScript, in geom()
    tools/make_dielines.py          Python, in dieline_uvs()
    blender/cereal_box_generator.py Python, in build_box_mesh()
    blender/daybreak_pipeline.py    Python, in build_box_mesh()

If any one of them drifts, artwork lands misaligned on the carton — and it is
almost invisible until it reaches a press. This script recomputes the canonical
net from spec/boxes.json and checks everything reachable without Blender or a
browser against it:

  * the UV rectangles the browser wrote into every jobs/*_job.json
  * the panel rectangles baked into tools/make_dielines.py
  * the geometry constants in app/daybreak-studio.html (scraped from the
    self-test table, so the browser's own assertion stays honest)

Run it before you commit, and in CI.

    python3 tools/verify_geometry.py
    python3 tools/verify_geometry.py --tolerance 1e-9

Exit code 0 = everything agrees. 1 = drift found.
"""

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "spec", "boxes.json")
IN = 0.0254
PANELS = ["FRONT", "RIGHT", "BACK", "LEFT", "TOP", "BOTTOM"]


def repo_version():
    """The one version number, read from /VERSION at the repo root."""
    try:
        with open(os.path.join(ROOT, "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "unknown"

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = DIM = RESET = ""


def canonical(size):
    """The one true dieline. Every other implementation is checked against this."""
    W, D, H = size["w"] * IN, size["d"] * IN, size["h"] * IN
    total_w, total_h = 2 * W + 2 * D, H + 2 * D
    k = 1.0 / max(total_w, total_h)
    offx = (1.0 - total_w * k) / 2.0
    offy = (1.0 - total_h * k) / 2.0

    def r(u0, u1, v0, v1):
        return (offx + u0 * k, offx + u1 * k, offy + v0 * k, offy + v1 * k)

    return {
        "FRONT":  r(0,             W,             D,     D + H),
        "RIGHT":  r(W,             W + D,         D,     D + H),
        "BACK":   r(W + D,         2 * W + D,     D,     D + H),
        "LEFT":   r(2 * W + D,     2 * W + 2 * D, D,     D + H),
        "TOP":    r(0,             W,             D + H, D + H + D),
        "BOTTOM": r(0,             W,             0,     D),
    }


class Report:
    def __init__(self, tol):
        self.tol = tol
        self.checks = 0
        self.fails = []
        self.worst = 0.0

    def compare(self, label, size_name, panel, got, want):
        self.checks += 1
        drift = max(abs(a - b) for a, b in zip(got, want))
        self.worst = max(self.worst, drift)
        if drift > self.tol:
            self.fails.append((label, size_name, panel, drift, got, want))
        return drift

    def line(self, label, ok, detail=""):
        mark = f"{GREEN}ok{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  [{mark}] {label}{(' ' + DIM + detail + RESET) if detail else ''}")


def check_jobs(spec, rep):
    """Every job file the browser exported carries its own dieline_uv block."""
    files = sorted(glob.glob(os.path.join(ROOT, "jobs", "*_job.json")))
    if not files:
        print(f"  {DIM}no jobs/*_job.json present — skipped{RESET}")
        return
    for path in files:
        with open(path) as f:
            job = json.load(f)
        name = os.path.basename(path)
        size_name = job.get("box", {}).get("size")
        if size_name not in spec["sizes"]:
            rep.line(name, False, f"unknown size {size_name!r}")
            rep.fails.append((name, size_name, "-", float("inf"), None, None))
            continue
        want = canonical(spec["sizes"][size_name])
        uv = job.get("dieline_uv", {})
        if not uv:
            print(f"  {DIM}{name}: no dieline_uv block — skipped{RESET}")
            continue
        worst = 0.0
        for panel in PANELS:
            if panel not in uv:
                continue
            got = (uv[panel]["u0"], uv[panel]["u1"], uv[panel]["v0"], uv[panel]["v1"])
            worst = max(worst, rep.compare(name, size_name, panel, got, want[panel]))
        rep.line(f"{name} ({size_name})", worst <= rep.tol, f"max drift {worst:.2e}")


def check_make_dielines(spec, rep):
    """tools/make_dielines.py keeps its own copy of the .blend UVs as a guard."""
    path = os.path.join(ROOT, "tools", "make_dielines.py")
    if not os.path.isfile(path):
        print(f"  {DIM}tools/make_dielines.py not found — skipped{RESET}")
        return
    src = open(path).read()
    block = re.search(r"BLEND_UVS\s*=\s*\{(.*?)\n\}", src, re.S)
    if not block:
        print(f"  {DIM}no BLEND_UVS table found — skipped{RESET}")
        return
    body = block.group(1)
    for size_name in spec["sizes"]:
        # non-greedy up to the next size key or end of table, so the LAST
        # entry is not silently skipped
        m = re.search(rf'"{size_name}":\s*\{{(.*?)\}}\s*,?\s*(?=\n\s*"\w+":|\s*$)',
                      body, re.S)
        if not m:
            continue
        want = canonical(spec["sizes"][size_name])
        worst = 0.0
        for panel in PANELS:
            pm = re.search(rf'"{panel}":\s*\(([^)]+)\)', m.group(1))
            if not pm:
                continue
            got = tuple(float(x) for x in pm.group(1).split(","))
            worst = max(worst, rep.compare("make_dielines.py", size_name, panel, got, want[panel]))
        rep.line(f"make_dielines.py BLEND_UVS[{size_name}]", worst <= rep.tol,
                 f"max drift {worst:.2e}")


def check_studio_selftest(spec, rep):
    """The browser asserts against a small table at load. Keep that table true."""
    path = os.path.join(ROOT, "app", "daybreak-studio.html")
    if not os.path.isfile(path):
        print(f"  {DIM}app/daybreak-studio.html not found — skipped{RESET}")
        return
    src = open(path).read()
    block = re.search(r"const want = \{(.*?)\n  \};", src, re.S)
    if not block:
        print(f"  {DIM}no self-test table found — skipped{RESET}")
        return
    found = 0
    for size_name, panel, nums in re.findall(
            r"(\w+):\s*\{([A-Z]+):\s*\[([^\]]+)\]", block.group(1)):
        if size_name not in spec["sizes"]:
            continue
        want = canonical(spec["sizes"][size_name])
        got = tuple(float(x) for x in nums.split(","))
        drift = rep.compare("daybreak-studio.html", size_name, panel, got, want[panel])
        rep.line(f"daybreak-studio.html self-test [{size_name}/{panel}]",
                 drift <= rep.tol, f"drift {drift:.2e}")
        found += 1
    if not found:
        print(f"  {DIM}self-test table parsed but held no rows — skipped{RESET}")


def check_version(rep):
    """The app cannot read /VERSION (no fetch from file://), so it carries an
    inlined copy. That copy is a duplicate, and duplicates drift."""
    want = repo_version()
    path = os.path.join(ROOT, "app", "daybreak-studio.html")
    if not os.path.isfile(path):
        return
    m = re.search(r'const APP_VERSION = "([^"]+)"', open(path).read())
    got = m.group(1) if m else "(missing)"
    ok = got == want
    rep.checks += 1
    rep.line(f"app APP_VERSION {got} == VERSION {want}", ok)
    if not ok:
        rep.fails.append(("APP_VERSION", "-", "-", float("inf"), got, want))


def check_templates(spec, rep):
    """The SVG templates state their true size in mm in the header."""
    for size_name, size in spec["sizes"].items():
        path = os.path.join(ROOT, "templates", f"dieline_{size_name}.svg")
        if not os.path.isfile(path):
            continue
        src = open(path).read()
        m = re.search(r'width="(\d+)" height="(\d+)"', src)
        if not m:
            continue
        rep.checks += 1
        ok = m.group(1) == m.group(2)      # the canvas must stay square
        rep.line(f"templates/dieline_{size_name}.svg", ok,
                 f"canvas {m.group(1)}x{m.group(2)}")
        if not ok:
            rep.fails.append((f"dieline_{size_name}.svg", size_name, "canvas",
                              float("inf"), m.group(1), m.group(2)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tolerance", type=float, default=1e-6,
                    help="maximum allowed UV drift (default 1e-6)")
    args = ap.parse_args()

    with open(SPEC) as f:
        spec = json.load(f)

    print(f"\nDaybreak Mills — geometry verification   v{repo_version()}")
    print(f"spec: {os.path.relpath(SPEC, ROOT)}   tolerance: {args.tolerance:g}\n")

    rep = Report(args.tolerance)

    print("job files exported by the browser")
    check_jobs(spec, rep)
    print("\ntemplate generator")
    check_make_dielines(spec, rep)
    print("\nbrowser self-test table")
    check_studio_selftest(spec, rep)
    print("\ntemplate files")
    check_templates(spec, rep)
    print("\nversion")
    check_version(rep)

    print(f"\n{rep.checks} comparisons, worst drift {rep.worst:.3e}")
    if rep.fails:
        print(f"\n{RED}{len(rep.fails)} FAILED{RESET}")
        for label, size_name, panel, drift, got, want in rep.fails[:12]:
            print(f"  {label}  {size_name}/{panel}  drift {drift:.3e}")
            if got is not None:
                print(f"      got  {got}")
                print(f"      want {want}")
        geo = [f for f in rep.fails if f[0] != "APP_VERSION"]
        if geo:
            print("\nThe dieline implementations disagree. Artwork will land misaligned.")
        if len(geo) < len(rep.fails):
            print("\nVersion mismatch: bump the app with  python3 tools/release.py --bump <part>")
        return 1

    print(f"{GREEN}All implementations agree.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
