# Mesh Tracker Improvements - Quick Start Guide

## What's New

This implementation adds **4 major priorities** to improve RSSI-based position estimation:

1. **✅ Priority 1**: Improved RSSI Triangulation (outlier filtering, SNR weights, SciPy optimization)
2. **✅ Priority 2**: Unlimited Sample Storage with Time-Decay Weighting
3. **✅ Priority 3**: Kalman Filter for Moving Target Tracking
4. **✅ Priority 4**: Terminal-based RSSI Heatmap Visualization
5. **⏸️ Priority 5**: GUI with PySimpleGUI (deferred for future implementation)

## Installation

### 1. Install New Dependencies (Using Virtual Environment - Recommended)

```bash
cd /home/iain/MeshLocator/MeshtasticDeviceLocator

# Option A: Automated installation with venv
./install.sh

# Option B: Manual venv setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

This will install:
- `numpy>=1.21.0` - Array operations and statistics
- `scipy>=1.7.0` - Advanced optimization (least_squares)
- `filterpy>=1.4.5` - Kalman filtering

### 2. Verify Installation

Run the test script to ensure all dependencies work:

```bash
# If you used install.sh, venv is already active
python test_improvements.py

# If manual setup, activate venv first
source venv/bin/activate
python test_improvements.py
```

Expected output: `✓ All tests passed! Ready to run mesh_tracker.py`

### 3. Running the Tracker

```bash
# Option A: Use convenience script (handles venv automatically)
./run.sh

# Option B: Activate venv manually
source venv/bin/activate
python mesh_tracker.py

# When done
deactivate
```

## Usage

### Basic Usage (Default Settings)

```bash
# Using convenience script (recommended)
./run.sh

# Or with venv activated
source venv/bin/activate
python mesh_tracker.py
```

**Defaults:**
- Frequency: 915 MHz (US)
- Tx Power: 14 dBm
- Path Loss: 2.5 (outdoor)
- Time Decay: 300s (5 minutes)
- Unlimited sample storage

### Custom Configuration Examples

#### European Settings (868 MHz)
```bash
./run.sh --freq 868.0
```

#### Indoor/Urban Environment (Higher Path Loss)
```bash
./run.sh --path-loss 3.5
```

#### Limit Estimation Window
```bash
# Use only last 100 samples
./run.sh --max-samples 100
```

#### Faster Time Decay (Prioritize Recent Samples)
```bash
# 2-minute decay instead of 5
./run.sh --time-decay 120
```

#### Custom Heatmap Grid
```bash
# 30 columns x 15 rows
./run.sh --heatmap-grid 30x15
```

#### Debug Mode
```bash
./run.sh --debug
```

## New Features

### 1. Enhanced Position Estimation

**Automatic Outlier Filtering:**
- Removes RSSI samples >2 standard deviations from mean
- Prevents bad readings from skewing results

**SNR-Enhanced Weighting:**
- Incorporates Signal-to-Noise Ratio when available
- Formula: `weight = 10^(RSSI/20) * (SNR + 10)`

**Diversity Checking:**
- Ensures samples span >30° bearing spread
- Prompts you to move if samples too clustered

**Advanced Trilateration:**
- Uses SciPy's robust `least_squares` optimization
- Provides RMSE error estimate in meters

### 2. Unlimited Sample Storage

**Before:** 100-sample rolling window (data loss)
**After:** Unlimited storage with smart downsampling

- All samples stored indefinitely
- Automatic downsampling at 500 samples (keeps every other)
- Time-based decay weights recent samples more heavily

**Time Decay Formula:**
```
weight *= exp(-sample_age / time_constant)
```
- Default: 5-minute half-life
- Configurable via `--time-decay`

### 3. Kalman Filter Tracking

**Automatic Motion Detection:**
- Detects if target moved >50m between estimates
- Or if RSSI std dev >10 dBm (signal instability)
- Increases Kalman process noise when motion detected

**Smoothed Position Tracking:**
- Uses constant-velocity Kalman filter (4-state)
- State: [latitude, longitude, velocity_lat, velocity_lon]
- Provides tracking uncertainty estimate

**When Active:**
- Requires ≥5 samples
- Method shown as "SciPy + Kalman filter"
- Tracking error displayed in metrics

### 4. Terminal Heatmap

**Press 'H' in tracking mode** to generate RSSI heatmap

**Features:**
- ANSI 24-bit color (green=weak, red=strong)
- Auto-scales to sample extent
- Shows legend with RSSI range
- Displays estimated position coordinates
- Requires ≥10 samples

**Customization:**
```bash
# Larger grid for more detail
python mesh_tracker.py --heatmap-grid 40x20
```

## New Keyboard Controls

| Key | Action |
|-----|--------|
| **1-9** | Select node (in list mode) |
| **B** | Back to node list (from tracking) |
| **H** | Show heatmap (in tracking mode, ≥10 samples) |
| **Q** | Quit |

## New Metrics Display

When tracking a node, the **Metrics Panel** shows:

| Metric | Description |
|--------|-------------|
| Total Samples Collected | All samples stored |
| Valid Samples Used | After outlier filtering |
| Avg RSSI | Mean signal strength (dBm) |
| RSSI Std Dev | Signal variability |
| Est. Error (RMSE) | Position uncertainty from trilateration |
| Sample Diversity | Bearing spread (degrees) |
| Avg Sample Age | How old samples are (minutes) |
| Motion Status | Yes/No if target appears to be moving |
| Tracking Error | Kalman filter uncertainty (meters) |

## CLI Arguments Reference

### Existing Arguments
- `--gps-port PORT` - UDP port for GPS data (default: 2947)
- `--meshtastic-port PORT` - Serial port for Meshtastic device
- `--debug` - Enable debug logging

### New Arguments (Priority 1-2)
- `--path-loss N` - Path loss exponent (default: 2.5)
  - 2.0 = free space
  - 2.5 = outdoor
  - 3.0-4.0 = urban/indoor
  
- `--tx-power DBM` - Transmit power in dBm (default: 14.0)
  - US: 14 dBm typical
  - EU: 10-14 dBm
  
- `--freq MHZ` - Frequency in MHz (default: 915.0)
  - US: 915 MHz
  - EU: 868 MHz
  
- `--max-samples N` - Limit estimation window (default: None = all)
  - Use if running on low-memory device
  - Example: `--max-samples 200`
  
- `--time-decay SEC` - Time decay constant (default: 300.0 = 5 min)
  - Lower = prioritize recent samples more
  - Higher = smoother long-term tracking

### New Arguments (Priority 4)
- `--heatmap-grid WxH` - Heatmap grid size (default: 20x10)
  - Example: `--heatmap-grid 30x15`
  
- `--auto-heatmap` - Auto-generate heatmap on updates
  - Manual mode (default): Press 'H' to show
  - Auto mode: Updates automatically (not yet fully integrated)

## Troubleshooting

### Dependencies Won't Install
```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Install dependencies one by one
pip install numpy
pip install scipy
pip install filterpy
```

### Heatmap Shows "Not enough samples"
- Need at least 10 samples
- Move to different positions while tracking
- Wait for more packet transmissions

### Motion Always Detected
- Check if you're moving (Pi GPS changing)
- Try increasing motion threshold in code (currently 50m)
- Check RSSI stability (std dev should be <10 dBm for stationary)

### Kalman Filter Not Activating
- Need at least 5 valid samples
- Check metrics panel for sample count
- Ensure diversity check passes (>30° bearing spread)

### Poor Position Accuracy
1. Collect more samples from diverse positions
2. Ensure good GPS fix (6+ satellites)
3. Try adjusting `--path-loss` for your environment
4. Check RSSI Std Dev in metrics (should be <15 dBm)
5. Look at RMSE error estimate (<100m is decent)

## Performance Notes

### Memory Usage
- ~1KB per sample
- 500 samples ≈ 500 KB per node
- Downsampling prevents excessive growth

### CPU Usage
- NumPy/SciPy: <1ms per estimation
- Kalman filter: negligible overhead
- Heatmap: 100-500ms (only when pressing 'H')

### Battery Impact
- No significant additional drain
- Same sampling rate as before
- Calculations done on Pi, not device

## Comparison: Before vs After

| Aspect | Before | After (Priorities 1-4) |
|--------|--------|------------------------|
| **Accuracy** | Basic centroid | SciPy optimization |
| **Filtering** | None | 2σ outlier removal |
| **Data Usage** | 100 samples max | Unlimited (downsampled) |
| **Motion** | Not handled | Kalman tracking |
| **Metrics** | Basic | 8+ detailed metrics |
| **Visualization** | Text only | Terminal heatmap |
| **SNR** | Ignored | Incorporated in weights |
| **Time Weighting** | Equal | Exponential decay |
| **Error Estimate** | None | RMSE + Kalman uncertainty |

## What's Next?

### Immediate Testing
1. Run `python test_improvements.py` to validate setup
2. Start tracker with default settings
3. Track a node and collect ≥30 samples
4. Press 'H' to see heatmap
5. Check metrics panel for accuracy estimates

### Future Enhancements (Priority 5 - GUI)
- PySimpleGUI interface
- Embedded matplotlib heatmaps
- Real-time map overlay
- Export to PNG/KML
- WebSocket API

## Support

**Documentation:**
- `IMPROVEMENTS_SUMMARY.md` - Detailed technical documentation
- `README.md` - Original project README
- `DEBUG_FINDINGS.md` - Debugging notes

**Testing:**
- `test_improvements.py` - Validation script
- `test_mesh_tracker.py` - Original tests

**For issues:** Check GitHub repo or debug logs with `--debug` flag

## Example Session

```bash
# 1. Install and test
pip install -r requirements.txt
python test_improvements.py

# 2. Start tracker with debug
python mesh_tracker.py --debug

# 3. In terminal:
#    - Wait for nodes to appear
#    - Press 1-9 to select a node
#    - Move around to collect samples from different positions
#    - Watch metrics panel for sample count and diversity
#    - Press H when you have 10+ samples to see heatmap
#    - Press B to go back, Q to quit

# 4. Review logs
ls mesh_tracker_*.jsonl     # Data logs
ls mesh_tracker_debug_*.log # Debug logs (if --debug)
```

## Tips for Best Results

1. **Collect samples from diverse positions** (≥30° bearing spread required)
2. **Maintain good GPS fix** (6+ satellites)
3. **Adjust path loss for environment** (2.5 outdoor, 3.5 urban)
4. **Wait for 20+ samples** before trusting estimates
5. **Check RMSE in metrics** (lower is better, <50m is good)
6. **Use heatmap** to visualize signal distribution
7. **Enable debug mode** if troubleshooting (`--debug`)

---

**Updated:** December 21, 2025
**Version:** Priorities 1-4 Complete
**Status:** Ready for Testing
