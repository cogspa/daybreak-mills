#!/usr/bin/env python3
"""
bridge.py — the other half of the studio's "Deploy to Blender" button.

A browser cannot write into your project or launch an application. This is a
tiny local server (stdlib only, bound to 127.0.0.1) that does both on the
browser's behalf, and runs the folder watcher in the same process so one thing
started once covers every way a job can arrive.

    python3 tools/bridge.py            # or double-click run-bridge.command

Then, in the studio's Export tab, the "Deploy to Blender" panel goes green,
shows every Blender install on the machine with its version, and the button
sends the range straight here: it is saved into jobs/, built by the chosen
Blender, and the finished scene is opened in the Blender GUI. The render comes
back and is shown in the studio.

If the bridge is NOT running, that panel says so and the buttons fall back to
ordinary downloads — the studio never depends on it.

Endpoints (all on http://127.0.0.1:8765):
    GET  /status            version, Blender installs, which one is chosen
    GET  /history           recent builds
    GET  /renders/<file>    a finished render, for the studio to display
    POST /select            {"path": "..."} choose the Blender to use
    POST /deploy?open=1     body: a range zip from the studio -> builds it

    --port 8765   --blender PATH   --hdri PATH   --no-watch   --no-downloads
"""

import argparse
import io
import secrets
import socket
import tempfile
import zipfile
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bridge_security import MAX_UPLOAD, pairing_key, validate_range
import watch_jobs as W                                   # noqa: E402

STATE = {"blender": None, "cfg": None, "led": None, "history": None,
         "token": None, "lock": threading.Lock(), "started": time.time(), "folders": []}


# One Blender at a time, whichever path a build arrives by. The watcher thread
# and a deploy request both end in run_blender, so the lock lives there.
_run_blender = W.run_blender
def _locked_run_blender(*a, **k):
    with STATE["lock"]:
        return _run_blender(*a, **k)
W.run_blender = _locked_run_blender


class Handler(BaseHTTPRequestHandler):
    server_version = "DaybreakBridge/" + W.repo_version()

    # ---- plumbing ----------------------------------------------------------
    def log_message(self, fmt, *args):            # quieter than the default
        if "/status" in (args[0] if args else ""):
            return
        sys.stdout.write(f"  {W.DIM}{self.address_string()} {fmt % args}{W.RESET}\n")

    def _cors(self):
        if self.headers.get("Origin") == "null":
            self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Daybreak-Name, X-Daybreak-Token")
        self.send_header("Cache-Control", "no-store")

    def _allowed(self, authenticate=True):
        # Host validation also prevents DNS rebinding to this loopback service.
        host = self.headers.get("Host", "")
        expected = f"127.0.0.1:{self.server.server_port}"
        if host != expected or self.headers.get("Origin") not in (None, "null"):
            self._json(403, {"error": "This bridge accepts local Studio requests only"})
            return False
        if authenticate and not self._paired():
            self._json(401, {"error": "Pair this Studio with jobs/bridge-pairing.json"})
            return False
        return True

    def _paired(self):
        token = self.headers.get("X-Daybreak-Token", "")
        return bool(STATE["token"] and secrets.compare_digest(token.encode(), STATE["token"].encode()))

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not self._allowed(False):
            return
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ---- GET ----------------------------------------------------------------
    def do_GET(self):
        if not self._allowed(False):
            return
        u = urlparse(self.path)
        if u.path == "/status":
            return self._json(200, status_payload() if self._paired() else {
                "bridge": "daybreak", "version": W.repo_version(), "pairing_required": True})
        if not self._allowed():
            return
        if u.path == "/history":
            return self._json(200, {"history": STATE["history"][:40]})
        if u.path.startswith("/renders/"):
            name = os.path.basename(u.path)
            p = os.path.join(W.JOBS, "renders", name)
            if not (name.endswith(".png") and os.path.isfile(p)):
                return self._json(404, {"error": "no such render"})
            with open(p, "rb") as f:
                data = f.read()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json(404, {"error": "unknown endpoint", "endpoints": ["/status", "/history", "/renders/<png>", "/select", "/deploy"]})

    # ---- POST ---------------------------------------------------------------
    def do_POST(self):
        u = urlparse(self.path)
        self.close_connection = True
        if not self._allowed():
            return
        if self.headers.get("Transfer-Encoding"):
            return self._json(400, {"error": "Transfer-Encoding is not supported"})
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(400, {"error": "Invalid Content-Length"})
        limit = 16384 if u.path == "/select" else MAX_UPLOAD
        if length < 0 or length > limit:
            return self._json(413, {"error": "Upload exceeds request limit"})
        self.connection.settimeout(30)
        try:
            body = self.rfile.read(length)
        except (socket.timeout, OSError):
            return self._json(408, {"error": "Upload timed out"})
        if len(body) != length:
            return self._json(400, {"error": "Incomplete upload"})

        if u.path == "/select":
            try:
                path = json.loads(body or b"{}").get("path", "")
            except Exception:
                return self._json(400, {"error": "bad json"})
            allowed = {b["path"] for b in W.list_blenders()} | {STATE["blender"]}
            if not isinstance(path, str) or path not in allowed or not os.path.isfile(path):
                return self._json(400, {"error": "Choose a detected Blender installation"})
            W.write_config(blender=path)
            STATE["blender"] = path
            print(f"  blender  : {path}  {W.DIM}(v{'.'.join(map(str, W.blender_version(path)))}) — chosen{W.RESET}")
            return self._json(200, status_payload())

        if u.path == "/deploy":
            if not body or body[:2] != b"PK":
                return self._json(400, {"error": "body must be a zip from the studio"})
            try:
                with zipfile.ZipFile(io.BytesIO(body)) as zf:
                    validate_range(zf)
            except (ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as e:
                return self._json(400, {"error": str(e)})
            name = self.headers.get("X-Daybreak-Name", f"daybreak_deploy_{int(time.time())}")
            name = "".join(c for c in name if c.isalnum() or c in "_-")[:80] or "daybreak_deploy"
            if not name.endswith(".zip"):
                name += ".zip"
            os.makedirs(W.JOBS, exist_ok=True)
            # Unique names avoid collisions between tabs and the folder watcher.
            name = "bridge_deploy_" + secrets.token_hex(12) + ".zip"
            zpath = os.path.join(W.JOBS, name)
            fd, pending = tempfile.mkstemp(prefix=".upload-", dir=W.JOBS)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(body)
                os.replace(pending, zpath)
            finally:
                if os.path.exists(pending):
                    os.unlink(pending)

            q = parse_qs(u.query)
            cfg = dict(STATE["cfg"], open=q.get("open", ["0"])[0] in ("1", "true"))
            cand = {"zip": zpath, "json": zpath, "tex": "", "job": {}, "folder": W.JOBS}
            t = time.time()
            res = W.process_range(cand, STATE["blender"], cfg, STATE["led"], STATE["history"])
            if not isinstance(res, dict):
                return self._json(500, {"error": "build failed — see the bridge terminal", "name": name})
            res["seconds"] = round(time.time() - t, 1)
            res["opened"] = bool(cfg["open"])
            res["blender"] = STATE["blender"]
            return self._json(200, res)

        self._json(404, {"error": "unknown endpoint"})


def status_payload():
    installs = W.list_blenders()
    chosen = STATE["blender"]
    if chosen and all(b["path"] != chosen for b in installs):     # e.g. --blender to a custom path
        installs.insert(0, {"path": chosen, "version": ".".join(map(str, W.blender_version(chosen)))})
    return {
        "bridge": "daybreak", "version": W.repo_version(), "authenticated": True,
        "uptime_s": int(time.time() - STATE["started"]),
        "blender": chosen,
        "blender_version": ".".join(map(str, W.blender_version(chosen))) if chosen else None,
        "blenders": [dict(b, selected=(b["path"] == chosen)) for b in installs],
        "jobs_dir": W.JOBS, "watching": STATE["folders"],
        "hdri": STATE["cfg"]["hdri"] if STATE["cfg"] else "",
        "builds": len(STATE["history"] or []),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--blender", default="")
    ap.add_argument("--hdri", default="")
    ap.add_argument("--no-watch", action="store_true", help="deploy button only; do not poll folders")
    ap.add_argument("--no-downloads", action="store_true")
    ap.add_argument("--downloads", default=os.path.expanduser("~/Downloads"))
    ap.add_argument("--interval", type=float, default=2.0)
    a = ap.parse_args()

    blender = W.find_blender(a.blender)
    if not blender:
        print(f"{W.RED}Could not find Blender.{W.RESET} Pass --blender PATH.")
        return 2
    hdri = a.hdri
    if not hdri:
        import glob
        for p in sorted(glob.glob(os.path.join(W.ROOT, "assets", "*.hdr")) +
                        glob.glob(os.path.join(W.ROOT, "assets", "*.exr"))):
            hdri = p
            break

    STATE["token"] = pairing_key(W.JOBS)
    STATE["blender"] = blender
    STATE["cfg"] = {"mode": "hero", "hdri": hdri, "dry_run": False, "open": False}
    STATE["led"] = W.load_ledger()
    STATE["history"] = W.load_history()
    STATE["folders"] = [W.JOBS] + ([] if a.no_downloads else [a.downloads])
    os.makedirs(W.JOBS, exist_ok=True)
    W.write_status(STATE["history"])

    print(f"\n{W.GREEN}Daybreak Mills — bridge{W.RESET} {W.DIM}v{W.repo_version()}{W.RESET}")
    print(f"  blender  : {blender}  {W.DIM}(v{'.'.join(map(str, W.blender_version(blender)))}){W.RESET}")
    others = [b for b in W.list_blenders() if b['path'] != blender]
    if others:
        print(f"  also     : " + ", ".join(f"{b['version']}" for b in others) + "  — choose in the studio, or POST /select")
    print(f"  hdri     : {hdri or '(built-in fallback)'}")
    print(f"  watching : {', '.join(STATE['folders']) if not a.no_watch else '(off)'}")
    print(f"  status   : {os.path.relpath(W.STATUS, W.ROOT)}")

    stop = threading.Event()
    if not a.no_watch:
        t = threading.Thread(target=W.run_loop, name="watcher", daemon=True,
                             args=(lambda: STATE["blender"], STATE["cfg"], STATE["folders"], STATE["led"], STATE["history"]),
                             kwargs={"interval": a.interval, "stop": stop})
        t.start()

    # 8765 was taken by an unrelated local tool on the reference machine, so
    # never insist on one port: take the first free one in a small range. The
    # studio probes the same range and checks the reply identifies as ours.
    srv, port = None, None
    for candidate in range(a.port, a.port + 10):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if srv is None:
        print(f"{W.RED}No free port in {a.port}-{a.port + 9}{W.RESET}")
        return 2
    with open(os.path.join(W.JOBS, ".bridge.port"), "w") as f:
        f.write(str(port))
    # our own pid, however we were started (terminal, start.py, launchd), so
    # install.py and start.py --stop can always find us
    with open(os.path.join(W.JOBS, ".bridge.pid"), "w") as f:
        f.write(str(os.getpid()))
    if port != a.port:
        print(f"  {W.YELL}port {a.port} was busy — using {port}{W.RESET}")
    print(f"  listening: http://127.0.0.1:{port}   (the studio's Deploy panel talks to this)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        stop.set()
        print(f"\n{W.DIM}stopped{W.RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
