#!/usr/bin/env python3
"""
update.py — bring this checkout up to the newest release zip, safely.

    python3 tools/update.py            # newest zip in ../releases/ over this checkout
    python3 tools/update.py --check    # just say what is available vs installed
    python3 tools/update.py --zip PATH # a specific zip
    python3 tools/update.py --force    # overwrite local edits (still backed up)

Releases land in <parent>/releases/daybreak-mills-v<version>.zip. This checkout
lives at <parent>/daybreak-mills/. The zip's inner folder is daybreak-mills/, so
extracting it at <parent> overwrites tracked files in place.

What it will never touch, because the zip never contains them:
    .vscode/  daybreak.config.json  assets/*.hdr  jobs/<your jobs>  _backup/

What it protects: a file you edited locally. Before overwriting, each file in the
zip is compared to what is on disk. If the disk copy differs from the incoming
one AND from the previous release's copy, that is a local edit. It is saved to
_backup/<installed-version>/<path> and the update stops unless --force.
In a git checkout, a dirty tree is the same signal: the update stops unless
--force, and asks you to commit or stash first.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
RELEASES = os.path.join(PARENT, "releases")
INNER = "daybreak-mills/"                     # folder inside every release zip

GREEN, RED, YELL, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELL = DIM = RESET = ""


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0, 0, 0)


def installed_version():
    try:
        return open(os.path.join(ROOT, "VERSION")).read().strip()
    except OSError:
        return "0.0.0"


def zip_version(path):
    try:
        with zipfile.ZipFile(path) as z:
            return z.read(INNER + "VERSION").decode().strip()
    except Exception:
        m = re.search(r"-v(\d+\.\d+\.\d+)\.zip$", os.path.basename(path))
        return m.group(1) if m else "0.0.0"


def available():
    zips = glob.glob(os.path.join(RELEASES, "daybreak-mills-v*.zip"))
    return sorted(zips, key=lambda p: vtuple(zip_version(p)))


def git_dirty():
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        return None
    try:
        r = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=20)
        return [l for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return None


def local_edits(new_zip, prev_zip):
    """Files on disk that differ from BOTH the incoming and the previous release —
    i.e. things you changed by hand rather than things a release changed."""
    edits = []
    with zipfile.ZipFile(new_zip) as znew:
        zprev = zipfile.ZipFile(prev_zip) if prev_zip else None
        try:
            for info in znew.infolist():
                if info.is_dir() or not info.filename.startswith(INNER):
                    continue
                rel = info.filename[len(INNER):]
                disk = os.path.join(ROOT, rel)
                if not os.path.isfile(disk):
                    continue
                on_disk = open(disk, "rb").read()
                incoming = znew.read(info.filename)
                if on_disk == incoming:
                    continue
                previous = None
                if zprev:
                    try:
                        previous = zprev.read(info.filename)
                    except KeyError:
                        pass
                if previous is not None and on_disk == previous:
                    continue                 # unchanged since last release: safe
                edits.append(rel)
        finally:
            if zprev:
                zprev.close()
    return edits


def backup(paths, tag):
    dest = os.path.join(ROOT, "_backup", tag)
    for rel in paths:
        src = os.path.join(ROOT, rel)
        dst = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    return dest


def apply(new_zip):
    with zipfile.ZipFile(new_zip) as z:
        members = [m for m in z.namelist() if m.startswith(INNER)]
        z.extractall(PARENT, members)
    for f in glob.glob(os.path.join(ROOT, "*.command")) + glob.glob(os.path.join(ROOT, "*.sh")):
        os.chmod(f, 0o755)
    return len(members)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", help="a specific release zip")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    cur = installed_version()
    zips = available()
    target = a.zip or (zips[-1] if zips else None)
    if not target or not os.path.isfile(target):
        print(f"{RED}No release zip found{RESET} in {RELEASES}")
        return 2
    new = zip_version(target)
    prev = None
    for z in reversed(zips):
        if vtuple(zip_version(z)) == vtuple(cur) and z != target:
            prev = z
            break

    print(f"\nDaybreak Mills — update")
    print(f"  installed : {cur}")
    print(f"  available : {new}   {DIM}{os.path.relpath(target, PARENT)}{RESET}")
    if vtuple(new) <= vtuple(cur) and not a.zip:
        print(f"  {GREEN}already up to date{RESET}")
        return 0
    if a.check:
        return 0

    dirty = git_dirty()
    if dirty:
        print(f"\n{YELL}git checkout has uncommitted changes:{RESET}")
        for l in dirty[:12]:
            print(f"    {l}")
        if not a.force:
            print(f"\nCommit or stash first, or re-run with --force.")
            return 1

    edits = local_edits(target, prev)
    if edits:
        dest = backup(edits, f"v{cur}")
        print(f"\n{YELL}{len(edits)} file(s) edited locally since {cur}{RESET} — backed up to "
              f"{os.path.relpath(dest, ROOT)}/")
        for rel in edits[:12]:
            print(f"    {rel}")
        if not a.force:
            print(f"\nNot overwriting. Merge your edits back afterwards, or re-run with --force.")
            return 1

    n = apply(target)
    print(f"\n  {GREEN}updated{RESET} {cur} -> {new}   ({n} files)")
    if edits:
        print(f"  your edited copies are in _backup/v{cur}/ — merge what you need back")
    return 0


if __name__ == "__main__":
    sys.exit(main())
