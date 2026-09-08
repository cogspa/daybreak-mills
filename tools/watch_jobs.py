#!/usr/bin/env python3
"""
watch_jobs.py — closes the gap between the browser and Blender.

A web page cannot write outside the downloads folder or launch an application,
so this watcher does both. Leave it running; export from daybreak-studio.html;
a render appears.

    python3 tools/watch_jobs.py

It polls two folders:

    jobs/          anything you drop in yourself
    ~/Downloads    where the browser actually puts exports (--no-downloads off)

When it sees a `*_job.json` whose texture has finished downloading, it moves the
pair into `jobs/` and runs `blender --background --python daybreak_pipeline.py`.

A range zip (`daybreak_range_*.zip` / `daybreak_matrix_*.zip`, exported from the
studio's "Export the range" button) is extracted into its own `jobs/<name>/`
folder and built as ONE lineup scene — every flavour side by side. A zip is only
touched once its size has settled and its end-of-central-directory record is
present, for the same reason PNGs are checked for IEND.

`jobs/status.html` is rewritten after every event. Open it in a browser and
leave it: it refreshes itself and shows each build with its render.

Handling partial downloads is the whole trick. A browser writes a large PNG over
several seconds, so a job is only picked up once:

  * the job JSON parses,
  * the texture named in its "texture" field exists, and
  * both files have had the same size for two consecutive polls.

Processed jobs are recorded in `jobs/.processed.json` by name, size and mtime,
so re-running the watcher does not rebuild everything, but re-exporting the same
job (which changes its size or mtime) does.

    --once              process what is already there, then exit
    --no-downloads      only watch jobs/
    --downloads PATH    watch somewhere else
    --mode hero|lineup  a render per job, or one lineup of everything (default hero)
    --interval 2.0      seconds between polls
    --hdri PATH         passed through to the pipeline
    --blender PATH      skip auto-detection
    --dry-run           show the command instead of running it
    --open              after each build, open the saved .blend in the Blender GUI
                        (the build itself always runs headless; this just hands
                        you the finished scene to look at)

Ctrl-C to stop.
"""

import argparse
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "jobs")
PIPELINE = os.path.join(ROOT, "blender", "daybreak_pipeline.py")
LEDGER = os.path.join(JOBS, ".processed.json")
CONFIG = os.path.join(ROOT, "daybreak.config.json")
HISTORY = os.path.join(JOBS, ".history.json")
STATUS = os.path.join(JOBS, "status.html")


def repo_version():
    """The one version number, read from /VERSION at the repo root."""
    try:
        with open(os.path.join(ROOT, "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "unknown"

GREEN, RED, YELL, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELL = DIM = RESET = ""


# ==============================================================================
# Finding Blender
# ==============================================================================

def find_blender(explicit=""):
    """Locate the Blender binary. Never hardcode a path — installs are named
    inconsistently (this was developed against '/Applications/Blender 3.app',
    which has both a space and a version in the bundle name)."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None

    # a chosen install beats auto-detection: daybreak.config.json {"blender": path}
    chosen = read_config().get("blender")
    if chosen and os.path.isfile(chosen):
        return chosen

    on_path = shutil.which("blender")
    if on_path:
        return on_path

    system = platform.system()
    patterns = []
    if system == "Darwin":
        patterns = [
            "/Applications/Blender*.app/Contents/MacOS/Blender",
            os.path.expanduser("~/Applications/Blender*.app/Contents/MacOS/Blender"),
        ]
    elif system == "Windows":
        patterns = [
            r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
            r"C:\Program Files (x86)\Blender Foundation\Blender*\blender.exe",
        ]
    else:
        patterns = [
            "/usr/bin/blender", "/usr/local/bin/blender",
            "/opt/blender*/blender",
            os.path.expanduser("~/blender*/blender"),
            os.path.expanduser("~/.local/share/flatpak/exports/bin/org.blender.Blender"),
        ]

    hits = []
    for pat in patterns:
        hits.extend(glob.glob(pat))
    hits = [h for h in hits if os.path.isfile(h)]
    if not hits:
        return None
    # Newest install wins — by REAL version, not by name. On one machine
    # "Blender.app" was 4.5 LTS while "Blender 3.app" was 5.1; an alphabetical
    # sort picked the oldest. Read the bundle's plist on macOS, else ask the
    # binary, and rank numerically.
    return max(hits, key=blender_version)


def read_config():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except Exception:
        return {}


def write_config(**changes):
    cfg = read_config()
    cfg.update(changes)
    with open(CONFIG + ".tmp", "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(CONFIG + ".tmp", CONFIG)
    return cfg


def list_blenders():
    """Every install we can see, with its version — for choosing one."""
    system = platform.system()
    pats = {"Darwin": ["/Applications/Blender*.app/Contents/MacOS/Blender",
                       os.path.expanduser("~/Applications/Blender*.app/Contents/MacOS/Blender")],
            "Windows": [r"C:\Program Files\Blender Foundation\Blender*\blender.exe"]
            }.get(system, ["/usr/bin/blender", "/usr/local/bin/blender", "/opt/blender*/blender",
                           os.path.expanduser("~/blender*/blender")])
    hits = set()
    for pat in pats:
        hits.update(h for h in glob.glob(pat) if os.path.isfile(h))
    on_path = shutil.which("blender")
    if on_path:
        hits.add(os.path.realpath(on_path))
    out = [{"path": h, "version": ".".join(map(str, blender_version(h)))} for h in sorted(hits)]
    out.sort(key=lambda b: tuple(int(x) for x in b["version"].split(".")), reverse=True)
    return out


_VERSION_CACHE = {}


def blender_version(binary):
    """(major, minor, patch) for an install, without launching it if possible.
    Cached per path: without this, status polls and picker refreshes shelled out
    to `blender --version` dozens of times (45 in one start-up during testing)."""
    if binary in _VERSION_CACHE:
        return _VERSION_CACHE[binary]
    v = _blender_version_uncached(binary)
    _VERSION_CACHE[binary] = v
    return v


def _blender_version_uncached(binary):
    if platform.system() == "Darwin":
        plist = os.path.join(os.path.dirname(os.path.dirname(binary)), "Info.plist")
        try:
            import plistlib
            with open(plist, "rb") as f:
                v = plistlib.load(f).get("CFBundleShortVersionString", "")
            parts = tuple(int(x) for x in v.split(".")[:3] if x.isdigit())
            if parts:
                return parts + (0,) * (3 - len(parts))
        except Exception:
            pass
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True,
                             timeout=30).stdout
        m = __import__("re").search(r"Blender (\d+)\.(\d+)(?:\.(\d+))?", out)
        if m:
            return tuple(int(x or 0) for x in m.groups())
    except Exception:
        pass
    return (0, 0, 0)


# ==============================================================================
# Ledger — what has already been built
# ==============================================================================

def load_ledger():
    try:
        with open(LEDGER) as f:
            return json.load(f)
    except Exception:
        return {}


def save_ledger(led):
    os.makedirs(JOBS, exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(led, f, indent=1)
    os.replace(tmp, LEDGER)


def fingerprint(*paths):
    parts = []
    for p in paths:
        try:
            st = os.stat(p)
            parts.append(f"{os.path.basename(p)}:{st.st_size}:{int(st.st_mtime)}")
        except OSError:
            parts.append(f"{os.path.basename(p)}:missing")
    return "|".join(parts)


# ==============================================================================
# Candidate detection
# ==============================================================================

def png_complete(path):
    """A PNG declares its own end with an IEND chunk. Size-stability alone
    cannot tell a finished download from a stalled one, so check the trailer
    too — a truncated texture would otherwise be baked onto a carton."""
    try:
        if os.path.getsize(path) < 33:          # smaller than a valid header+IEND
            return False
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return True                     # not a PNG; nothing to assert
            f.seek(-12, os.SEEK_END)
            return b"IEND" in f.read(12)
    except OSError:
        return False


def zip_complete(path):
    """A zip ends with an end-of-central-directory record (PK\x05\x06). Its
    absence means the download is still in flight."""
    try:
        if os.path.getsize(path) < 22:
            return False
        with open(path, "rb") as f:
            f.seek(-22, os.SEEK_END)
            return f.read(4) == b"PK\x05\x06"
    except OSError:
        return False


def sizes_of(*paths):
    out = []
    for p in paths:
        try:
            out.append(os.path.getsize(p))
        except OSError:
            out.append(-1)
    return tuple(out)


def candidates(folders):
    """Every *_job.json we can see, paired with the texture it names — plus any
    range zip, which stands in for a whole set of them."""
    found = []
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for zpath in sorted(glob.glob(os.path.join(folder, "daybreak_*.zip"))):
            found.append({"zip": zpath, "json": zpath, "tex": "", "job": {}, "folder": folder})
        for jpath in sorted(glob.glob(os.path.join(folder, "*_job.json"))):
            try:
                with open(jpath) as f:
                    job = json.load(f)
            except Exception:
                continue                      # still being written — try next poll
            tex_name = job.get("texture", "")
            tpath = os.path.join(folder, tex_name) if tex_name else ""
            found.append({"json": jpath, "tex": tpath, "job": job, "folder": folder})
    return found


def move_into_jobs(cand):
    """Bring a pair in from Downloads. Files already in jobs/ are left alone."""
    if os.path.abspath(cand["folder"]) == os.path.abspath(JOBS):
        return cand["json"], cand["tex"]
    os.makedirs(JOBS, exist_ok=True)
    dst_json = os.path.join(JOBS, os.path.basename(cand["json"]))
    dst_tex = os.path.join(JOBS, os.path.basename(cand["tex"])) if cand["tex"] else ""
    shutil.move(cand["json"], dst_json)
    if cand["tex"] and os.path.isfile(cand["tex"]):
        shutil.move(cand["tex"], dst_tex)
    return dst_json, dst_tex


# ==============================================================================
# Running Blender
# ==============================================================================

def run_blender(blender, args, job_name, dry=False):
    cmd = [blender, "--background", "--python", PIPELINE, "--"] + args
    if dry:
        print(f"  {DIM}would run:{RESET} {' '.join(repr(c) if ' ' in c else c for c in cmd)}")
        return True

    print(f"  {DIM}$ {os.path.basename(blender)} --background --python "
          f"daybreak_pipeline.py -- {' '.join(args)}{RESET}")
    t = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        print(f"  [{RED}timeout{RESET}] Blender did not finish within 15 minutes")
        return False
    except OSError as e:
        print(f"  [{RED}error{RESET}] could not start Blender: {e}")
        return False

    secs = time.time() - t
    if p.returncode != 0:
        print(f"  [{RED}FAIL{RESET}] Blender exited {p.returncode} after {secs:.1f}s")
        tail = (p.stdout or "").strip().splitlines()[-12:]
        for line in tail:
            print(f"    {DIM}{line}{RESET}")
        if p.stderr.strip():
            for line in p.stderr.strip().splitlines()[-6:]:
                print(f"    {RED}{line}{RESET}")
        return False

    # surface the lines that matter rather than the whole Blender log
    for line in (p.stdout or "").splitlines():
        s = line.strip()
        if any(k in s for k in ("UV check", "[FAIL]", "[warn]", "boxes built",
                                "rendered", "saved", "sun matched")):
            print(f"    {s}")
    print(f"  [{GREEN}ok{RESET}] {job_name} in {secs:.1f}s")
    return True


# ==============================================================================
# Main loop
# ==============================================================================

def process(cand, blender, cfg, led, history):
    name = os.path.basename(cand["json"])
    box = cand["job"].get("box", {}).get("size", "?")
    flav = cand["job"].get("flavour", {}).get("name", "?")
    print(f"\n{YELL}→{RESET} {name}  {DIM}({box} · {flav}){RESET}")

    jpath, tpath = move_into_jobs(cand)
    if cand["folder"] != JOBS:
        print(f"  moved into jobs/ from {os.path.basename(cand['folder'])}/")

    stem = os.path.basename(jpath).replace("_job.json", "")
    blend = os.path.join(JOBS, "renders", stem + ".blend")
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    args = ["--jobs", JOBS, "--one", stem, "--render", "--save", blend]
    if cfg["hdri"]:
        args += ["--hdri", cfg["hdri"]]
    if cfg["mode"] == "hero":
        args += ["--hero"]

    ok = run_blender(blender, args, name, cfg["dry_run"])
    if ok and not cfg["dry_run"]:
        led[os.path.basename(jpath)] = fingerprint(jpath, tpath)
        save_ledger(led)
        render = os.path.join(JOBS, "renders", "daybreak_.png")
        shown = os.path.join(JOBS, "renders", stem + ".png")
        if os.path.isfile(render):
            os.replace(render, shown)
        history.insert(0, {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "box",
                           "name": stem, "boxes": 1,
                           "size": box, "flavour": flav,
                           "claim": cand["job"].get("copy", {}).get("claim", ""),
                           "brief": cand["job"].get("brief", {}),
                           "render": os.path.relpath(shown, JOBS) if os.path.isfile(shown) else None,
                           "blend": os.path.relpath(blend, JOBS)})
        write_status(history)
        if cfg["open"] and os.path.isfile(blend):
            open_in_gui(blender, blend)
    return ok


def load_history():
    try:
        with open(HISTORY) as f:
            return json.load(f)
    except Exception:
        return []


def write_status(history):
    """A self-refreshing page the watcher rewrites after every build. No server:
    it is a plain file with a meta refresh, so it works from file:// like the
    studio does."""
    history = history[:40]
    with open(HISTORY + ".tmp", "w") as f:
        json.dump(history, f, indent=1)
    os.replace(HISTORY + ".tmp", HISTORY)

    def esc(t):
        return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    cards = []
    for h in history:
        brief = h.get("brief") or {}
        bl = " · ".join(f"{k} {v}" for k, v in brief.items()) if brief else ""
        title = (f"{h.get('boxes',1)} boxes — {esc(h.get('mode',''))} range" if h["kind"] == "range"
                 else f"{esc(h.get('size',''))} · {esc(h.get('flavour',''))}")
        img = (f'<img src="{esc(h["render"])}?t={int(time.time())}" alt="">'
               if h.get("render") else '<div class="nor">no render</div>')
        cards.append(f'''
      <article class="card {h["kind"]}">
        {img}
        <div class="meta">
          <div class="t">{title}</div>
          <div class="s">{esc(h.get("claim", ""))}</div>
          <div class="b">{esc(bl)}</div>
          <div class="w">{esc(h["when"])} · <code>{esc(h.get("blend",""))}</code></div>
        </div>
      </article>''')

    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="3"><title>Daybreak Mills — builds</title>
<style>
  body{{margin:0;background:#0f1319;color:#e8ecf2;font:14px/1.5 -apple-system,Helvetica,Arial,sans-serif}}
  header{{background:#16233a;padding:12px 20px;display:flex;align-items:center;gap:14px}}
  .mark{{background:#f4efe6;color:#16233a;font-weight:900;font-size:11px;letter-spacing:.16em;padding:6px 11px 5px;border-radius:3px}}
  header span{{color:#93a1b6;font-family:ui-monospace,Menlo,monospace;font-size:11px}}
  main{{padding:18px 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}}
  .card{{background:#171d26;border:1px solid #2b3441;border-radius:9px;overflow:hidden}}
  .card.range{{grid-column:1/-1}}
  .card img{{display:block;width:100%;height:auto;background:#0a0d12}}
  .nor{{height:180px;display:grid;place-items:center;color:#778397;font-style:italic}}
  .meta{{padding:12px 14px 14px}}
  .t{{font-weight:700;font-size:15px}} .s{{color:#a3aebe;font-size:13px;margin-top:2px}}
  .b{{color:#778397;font-size:12px;margin-top:6px}} .w{{color:#5f6b7e;font-size:11px;margin-top:6px;font-family:ui-monospace,Menlo,monospace}}
  .empty{{grid-column:1/-1;color:#778397;padding:40px;text-align:center;font-style:italic}}
</style></head><body>
<header><div class="mark">DAYBREAK MILLS</div><span>builds · refreshes every 3 s · v{repo_version()}</span></header>
<main>{"".join(cards) if cards else '<div class="empty">Nothing built yet. Export from the studio and it will appear here.</div>'}</main>
</body></html>'''
    with open(STATUS + ".tmp", "w") as f:
        f.write(html)
    os.replace(STATUS + ".tmp", STATUS)


def open_in_gui(blender, blend):
    """Hand the finished scene to a real Blender window. Non-blocking, so the
    watcher keeps watching. Each job opens its own window; close them as you go."""
    try:
        subprocess.Popen([blender, blend],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  {DIM}opened in Blender: {os.path.relpath(blend, ROOT)}{RESET}")
    except OSError as e:
        print(f"  [{YELL}warn{RESET}] could not open the GUI: {e}")


def process_range(cand, blender, cfg, led, history):
    import zipfile
    zpath = cand["zip"]
    stem = os.path.splitext(os.path.basename(zpath))[0]
    dest = os.path.join(JOBS, stem)
    print(f"\n{YELL}→{RESET} {os.path.basename(zpath)}  {DIM}(range){RESET}")

    if os.path.abspath(cand["folder"]) != os.path.abspath(JOBS):
        os.makedirs(JOBS, exist_ok=True)
        moved = os.path.join(JOBS, os.path.basename(zpath))
        shutil.move(zpath, moved)
        zpath = moved
        print(f"  moved into jobs/ from {os.path.basename(cand['folder'])}/")

    try:
        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
            if "range.json" not in names:
                print(f"  [{RED}skip{RESET}] no range.json inside — not a Daybreak range zip")
                return False
            os.makedirs(dest, exist_ok=True)
            zf.extractall(dest)
    except zipfile.BadZipFile as e:
        print(f"  [{RED}skip{RESET}] bad zip: {e}")
        return False

    with open(os.path.join(dest, "range.json")) as f:
        manifest = json.load(f)
    jobs = manifest.get("jobs", [])
    print(f"  {len(jobs)} boxes · {manifest.get('mode','?')} · "
          f"sizes {', '.join(manifest.get('sizes', []))}")

    blend = os.path.join(JOBS, "renders", stem + ".blend")
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    args = ["--jobs", dest, "--render", "--save", blend]
    if cfg["hdri"]:
        args += ["--hdri", cfg["hdri"]]
    if len(jobs) == 1:
        args += ["--hero"]

    ok = run_blender(blender, args, stem, cfg["dry_run"])
    if ok and not cfg["dry_run"]:
        led[os.path.basename(zpath)] = fingerprint(zpath)
        save_ledger(led)
        # the pipeline writes to <--jobs>/renders/, and for a range --jobs is
        # the range's own folder — not jobs/. Bring it up beside the .blend.
        render = os.path.join(dest, "renders", "daybreak_.png")
        shown = os.path.join(JOBS, "renders", stem + ".png")
        if os.path.isfile(render):
            os.replace(render, shown)
        history.insert(0, {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "range",
                           "name": stem, "boxes": len(jobs), "mode": manifest.get("mode"),
                           "brief": manifest.get("brief", {}),
                           "render": os.path.relpath(shown, JOBS) if os.path.isfile(shown) else None,
                           "blend": os.path.relpath(blend, JOBS)})
        write_status(history)
        if cfg["open"] and os.path.isfile(blend):
            open_in_gui(blender, blend)
        return {"ok": True, "name": stem, "boxes": len(jobs),
                "render": os.path.relpath(shown, JOBS) if os.path.isfile(shown) else None,
                "blend": os.path.relpath(blend, JOBS)}
    return ok


def build_lineup(blender, cfg):
    args = ["--jobs", JOBS, "--render",
            "--save", os.path.join(ROOT, "daybreak_lineup.blend")]
    if cfg["hdri"]:
        args += ["--hdri", cfg["hdri"]]
    print(f"\n{YELL}→{RESET} rebuilding the full lineup")
    return run_blender(blender, args, "lineup", cfg["dry_run"])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--no-downloads", action="store_true")
    ap.add_argument("--downloads", default=os.path.expanduser("~/Downloads"))
    ap.add_argument("--mode", choices=["hero", "lineup"], default="hero")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--hdri", default="")
    ap.add_argument("--blender", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--open", action="store_true",
                    help="open each finished .blend in the Blender GUI")
    a = ap.parse_args()

    blender = find_blender(a.blender)
    if not blender:
        print(f"{RED}Could not find Blender.{RESET}\n"
              f"Pass it explicitly:\n"
              f"  python3 tools/watch_jobs.py --blender "
              f"'/Applications/Blender.app/Contents/MacOS/Blender'")
        return 2
    if not os.path.isfile(PIPELINE):
        print(f"{RED}Missing {PIPELINE}{RESET}")
        return 2

    hdri = a.hdri
    if not hdri:
        for p in sorted(glob.glob(os.path.join(ROOT, "assets", "*.hdr")) +
                        glob.glob(os.path.join(ROOT, "assets", "*.exr"))):
            hdri = p
            break

    cfg = {"mode": a.mode, "hdri": hdri, "dry_run": a.dry_run, "open": a.open}
    folders = [JOBS] + ([] if a.no_downloads else [a.downloads])

    print(f"\n{GREEN}Daybreak Mills — job watcher{RESET} {DIM}v{repo_version()}{RESET}")
    print(f"  blender  : {blender}  {DIM}(v{'.'.join(map(str, blender_version(blender)))}){RESET}")
    print(f"  watching : {', '.join(folders)}")
    print(f"  hdri     : {hdri or '(built-in fallback)'}")
    print(f"  mode     : {a.mode}"
          f"{'   [dry run]' if a.dry_run else ''}"
          f"{'   [opens GUI after each build]' if a.open else ''}")
    os.makedirs(JOBS, exist_ok=True)

    led = load_ledger()
    history = load_history()
    write_status(history)
    print(f"  status   : {os.path.relpath(STATUS, ROOT)}  (open it in a browser)")
    try:
        run_loop(blender, cfg, folders, led, history, once=a.once, interval=a.interval,
                 lineup=(a.mode == "lineup"))
    except KeyboardInterrupt:
        print(f"\n{DIM}stopped{RESET}")
    return 0


def run_loop(blender, cfg, folders, led, history, once=False, interval=2.0,
             lineup=False, stop=None):
    """The poll loop. `stop` is an optional threading.Event so a host process
    (the bridge) can end it cleanly."""
    pending = {}          # path -> last seen (json_size, tex_size), for stability
    passes = 0
    pick = blender
    if True:
        while not (stop and stop.is_set()):
            blender = pick() if callable(pick) else pick   # the bridge can re-choose at runtime
            built_this_pass = 0
            for cand in candidates(folders):
                key = cand["json"]

                if cand.get("zip"):
                    if led.get(os.path.basename(key)) == fingerprint(key):
                        continue
                    if not zip_complete(key):
                        continue
                    now = sizes_of(key)
                    if pending.get(key) != now:
                        pending[key] = now
                        continue
                    pending.pop(key, None)
                    if process_range(cand, blender, cfg, led, history):
                        built_this_pass += 1
                    continue

                fp = fingerprint(cand["json"], cand["tex"])
                if led.get(os.path.basename(key)) == fp:
                    continue                                  # already built

                if not cand["tex"] or not os.path.isfile(cand["tex"]):
                    continue                                  # texture not here yet
                if not png_complete(cand["tex"]):
                    continue                                  # still downloading

                now = sizes_of(cand["json"], cand["tex"])
                if -1 in now:
                    continue
                # a browser writes a 4K PNG over several seconds — only act once
                # both files have held the same size across two polls
                if pending.get(key) != now:
                    pending[key] = now
                    continue

                pending.pop(key, None)
                if process(cand, blender, cfg, led, history):
                    built_this_pass += 1

            # lineup mode: one scene holding everything, rebuilt whenever the
            # set of jobs actually changed
            if lineup and built_this_pass:
                build_lineup(blender, cfg)      # single jobs only; a range is its own scene

            passes += 1
            # The stability check needs two observations of the same file size,
            # so --once must poll twice or it would never build anything.
            if once and passes >= 2:
                break
            time.sleep(0.4 if once else interval)


if __name__ == "__main__":
    sys.exit(main())
