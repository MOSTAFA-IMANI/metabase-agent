#!/bin/bash
# Double-click to start the Soupop launcher on a Mac.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "" >/dev/null 2>&1; then
  echo "Python 3 is missing. A window will offer to install Apple's command line tools."
  echo "Click Install, wait for it to finish, then double-click start.command again."
  xcode-select --install 2>/dev/null
  read -r -p "Press Enter to close."
  exit 1
fi
git pull --ff-only --quiet 2>/dev/null || true
# Keep a log so problems can be checked later, and keep the window open if it stops.
python3 -u launcher/server.py 2>&1 | tee launcher.log
echo
echo "The launcher stopped. Details are in $(pwd)/launcher.log"
read -r -p "Press Enter to close."
