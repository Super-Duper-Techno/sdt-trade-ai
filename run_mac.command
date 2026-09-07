#!/bin/bash
# SDT Trade AI — macOS launcher.
# Double-click this file in Finder (mark it executable first, see README).
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
