#!/bin/bash
# Convenience script to run mesh_tracker.py in virtual environment

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Running installation..."
    ./install.sh
    exit $?
fi

# Activate venv and run
source venv/bin/activate
python mesh_tracker.py "$@"
