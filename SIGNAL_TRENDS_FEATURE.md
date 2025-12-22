# Signal Trends Feature - Quick Reference

## Overview
Added a new feature to display signal strength trends (hotter/colder) over multiple time frames and show the last 5 signal readings for the target node.

## What's New

### 1. Time-Based Signal Trends
The system now shows whether you're getting **HOTTER** (closer) or **COLDER** (farther) from the target node across three time windows:

- **Last 10 seconds**: Short-term trend for immediate feedback
- **Last 60 seconds**: Medium-term trend to see recent movement direction
- **Last 5 minutes**: Long-term trend to understand overall approach

#### Trend Indicators:
- 🔥 **HOTTER** - Signal getting stronger (moving closer or better line of sight)
- ❄️ **COLDER** - Signal getting weaker (moving away or worse line of sight)
- ➡️ **STABLE** - Signal staying roughly the same (perpendicular movement or stationary)

Each trend shows the actual signal change in dBm (e.g., "+5.2 dBm" or "-3.1 dBm")

### 2. Last 5 Signal Readings
Display the last 5 signal measurements received from the target node, showing:
- RSSI value (in dBm)
- SNR value (Signal-to-Noise Ratio in dB)
- How long ago each reading was received

This helps you:
- Verify signal quality over time
- Spot sudden changes or drops
- Understand the recency of data

## Where to Find It

### Terminal Version (mesh_tracker.py)
When tracking a node, the signal trends and last 5 readings appear in the **Navigation & Signal Tracking** panel with:
- Color-coded trends (green=hotter, red=colder, yellow=stable)
- Color-coded readings (green=strong, yellow=medium, red=weak signal)

### GUI Version (mesh_tracker_gui.py)
In the node info panel on the right side, look for:
- **Signal Trends (Hotter/Colder)** section showing all three time windows
- **Last 5 Signal Readings** section showing recent measurements

## How to Use

1. **Select a target node** from the node list
2. **Wait for signal readings** - You need at least 2 readings for trends to appear
3. **Move around** and watch the trends:
   - If HOTTER (🔥): Keep moving in that direction
   - If COLDER (❄️): Turn around or try a different direction
   - If STABLE (➡️): You're moving perpendicular or the node/environment is stable

### Tips:
- **10-second trend** is most useful for immediate navigation feedback
- **60-second trend** helps confirm you're on the right track
- **5-minute trend** shows if your overall strategy is working
- Watch the **last 5 readings** to ensure data is fresh and signal quality is consistent

## Technical Details

### New Methods Added to MeshNode Class:

```python
def get_signal_trend(time_window: int) -> Optional[str]:
    """
    Get signal trend over specified time window in seconds
    Returns: 'hotter', 'colder', 'stable', or None if insufficient data
    """

def get_signal_strength_change(time_window: int) -> Optional[float]:
    """
    Get the actual dBm change over the time window
    Returns: Float representing signal change in dBm
    """

def get_last_n_signal_readings(n: int = 5) -> List[dict]:
    """
    Get the last N signal readings with timestamps
    Returns: List of dicts with 'timestamp', 'rssi', 'snr', and 'age'
    """
```

### Algorithm:
- Compares average signal strength of first half vs second half of time window
- Threshold of ±3 dBm for determining hotter/colder (filters out noise)
- Maintains up to 100 readings in history (approximately 30 minutes of data)

## Testing

Run the test script to verify functionality:
```bash
python3 test_signal_trends.py
```

This simulates walking toward and away from a node and displays the trends.

## Files Modified

1. **mesh_tracker.py**
   - Added `get_last_n_signal_readings()` method to MeshNode
   - Updated tracking display to show trends and last 5 readings

2. **mesh_tracker_gui.py**
   - Added `get_signal_trend()`, `get_signal_strength_change()`, and `get_last_n_signal_readings()` methods
   - Updated node info display to show trends and readings

3. **test_signal_trends.py** (new)
   - Test script demonstrating the feature with simulated data
