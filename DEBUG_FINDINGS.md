# Debug Analysis - Signal Tracking Investigation

## Date: 2025-12-21

## Question: Is tracking logic really working?

### Answer: **YES, it's working correctly!**

## Findings

### 1. Signal Tracking IS Working
- RSSI and SNR are correctly extracted from live packets
- Signal history is properly maintained (timestamped with GPS coordinates)
- Hotter/colder trending calculations work as designed
- Movement detection (Pi stationary vs. target moving) works correctly

### 2. The Real Issue: NodeDB vs. Live Packets

**NodeDB Packets (No Signal Data)**:
- When the app starts, it loads ~180+ nodes from the Meshtastic nodeDB
- These are cached node records from past activity
- **They do NOT contain rxRssi or rxSnr fields**
- Example packet from nodeDB:
  ```python
  {
    'from': '!9e757a8c', 
    'fromId': '!9e757a8c',
    'decoded': {'position': {...}},
    'user': {'shortName': '7a8c', 'longName': 'Meshtastic 7a8c'}
  }
  # No rxRssi, no rxSnr!
  ```

**Live Received Packets (With Signal Data)**:
- When a node actively transmits and your radio receives it
- These packets include rxRssi and rxSnr fields
- Example live packet:
  ```python
  {
    'from': 2658555560,
    'to': 4294967295,
    'decoded': {...},
    'rxRssi': -37,    # ✓ Present!
    'rxSnr': 6.25,    # ✓ Present!
    ...
  }
  ```

### 3. Test Results (30-second capture)

**Total packets processed**: 190
- NodeDB packets (no RSSI): 187
- Live packets (with RSSI): 3

**Nodes with signal tracking data**: 1
- Node `!43569c10`: Received 3 packets with RSSI values (-37, -40, -39 dBm)
- Signal history properly maintained
- GPS coordinates captured with each signal measurement

### 4. Why It Appeared Broken

During the test:
- Auto-selected node: `!9e757a8c` (from nodeDB, not actively transmitting)
- This node had: RSSI=None, SNR=None, Signal History=[]
- The tracking screen showed "Collecting data..." (correct behavior)

Meanwhile:
- Node `!43569c10` WAS actively transmitting
- Had full signal tracking data
- Would have shown proper hotter/colder trending if selected

### 5. Improvements Made

#### Debug Mode Added
```bash
python mesh_tracker.py --debug
```

Enables:
- **Debug log**: `mesh_tracker_debug_TIMESTAMP.log`
  - Raw packet inspection
  - RSSI/SNR field detection
  - Signal history updates
  - Trend calculations

- **Screen capture**: `mesh_tracker_screen_TIMESTAMP.txt`
  - Periodic snapshots of UI state
  - Node details and signal history
  - Trend calculations
  - Captured every 2 seconds

#### Auto-Selection Improved
- **Old behavior**: Auto-select last saved node (might be inactive)
- **New behavior**: Prefer nodes with recent signal data
  - First choice: Node with most recent signal history
  - Fallback: Previously saved node
  - This ensures tracking actually works on startup

## Verification

### Signal History Working
From debug log for node `!43569c10`:
```
[10:12:57] Latest signal history entry: 
  {'timestamp': 1766340777.12, 'rssi': -37, 'snr': 6.25, 
   'latitude': 35.968397, 'longitude': -115.081398}

[10:13:14] Latest signal history entry:
  {'timestamp': 1766340794.09, 'rssi': -40, 'snr': 6.25,
   'latitude': 35.968397, 'longitude': -115.081398}

[10:13:21] Latest signal history entry:
  {'timestamp': 1766340801.00, 'rssi': -39, 'snr': 5.75,
   'latitude': 35.968397, 'longitude': -115.081398}
```

### All Tests Passing
```
Ran 35 tests in 0.148s
OK
✓ ALL TESTS PASSED!
```

## Usage Tips

### To Track Actively Transmitting Nodes:
1. Start the app and wait 10 seconds
2. App will auto-select a node with recent signal data
3. Or manually press 1-9 to select a node you see receiving packets
4. Hotter/colder tracking will work immediately for active nodes

### To Debug Issues:
```bash
# Run with debug mode
python mesh_tracker.py --debug

# Check which nodes have RSSI data
grep "FOUND rxRssi" mesh_tracker_debug_*.log

# See signal history updates
grep "Latest signal history" mesh_tracker_debug_*.log

# View screen captures
cat mesh_tracker_screen_*.txt
```

### Understanding "Collecting data..."
- This message means the selected node hasn't transmitted recently
- It's working correctly - just waiting for that node to transmit
- Try selecting a different node that shows RSSI values

## Conclusion

The tracking logic is **100% functional**. The confusion came from:
1. Most nodes in the list are from nodeDB (inactive)
2. Only actively transmitting nodes have signal data
3. Auto-selection was picking saved nodes (possibly inactive)

**Solution**: Now auto-selects nodes with recent activity, ensuring tracking works immediately.
