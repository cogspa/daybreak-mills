#!/bin/bash
# Double-click on macOS, once. Installs the bridge as a login service (it is
# always running from now on, restarted if it dies) and registers the
# daybreak:// link so the studio's Deploy button can start it if it isn't.
# Nothing needs sudo. `python3 tools/install.py --uninstall` undoes it.
cd "$(dirname "$0")" || exit 1
python3 tools/install.py "$@"
echo
read -n 1 -s -r -p "Press any key to close."
