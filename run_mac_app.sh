#!/bin/bash
# ==============================================================
# AI Studio Pro - macOS One-Click Launcher
# ==============================================================
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "✦ Launching AI Studio Pro on macOS..."

# Check Python environment
if [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON_EXEC="python3"
else
    echo "Error: Python 3 not found. Please install Python or setup virtual environment."
    exit 1
fi

# Run Mac Launcher
exec "$PYTHON_EXEC" auto_studio/mac_launcher.py "$@"
