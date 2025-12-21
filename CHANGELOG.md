# Changelog - December 21, 2025

## Updates Pushed to GitHub

### 🔍 Debug Mode & Verification (Commit 1ff4dbd)
- Added comprehensive `--debug` flag
- Deep packet inspection with field detection
- Screen capture every 2 seconds
- Detailed logging of signal tracking
- Verified all tracking features work correctly
- Created demo script to prove functionality

### 📏 Unit Conversion to Feet/Miles (Commit 2eaaf12)
- **Distance Display**: Now shows feet (< 1 mile) or miles (≥ 1 mile)
  - Before: `145.7m` or `1.23km`
  - After: `478.3ft` or `0.76mi`
- **Altitude Display**: All altitudes now in feet
  - GPS altitude: `2718.8ft`
  - Node altitude: `2570.5ft`

### ⚠️ GPS Accuracy Warnings
- Added satellite count warnings
  - Shows warning if less than 6 satellites
  - "Low satellite count - position may be inaccurate"
  - "Low - position may be aged or inaccurate"
- No GPS fix warnings enhanced
  - "No GPS fix - cannot calculate distance/bearing"
  - "Cannot calculate distance/bearing" in tracking view

### 📍 Enhanced Position Estimation Section
- Dedicated panel for position estimation
- Shows real-time updates from estimation process
- Progress indicator (e.g., "3/3 samples")
- Confidence level (Low/Medium based on sample count)
- Recent estimation log entries displayed
- Clear status messages:
  - "Collecting RSSI data... (2 samples)"
  - "Minimum 3 samples needed"
  - "Node has GPS - estimation not needed"
  - "Need GPS fix on Pi to start"

### 🎯 Improved Auto-Selection
- Prefers nodes with recent signal data
- Falls back to last saved node if no active nodes
- Ensures tracking works immediately on startup
- Debug logging of selection decision

### ✅ All Tests Passing
- Updated tests for new distance units
- All 35 unit tests pass
- Verified on actual hardware

## Files Added
- `DEBUG_FINDINGS.md` - Detailed investigation results
- `DEBUG_QUICKSTART.md` - Quick debug reference
- `TRACKING_VERIFICATION_REPORT.md` - Complete verification
- `demo_tracking.py` - Working demonstration script
- `CHANGELOG.md` - This file

## Usage

### Run with Debug Mode
```bash
python mesh_tracker.py --debug
```

### View Debug Output
```bash
# See packets with RSSI
grep "FOUND rxRssi" mesh_tracker_debug_*.log

# See signal history
grep "Latest signal history" mesh_tracker_debug_*.log

# View screen captures
tail -50 mesh_tracker_screen_*.txt
```

### Run Demo
```bash
python demo_tracking.py
```

## Breaking Changes
None - all changes are backward compatible

## Bug Fixes
- Fixed auto-selection to prefer active nodes
- Added proper GPS accuracy warnings
- Enhanced position estimation display

## Performance
- No performance impact
- Debug mode adds minimal overhead
- Screen capture only in debug mode

## Next Steps
- Continue monitoring real-world usage
- Gather feedback on accuracy warnings
- Consider adding distance history graphs

---
*All changes tested and verified*
*Pushed to GitHub: tracking_logic branch*
