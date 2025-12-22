# Signal Trends Feature - Implementation Summary

## Date: 2024-12-22

## Feature Request
Add a feature to show "hotter or colder" signal trends in different time frames (last 10 seconds, last 60 seconds, last 5 minutes) and display the last 5 signal readings to the target node.

## Implementation Complete ✓

### Files Modified

1. **mesh_tracker.py** (Terminal version)
   - Added `get_last_n_signal_readings(n=5)` method to MeshNode class
   - Updated `generate_tracking_view()` to display:
     - Signal trends for 10s, 60s, and 5m time windows
     - Last 5 signal readings with color coding
   - Lines modified: ~165-230 (new methods), ~1515-1545 (display updates)

2. **mesh_tracker_gui.py** (GUI version)
   - Added `get_signal_trend(time_window)` method to MeshNode class
   - Added `get_signal_strength_change(time_window)` method to MeshNode class
   - Added `get_last_n_signal_readings(n=5)` method to MeshNode class
   - Updated `get_node_info()` to display:
     - Signal trends for 10s, 60s, and 5m time windows with emoji indicators
     - Last 5 signal readings with timestamps
   - Lines modified: ~220-310 (new methods), ~2134-2178 (display updates)

### New Methods

#### `get_signal_trend(time_window: int) -> Optional[str]`
- Returns: 'hotter', 'colder', 'stable', or None
- Compares average signal strength of first half vs second half of time window
- Uses ±3 dBm threshold to filter out noise
- Time window in seconds (10, 60, or 300)

#### `get_signal_strength_change(time_window: int) -> Optional[float]`
- Returns: Actual dBm change (e.g., +5.2 or -3.1)
- Same algorithm as trend detection but returns numeric value
- Used to show precise signal change amounts

#### `get_last_n_signal_readings(n: int = 5) -> List[dict]`
- Returns: List of last N signal readings
- Each entry contains: timestamp, rssi, snr, age (seconds ago)
- Automatically calculates how long ago each reading was received

### Display Features

#### Terminal Version (mesh_tracker.py)
- Shows trend emojis: 🔥 (hotter), ❄️ (colder), ➡️ (stable)
- Color codes trends: green (hotter), red (colder), yellow (stable)
- Color codes readings by signal strength: green (>-70), yellow (>-90), red (weak)
- Shows precise dBm changes (e.g., "+5.2 dBm")

#### GUI Version (mesh_tracker_gui.py)
- Shows trend emojis: 🔥 (hotter), ❄️ (colder), ➡️ (stable)
- Displays "Signal Trends (Hotter/Colder):" section
- Shows all three time windows with current trend and dBm change
- Displays "Last 5 Signal Readings:" section
- Shows RSSI, SNR, and age for each reading

### Test File Created

**test_signal_trends.py**
- Standalone test demonstrating the feature
- Simulates walking toward and away from a node
- Verifies trend detection works correctly
- Shows example output for both scenarios

### Documentation Created

1. **SIGNAL_TRENDS_FEATURE.md**
   - Complete feature documentation
   - Usage instructions
   - Technical details
   - API reference

2. **SIGNAL_TRENDS_EXAMPLES.txt**
   - Visual examples of output format
   - Interpretation guide for different scenarios
   - Pattern recognition guide

## How It Works

### Data Collection
- Signal history stored in `node.signal_history` list
- Each entry contains: timestamp, rssi, snr, latitude, longitude
- Maintains up to 100 readings (last 30 minutes)
- Automatically cleaned up (removes old entries)

### Trend Detection Algorithm
1. Filter readings by time window (10s, 60s, or 300s)
2. Split filtered readings into first half and second half
3. Calculate average RSSI for each half
4. Compare averages:
   - Difference > +3 dBm = HOTTER (signal improving)
   - Difference < -3 dBm = COLDER (signal degrading)
   - Otherwise = STABLE (no significant change)

### Why This Works
- RSSI is measured in dBm (negative numbers)
- Higher RSSI (e.g., -65) = stronger signal = closer
- Lower RSSI (e.g., -90) = weaker signal = farther
- 3 dBm threshold filters out random fluctuations
- Comparing halves gives directional trend, not just variance

## Testing Results

Test output shows correct behavior:
```
Scenario 1: Walking TOWARD node (getting HOTTER)
  5 minutes:   hotter (+13.2 dBm) ✓

Scenario 2: Walking AWAY from node (getting COLDER)
  5 minutes:   colder (-13.0 dBm) ✓
```

Last 5 readings correctly show:
- RSSI progression (improving or degrading)
- SNR values
- Time since each reading

## Usage Examples

### For Users
```
Select a target node → Watch the trends:
- 🔥 HOTTER: Keep moving in this direction
- ❄️ COLDER: Turn around, wrong way
- ➡️ STABLE: Move perpendicular or try different direction
```

### For Developers
```python
# Get trend for last 60 seconds
trend = node.get_signal_trend(60)
# Returns: 'hotter', 'colder', 'stable', or None

# Get precise change amount
change = node.get_signal_strength_change(60)
# Returns: +5.2 (dBm improvement)

# Get last 5 readings
readings = node.get_last_n_signal_readings(5)
# Returns: [{'rssi': -68, 'snr': 5.2, 'age': 8.0}, ...]
```

## Benefits

1. **Real-time Navigation Feedback**
   - Immediate confirmation if moving in right direction
   - No need to guess based on single RSSI reading

2. **Multiple Time Scales**
   - 10s: Immediate feedback for adjustments
   - 60s: Confirms you're on right track
   - 5m: Shows overall strategy effectiveness

3. **Historical Context**
   - Last 5 readings show recent signal history
   - Helps identify sudden drops vs gradual changes
   - Useful for detecting obstacles or interference

4. **Easy to Understand**
   - Emoji indicators (🔥/❄️) are intuitive
   - Color coding provides visual feedback
   - Precise dBm values for technical analysis

## Future Enhancements (Potential)

- Add graphical signal strength chart
- Add audio feedback (beep faster when hotter)
- Add prediction: "At current rate, you'll reach target in X minutes"
- Add recommendation engine: "Suggest turning 45° left"
- Add history log: Track all movements and results

## Compatibility

- Works with both terminal (mesh_tracker.py) and GUI (mesh_tracker_gui.py) versions
- No external dependencies required (uses existing signal_history data)
- Backward compatible (doesn't break existing functionality)
- Can be disabled/hidden if not needed (just don't display the sections)

## Performance Impact

- Minimal: O(n) where n = number of readings in time window
- Typical: 10-20 readings per minute = negligible CPU usage
- Memory: 100 readings × ~50 bytes = ~5KB per node
- No network overhead (uses locally collected data)

## Known Limitations

- Requires at least 2 readings for trend detection
- May show "stable" during rapid direction changes
- Environmental factors (obstacles, weather) affect readings
- Works best with consistent node transmission rate
- 3 dBm threshold may need tuning for different environments

## Conclusion

Feature successfully implemented and tested. Provides valuable real-time navigation feedback across multiple time scales with minimal complexity and excellent user experience.
