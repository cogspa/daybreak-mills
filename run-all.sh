#!/bin/bash
# Double-click on macOS: starts the bridge, opens your chosen Blender, opens the studio.
cd "$(dirname "$0")" || exit 1
python3 tools/start.py "$@"
echo; read -n 1 -s -r -p "Press any key to close this window (the bridge keeps running)."
