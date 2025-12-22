# GUI Tracker - Startup Guide

## Current Status

✅ **GUI is running and displaying correctly**
- Window shows with node list, map, and info panels
- Display updates every second
- Map widget loaded successfully

## Issues Identified

### 1. GPS Port Conflict
**Problem:** `gps_client_udp.py` already running and bound to port 2947
**Solution:** Either:
- Kill gps_client_udp.py before starting GUI (GUI has built-in GPS receiver)
- OR use the terminal version which doesn't have a built-in GPS receiver

### 2. Meshtastic Port Not Found
**Problem:** `/dev/ttyACM0` doesn't exist
**Solution:** Find correct port first

## Proper Startup Sequence

### Option A: GUI Only (Recommended)
```bash
# 1. Kill any existing processes
pkill -f gps_client
pkill -f mesh_tracker

# 2. Find Meshtastic device port
ls /dev/tty* | grep -E "(USB|ACM)"

# 3. Start GUI with correct port (or let it auto-detect)
cd /home/iain/MeshLocator/MeshtasticDeviceLocator
source venv/bin/activate
python3 mesh_tracker_gui.py --meshtastic-port /dev/ttyUSB0  # Use actual port
```

### Option B: Terminal Version (Original)
```bash
# 1. Start GPS receiver
python3 gps_client_udp.py &

# 2. Start terminal tracker
python3 mesh_tracker.py --auto-heatmap
```

## Finding Your Meshtastic Device

```bash
# List all serial devices
ls -la /dev/tty* | grep -E "(USB|ACM)"

# Common ports:
# /dev/ttyUSB0  - USB-to-serial adapters
# /dev/ttyACM0  - Arduino/ESP32 devices
# /dev/serial0  - Raspberry Pi serial
```

## What's Working

Based on debug output:
- ✅ GUI window created successfully
- ✅ Map widget loaded
- ✅ Display update loop running (every 1 second)
- ✅ Node list panel ready
- ✅ Info panel ready
- ✅ Status bar updating
- ❌ GPS receiver failed (port already in use)
- ❌ Meshtastic receiver failed (device not found)

## Next Steps

1. **Close the current GUI** (it's running but not connected)
2. **Find the correct Meshtastic port**
3. **Restart with proper port**

## Full Debug Startup

To see all debug messages:
```bash
cd /home/iain/MeshLocator/MeshtasticDeviceLocator
source venv/bin/activate
python3 mesh_tracker_gui.py --meshtastic-port /dev/ttyUSB0 2>&1 | tee gui_debug.log
```

## GUI Features Working

Even without GPS/Meshtastic connected:
- Window displays correctly
- Panels are laid out properly
- Map is interactive (can pan/zoom)
- Status bar updates
- Would show nodes if Meshtastic was connected
- Would show GPS marker if GPS was working

The GUI infrastructure is **fully functional** - just needs proper device connections!
