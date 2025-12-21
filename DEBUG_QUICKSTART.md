# Quick Debug Guide

## Running in Debug Mode

```bash
# Normal mode
python mesh_tracker.py

# Debug mode (recommended for troubleshooting)
python mesh_tracker.py --debug
```

## Debug Files Created

When running with `--debug`:

1. **mesh_tracker_debug_TIMESTAMP.log** - Detailed packet inspection
   - Shows every packet received
   - Displays which fields contain RSSI/SNR
   - Tracks signal history updates
   - Logs trend calculations

2. **mesh_tracker_screen_TIMESTAMP.txt** - UI snapshots every 2 seconds
   - Current mode and selected node
   - GPS status
   - Signal history length
   - Trend calculations

3. **mesh_tracker_TIMESTAMP.jsonl** - Data log (always created)
   - GPS readings
   - Mesh packets
   - For ML analysis

## Quick Checks

### Check if nodes are receiving RSSI data:
```bash
grep "FOUND rxRssi" mesh_tracker_debug_*.log
```

### See which nodes have signal tracking:
```bash
grep "Latest signal history" mesh_tracker_debug_*.log
```

### Check auto-selection:
```bash
grep "Auto-selected" mesh_tracker_debug_*.log
```

### View last screen capture:
```bash
tail -50 mesh_tracker_screen_*.txt
```

## Common Issues

### "Collecting data..." message
- **Not a bug!** Node hasn't transmitted recently
- Only nodes that actively transmit will have signal data
- Try selecting a different node from the list

### No hotter/colder trends showing
- Check if node has RSSI: Look for green/red signal strength in node list
- If RSSI shows "N/A", that node isn't transmitting
- Select a node showing actual RSSI values (e.g., "-45 dBm")

### Want to see which nodes are active RIGHT NOW?
- Look at the node list
- Nodes with recent "Last" times (1s, 2s, 3s ago) are actively transmitting
- Nodes with old times (5m, 10m ago) are from nodeDB cache

## Debug Log Examples

### Good packet (has RSSI):
```
[2025-12-21 10:12:57] === RAW PACKET ===
[2025-12-21 10:12:57] Keys: ['from', 'to', 'decoded', 'rxRssi', 'rxSnr', ...]
[2025-12-21 10:12:57]   FOUND rxRssi: -37
[2025-12-21 10:12:57]   FOUND rxSnr: 6.25
[2025-12-21 10:12:57] Set RSSI to -37 for node !43569c10
[2025-12-21 10:12:57] Node !43569c10 signal history length: 1
```

### NodeDB packet (no RSSI - normal):
```
[2025-12-21 10:12:55] === RAW PACKET ===
[2025-12-21 10:12:55] Keys: ['from', 'fromId', 'decoded', 'user']
[2025-12-21 10:12:55] WARNING: No RSSI found in packet from !9e757a8c
[2025-12-21 10:12:55] Node !9e757a8c signal history length: 0
```

## Understanding the Data

### NodeDB vs Live Packets
- **NodeDB**: Cached nodes from past activity (~100-200 nodes)
  - No RSSI/SNR
  - May not be actively transmitting
  - Used to populate node list
  
- **Live Packets**: Actually received transmissions (1-10 per minute)
  - Has RSSI/SNR
  - These are what enable tracking
  - Only available for nodes transmitting NOW

### Signal History Requirements
- **Minimum for trends**: 2 entries
- **Typical for good tracking**: 5-10 entries per minute
- **Maximum stored**: Last 30 minutes (auto-pruned)

## Testing the Fix

The auto-selection now prefers nodes with signal data:

```bash
# Run for 30 seconds in debug mode
timeout 30 python mesh_tracker.py --debug

# Check which node was auto-selected
grep "Auto-selected node with signal" mesh_tracker_debug_*.log

# Verify it has signal data
grep "Latest signal history" mesh_tracker_debug_*.log
```

Should see output like:
```
Auto-selected node with signal data: !43569c10
Latest signal history entry: {'timestamp': ..., 'rssi': -37, ...}
```
