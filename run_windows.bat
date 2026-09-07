@echo off
REM SDT Trade AI — Windows launcher. Double-click this file.
cd /d "%~dp0"

if not exist venv (
    echo Setting up (first run only)...
    python -m venv venv
)

call venv\Scripts\activate.bat
pip install -q -r requirements.txt

echo Starting SDT Trade AI — opening your browser...
python app.py

pause
