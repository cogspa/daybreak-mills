#!/bin/bash
# Double-click this on macOS to start the job watcher.
# It finds Blender itself, watches jobs/ and ~/Downloads, and builds
# every job the studio exports. Close the window or press Ctrl-C to stop.
cd "$(dirname "$0")" || exit 1
echo "Daybreak Mills — starting job watcher"
echo "Export from app/daybreak-studio.html and the render will appear in jobs/renders/"
echo
exec python3 tools/watch_jobs.py "$@"
