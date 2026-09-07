#!/bin/bash
# SDT Trade AI — Linux launcher.
# Double-click this in your file manager (mark it executable first, see
# README), or run `./run_linux.sh` from a terminal.
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "Setting up (first run only)..."
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo "Starting SDT Trade AI — opening your browser..."
python3 app.py
