#!/usr/bin/env python3
"""
install.py — make the bridge something you never have to start.

    python3 tools/install.py             # or double-click run-install.command
    python3 tools/install.py --status
    python3 tools/install.py --uninstall

Two things get installed, both per-user, nothing needs sudo:

  1. A login service (macOS launchd LaunchAgent). tools/bridge.py starts when
     you log in and is restarted if it ever dies. The studio's Deploy panel is
     simply always green. Logs go to jobs/bridge.log.

  2. A URL handler app, ~/Applications/Daybreak Bridge.app, registered for the
     daybreak:// scheme. A web page cannot start a program — that is a hard
     browser rule — but it CAN open a URL, and macOS routes a registered scheme
     to an app. So when the studio's Deploy button finds no bridge, it opens
     daybreak://start, this app runs tools/start.py, the bridge comes up, and
     the deploy goes through. The first time, the browser asks "Open Daybreak
     Bridge?" — tick "always allow".

Either one alone is enough; together the second only matters if you stopped
the service yourself. Re-run after moving the repo: both bake in its path.

macOS only. On Linux the same idea is a systemd --user unit and an
xdg-mime handler; on Windows a Task Scheduler entry and a registry key.
"""

import argparse
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import watch_jobs as W                                  # noqa: E402
from start import bridge_up                             # noqa: E402

ROOT = W.ROOT
LABEL = "com.daybreakmills.bridge"
AGENT = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
APP = os.path.expanduser("~/Applications/Daybreak Bridge.app")
PID = os.path.join(W.JOBS, ".bridge.pid")
LOG = os.path.join(W.JOBS, "bridge.log")
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
              "LaunchServices.framework/Support/lsregister")


def python3():
    """A system python for the service — never Blender's bundled one, which is
    what sys.executable is when this runs from inside Blender."""
    if "Blender" not in sys.executable and "blender" not in sys.executable:
        return sys.executable
    for cand in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"):
        if os.path.isfile(cand):
            return cand
    return shutil.which("python3") or "/usr/bin/python3"


def sh(*cmd, ok=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode and not ok:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stderr.strip()}")
    return r


def stop_stray_bridges():
    """Kill any bridge not managed by launchd, so the service gets its port."""
    pids = set()
    if os.path.isfile(PID):
        try:
            pids.add(int(open(PID).read().strip() or 0))
        except ValueError:
            pass
    r = sh("pgrep", "-f", os.path.join(ROOT, "tools", "bridge.py"))
    pids |= {int(p) for p in r.stdout.split() if p.isdigit()}
    r = sh("pgrep", "-f", "tools/bridge.py")           # started from the repo folder as `python3 tools/bridge.py`
    pids |= {int(p) for p in r.stdout.split() if p.isdigit()}
    pids.discard(os.getpid())
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if pids:
        time.sleep(0.6)
    return sorted(pids)


# ---- 1. the login service --------------------------------------------------
def install_agent():
    py = python3()
    plist = {
        "Label": LABEL,
        "ProgramArguments": [py, os.path.join(ROOT, "tools", "bridge.py")],
        "WorkingDirectory": ROOT,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Interactive",              # may launch a GUI app (Blender)
        "StandardOutPath": LOG,
        "StandardErrorPath": LOG,
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "DAYBREAK_ROOT": ROOT,
            "PYTHONUNBUFFERED": "1",
        },
    }
    os.makedirs(os.path.dirname(AGENT), exist_ok=True)
    os.makedirs(W.JOBS, exist_ok=True)
    uid = os.getuid()
    sh("launchctl", "bootout", f"gui/{uid}/{LABEL}")             # replace a previous install
    time.sleep(0.3)
    with open(AGENT, "wb") as f:
        plistlib.dump(plist, f)
    stopped = stop_stray_bridges()
    sh("launchctl", "bootstrap", f"gui/{uid}", AGENT, ok=False)
    port = None
    for _ in range(40):
        port = bridge_up(8765)
        if port:
            break
        time.sleep(0.25)
    return py, stopped, port


def uninstall_agent():
    uid = os.getuid()
    sh("launchctl", "bootout", f"gui/{uid}/{LABEL}")
    if os.path.isfile(AGENT):
        os.remove(AGENT)


def agent_status():
    uid = os.getuid()
    r = sh("launchctl", "print", f"gui/{uid}/{LABEL}")
    if r.returncode:
        return None
    state = "running" if "state = running" in r.stdout else "loaded"
    pid = ""
    for line in r.stdout.splitlines():
        if line.strip().startswith("pid = "):
            pid = line.split("=")[1].strip()
    return f"{state}" + (f", pid {pid}" if pid else "")


# ---- 2. the daybreak:// handler app ------------------------------------------
def install_app():
    py = python3()
    macos = os.path.join(APP, "Contents", "MacOS")
    os.makedirs(macos, exist_ok=True)
    info = {
        "CFBundleName": "Daybreak Bridge",
        "CFBundleDisplayName": "Daybreak Bridge",
        "CFBundleIdentifier": "com.daybreakmills.bridge-launcher",
        "CFBundleVersion": W.repo_version(),
        "CFBundleShortVersionString": W.repo_version(),
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "launch",
        "LSUIElement": True,                       # no Dock icon, no menu bar
        "LSMinimumSystemVersion": "12.0",
        "CFBundleURLTypes": [{
            "CFBundleURLName": "Daybreak Mills bridge",
            "CFBundleURLSchemes": ["daybreak"],
            "LSHandlerRank": "Owner",
        }],
    }
    with open(os.path.join(APP, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump(info, f)
    # The URL itself arrives by Apple Event, which a shell script cannot read;
    # it does not matter — the only thing daybreak:// ever asks is "be up".
    # No Blender here: the deploy that follows opens Blender on its own result,
    # and a second window on the last lineup would just be in the way.
    launcher = os.path.join(macos, "launch")
    with open(launcher, "w") as f:
        f.write("#!/bin/bash\n"
                f"cd {sq(ROOT)} || exit 1\n"
                f"exec {sq(py)} tools/start.py --no-browser --no-blender >> {sq(LOG)} 2>&1\n")
    os.chmod(launcher, 0o755)
    if os.path.isfile(LSREGISTER):
        sh(LSREGISTER, "-f", APP)
    else:
        sh("open", "-g", "-a", APP)                # falls back to touching it once
    return APP


def sq(s):
    return "'" + s.replace("'", "'\\''") + "'"


def uninstall_app():
    if os.path.isdir(APP):
        if os.path.isfile(LSREGISTER):
            sh(LSREGISTER, "-u", APP)
        shutil.rmtree(APP)


# ---- main --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--no-agent", action="store_true", help="skip the login service")
    ap.add_argument("--no-app", action="store_true", help="skip the daybreak:// handler")
    a = ap.parse_args()

    if sys.platform != "darwin":
        print(f"{W.RED}install.py is macOS-only for now.{W.RESET} Run tools/bridge.py yourself, or see the docstring for the Linux/Windows equivalents.")
        return 2

    print(f"\n{W.GREEN}Daybreak Mills — install{W.RESET} {W.DIM}v{W.repo_version()}{W.RESET}")
    if a.status:
        st = agent_status()
        print(f"  service  : {st or 'not installed'}   {W.DIM}{AGENT}{W.RESET}")
        print(f"  handler  : {'installed' if os.path.isdir(APP) else 'not installed'}   {W.DIM}{APP}{W.RESET}")
        up = bridge_up(8765)
        print(f"  bridge   : {'up on :' + str(up) if up else 'not answering'}")
        return 0

    if a.uninstall:
        uninstall_agent()
        uninstall_app()
        print("  service  : removed")
        print("  handler  : removed")
        print(f"  {W.DIM}the bridge is no longer running; python3 tools/bridge.py starts it by hand{W.RESET}")
        return 0

    if not a.no_agent:
        py, stopped, port = install_agent()
        if stopped:
            print(f"  stopped  : bridge pid{'s' if len(stopped) > 1 else ''} {', '.join(map(str, stopped))} (not managed by the service)")
        print(f"  service  : {LABEL} — {agent_status() or 'failed to load'}   {W.DIM}{py}{W.RESET}")
        print(f"  bridge   : {'up on :' + str(port) if port else W.RED + 'did not come up — see jobs/bridge.log' + W.RESET}")
    if not a.no_app:
        install_app()
        print(f"  handler  : daybreak:// → {W.DIM}{APP}{W.RESET}")
    print(f"\n  The studio's Deploy panel is green from now on, including after a reboot.")
    print(f"  {W.DIM}python3 tools/install.py --status · --uninstall{W.RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
