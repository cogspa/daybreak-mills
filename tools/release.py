#!/usr/bin/env python3
"""
release.py — version and package the system.

    python3 tools/release.py                 verify, then zip the current version
    python3 tools/release.py --bump patch    1.2.0 -> 1.2.1, then zip
    python3 tools/release.py --bump minor    1.2.0 -> 1.3.0
    python3 tools/release.py --bump major    1.2.0 -> 2.0.0
    python3 tools/release.py --set 2.1.0     exact version
    python3 tools/release.py --no-zip        just bump and verify

A bump rewrites /VERSION AND the APP_VERSION constant inlined in the studio app
together — they are the same number in two places, and tools/verify_geometry.py
refuses to pass if they disagree. It also opens a dated section at the top of
CHANGELOG.md for you to fill in.

Output: dist/daybreak-mills-v<version>.zip, containing the repo minus scratch,
renders, HDRIs and the watcher's ledger. The folder inside the zip is always
daybreak-mills/ so unzipping a newer release over an IDE checkout is a clean
overwrite.
"""

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(ROOT, "VERSION")
APP = os.path.join(ROOT, "app", "daybreak-studio.html")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
DIST = os.path.join(ROOT, "dist")

EXCLUDE_DIRS = {".git", "dist", "node_modules", "__pycache__", "renders", "_preview", ".vscode", ".idea"}
EXCLUDE_FILES = {".DS_Store", ".processed.json", ".history.json", ".bridge.pid", ".bridge.port", "status.html",
                 "bridge.log", "bridge-pairing.json", "Thumbs.db", "daybreak.config.json"}
EXCLUDE_EXT = {".hdr", ".exr", ".blend1", ".blend2", ".pyc"}


def read_version():
    return open(VERSION_FILE).read().strip()


def bump(v, part):
    major, minor, patch = (int(x) for x in v.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write_version(new):
    old = read_version()
    with open(VERSION_FILE, "w") as f:
        f.write(new + "\n")

    src = open(APP).read()
    src, n = re.subn(r'const APP_VERSION = "[^"]+"', f'const APP_VERSION = "{new}"', src)
    if n != 1:
        sys.exit("APP_VERSION constant not found exactly once in the app — refusing to continue")
    open(APP, "w").write(src)

    log = open(CHANGELOG).read()
    stamp = dt.date.today().isoformat()
    section = f"## {new} — {stamp}\n\n- \n\n"
    log = log.replace("## " + old, section + "## " + old, 1) if ("## " + old) in log \
        else log.replace("\n## ", "\n" + section + "## ", 1)
    open(CHANGELOG, "w").write(log)
    print(f"version {old} -> {new}   (VERSION, app constant, CHANGELOG section opened)")


def verify():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "verify_geometry.py")],
                       capture_output=True, text=True)
    tail = "\n".join(r.stdout.strip().splitlines()[-2:])
    print(tail)
    if r.returncode != 0:
        sys.exit("verify_geometry.py failed — not packaging a broken release")


def runtime_job(dirpath, name):
    """Ranges and deploys that landed in jobs/ while testing are not part of a
    release — only the two hand-picked sample jobs are. A test deploy once
    shipped 10 MB of textures this way."""
    # every studio deploy/range carries a _YYYYMMDD-HHMM stamp; the samples don't
    return (os.path.basename(dirpath) == "jobs"
            and (re.search(r"_\d{8}-\d{4}", name) is not None
                 or name.startswith(("daybreak_range_", "daybreak_matrix_", "daybreak_deploy_", "bridge_deploy_"))))


def package(version):
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f"daybreak-mills-v{version}.zip")
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not runtime_job(dirpath, d)]
            for name in files:
                if name in EXCLUDE_FILES or os.path.splitext(name)[1] in EXCLUDE_EXT or runtime_job(dirpath, name):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, ROOT)
                z.write(full, os.path.join("daybreak-mills", rel))
                count += 1
    size = os.path.getsize(out) / 1e6
    print(f"packaged {count} files -> {os.path.relpath(out, ROOT)}  ({size:.1f} MB)")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--bump", choices=["major", "minor", "patch"])
    g.add_argument("--set", metavar="X.Y.Z")
    ap.add_argument("--no-zip", action="store_true")
    a = ap.parse_args()

    if a.bump:
        write_version(bump(read_version(), a.bump))
    elif a.set:
        if not re.fullmatch(r"\d+\.\d+\.\d+", a.set):
            sys.exit("version must be X.Y.Z")
        write_version(a.set)

    verify()
    if not a.no_zip:
        package(read_version())


if __name__ == "__main__":
    main()
