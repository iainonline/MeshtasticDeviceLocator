#!/bin/bash
# Launch Meshtastic Node Tracker GUI

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the GUI tracker
python3 mesh_tracker_gui.py "$@"
