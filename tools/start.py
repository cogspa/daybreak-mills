#!/usr/bin/env python3
"""
start.py — one command that brings the whole system up.

    python3 tools/start.py           # or double-click run-all.command

    1. starts the bridge in the background (tools/bridge.py: deploy button +
       folder watcher), logging to jobs/bridge.log
    2. launches your chosen Blender's GUI with blender/startup_hook.py, which
       starts the MCP add-on's server if there is one and opens the last lineup
    3. opens the studio (app/daybreak-studio.html) in your default browser

    python3 tools/start.py --stop    # stop the bridge started this way

    --no-blender  --no-browser  --no-last  --blender PATH  --port 8765

Blender is a normal GUI process here — close it like any app. The bridge is
the thing that keeps running; --stop ends it (it remembers its pid in
jobs/.bridge.pid).
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import watch_jobs as W                                  # noqa: E402

ROOT = W.ROOT
PID = os.path.join(W.JOBS, ".bridge.pid")
LOG = os.path.join(W.JOBS, "bridge.log")
HOOK = os.path.join(ROOT, "blender", "startup_hook.py")
STUDIO = os.path.join(ROOT, "app", "daybreak-studio.html")


def bridge_up(port):
    """True if OUR bridge answers on `port` or one of the next nine."""
    import json
    for p in range(port, port + 10):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{p}/status", timeout=0.8) as r:
                if r.status == 200 and json.loads(r.read()).get("bridge") == "daybreak":
                    return p
        except Exception:
            continue
    return None


def stop():
    if not os.path.isfile(PID):
        print("no bridge pid file — nothing to stop")
        return 0
    pid = int(open(PID).read().strip() or 0)
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"stopped bridge (pid {pid})")
    except ProcessLookupError:
        print(f"bridge (pid {pid}) was not running")
    os.remove(PID)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--no-blender", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-last", action="store_true", help="open Blender empty instead of on the last lineup")
    ap.add_argument("--blender", default="")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    if a.stop:
        return stop()

    os.makedirs(W.JOBS, exist_ok=True)
    print(f"\n{W.GREEN}Daybreak Mills — start{W.RESET} {W.DIM}v{W.repo_version()}{W.RESET}")

    # 1. bridge
    up = bridge_up(a.port)
    if up:
        print(f"  bridge   : already running on :{up}")
    else:
        cmd = [sys.executable, os.path.join(ROOT, "tools", "bridge.py"), "--port", str(a.port)]
        if a.blender:
            cmd += ["--blender", a.blender]
        log = open(LOG, "a")
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
        up = None                                      # bridge.py writes its own pid file
        for _ in range(30):
            up = bridge_up(a.port)
            if up:
                break
            time.sleep(0.2)
        print(f"  bridge   : {'up on :' + str(up) if up else 'starting…'}  "
              f"{W.DIM}pid {p.pid}, log jobs/bridge.log{W.RESET}")

    # 2. blender GUI
    blender = W.find_blender(a.blender)
    if a.no_blender:
        print("  blender  : skipped")
    elif not blender:
        print(f"  blender  : {W.RED}not found{W.RESET} — pass --blender PATH")
    else:
        env = dict(os.environ, DAYBREAK_ROOT=ROOT, DAYBREAK_OPEN_LAST="0" if a.no_last else "1")
        subprocess.Popen([blender, "--python", HOOK], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print(f"  blender  : launched {W.DIM}{blender} "
              f"(v{'.'.join(map(str, W.blender_version(blender)))}){W.RESET}")

    # 3. studio
    if a.no_browser:
        print("  studio   : skipped")
    else:
        webbrowser.open("file://" + STUDIO)
        print(f"  studio   : opened {W.DIM}app/daybreak-studio.html{W.RESET}")

    print(f"\n  Export tab → Deploy to Blender should be green. `python3 tools/start.py --stop` ends the bridge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
