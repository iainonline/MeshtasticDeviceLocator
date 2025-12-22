# Meshtastic Node Tracker - GUI Version

Windows-style graphical interface with embedded map for tracking Meshtastic nodes.

## Features

- **Windows-style GUI** with familiar layout
- **Interactive Map** showing:
  - 📍 Blue marker: Your location (tracking device)
  - 🎯 Red marker: Target node's estimated location
- **Node List** showing all detected mesh nodes
- **Real-time Updates** of position, signal strength, and navigation data
- **Position Estimation** using GPS-based trilateration with Kalman filtering

## Installation

### Required Libraries

```bash
cd /home/iain/MeshLocator/MeshtasticDeviceLocator
source venv/bin/activate
pip install tkintermapview
```

All other dependencies should already be installed from the terminal version.

## Running the GUI

### Using the launch script:
```bash
./run_gui.sh
```

### Direct Python:
```bash
python3 mesh_tracker_gui.py
```

### With options:
```bash
python3 mesh_tracker_gui.py --gps-port 2947 --meshtastic-port /dev/ttyUSB0
```

## GUI Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Meshtastic Node Tracker                                    │
├──────────────┬──────────────────────────────────────────────┤
│ Mesh Nodes   │  Tracking Information                        │
│              │  ┌────────────────────────────────────────┐  │
│ Node1 -60dBm │  │ Node: Test Node                        │  │
│ Node2 -75dBm │  │ Signal: -60dBm, SNR: 8.5dB            │  │
│ Node3 -82dBm │  │ Distance: 150ft, Bearing: 45° (NE)    │  │
│              │  └────────────────────────────────────────┘  │
│              │                                              │
│              │  Map View                                    │
│              │  ┌────────────────────────────────────────┐  │
│              │  │                                        │  │
│              │  │     📍 You                            │  │
│              │  │                                        │  │
│              │  │            🎯 Target                  │  │
│              │  │         (estimated position)          │  │
│              │  │                                        │  │
│              │  └────────────────────────────────────────┘  │
│              │                                              │
│              │  GPS: Fix | Nodes: 3 | Selected: Node1      │
└──────────────┴──────────────────────────────────────────────┘
```

## Usage

1. **Start the GPS receiver** (gps_client_udp.py) in a separate terminal
2. **Launch the GUI** with `./run_gui.sh`
3. **Select a node** from the list on the left
4. **Watch the map** as the system:
   - Shows your position in blue (📍)
   - Estimates and displays target node in red (🎯)
   - Updates in real-time as you move around

## Map Controls

- **Left click + drag**: Pan the map
- **Mouse wheel**: Zoom in/out
- **Right click**: Context menu (copy coordinates, etc.)

## Markers

### 📍 Blue Marker (You)
- Your current GPS position
- Updates in real-time as you move
- Requires GPS fix

### 🎯 Red Marker (Target)
- Estimated position of selected node
- Calculated using trilateration from RSSI samples
- Refined with Kalman filtering for accuracy
- Only appears when:
  - A node is selected
  - At least 10 samples collected
  - Position has been estimated

## Signal Quality

The info panel shows:
- **RSSI**: Signal strength in dBm (higher = better)
- **SNR**: Signal-to-noise ratio in dB
- **Distance**: Calculated distance to target
- **Bearing**: Direction to target in degrees and compass
- **Samples**: Number of data points collected

## Troubleshooting

### Map not loading
- Check internet connection (map tiles download from OpenStreetMap)
- Wait a few seconds for tiles to load

### GPS marker not appearing
- Ensure GPS receiver (gps_client_udp.py) is running
- Check GPS has fix (at least 4 satellites)
- Verify GPS data on UDP port 2947

### Target marker not appearing
- Select a node from the list
- Wait for at least 10 samples to be collected
- Move around the target to collect samples from different positions

### Window too small
- Resize window by dragging edges
- Default size is 1200x800
- Minimum recommended: 1024x768

## Command Line Options

```bash
python3 mesh_tracker_gui.py [OPTIONS]

Options:
  --gps-port PORT          UDP port for GPS data (default: 2947)
  --meshtastic-port PORT   Serial port for Meshtastic device
  --path-loss FLOAT        Path loss exponent (default: 2.5)
  --tx-power FLOAT         Transmit power in dBm (default: 14.0)
  --freq FLOAT             Frequency in MHz (default: 915.0)
```

## Differences from Terminal Version

**GUI Version:**
- ✅ Visual map with markers
- ✅ Mouse-driven interface
- ✅ Better for stationary operation
- ✅ Easier to see spatial relationships
- ❌ No keyboard shortcuts
- ❌ Requires X server / desktop environment

**Terminal Version:**
- ✅ Works over SSH without X forwarding
- ✅ Keyboard shortcuts (1-9, H, B, Q)
- ✅ Heatmap visualization
- ✅ Lower resource usage
- ❌ No visual map
- ❌ Text-only interface

## Tips for Best Results

1. **Collect samples from multiple angles**
   - Walk around the general area of the target
   - More diverse positions = better accuracy

2. **Wait for GPS fix before moving**
   - Ensure good satellite lock (6+ satellites)
   - Let GPS stabilize for 30 seconds

3. **Monitor signal strength**
   - Stay within range (-120dBm to -60dBm)
   - Closer = more accurate position estimates

4. **Use both versions together**
   - GUI for general overview and visualization
   - Terminal for detailed metrics and heatmaps

## System Requirements

- Raspberry Pi or Linux system with desktop environment
- Python 3.7+
- Tkinter (usually included with Python)
- Internet connection (for map tiles)
- GPS receiver with UDP output
- Meshtastic device

## License

Same as the main project.
