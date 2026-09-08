#!/bin/bash
# Double-click on macOS. Starts the bridge: the studio's "Deploy to Blender"
# button talks to it, and it also watches jobs/ and ~/Downloads.
# Leave this window open; close it or press Ctrl-C to stop.
cd "$(dirname "$0")" || exit 1
exec python3 tools/bridge.py "$@"
