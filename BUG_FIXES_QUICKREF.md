# Bug Fixes - Quick Reference

## ✅ All 4 Bugs Fixed (21 Dec 2025)

### 1. Heatmap Overlay ✅
**What:** Estimated position now shows as white 'X' on heatmap grid  
**Usage:** Press 'H' in tracking mode or use `--auto-heatmap`  
**Visual:** Look for bright white 'X' marker on the colored heatmap

### 2. Auto-Heatmap ✅
**What:** Automatically displays heatmap when position is estimated  
**Usage:** `python mesh_tracker.py --auto-heatmap`  
**Behavior:** Shows heatmap for 3 seconds after each position update

### 3. Kalman Initialization ✅
**What:** Smoother startup without position jumps  
**Impact:** First position estimate is now more stable  
**Technical:** Uses 50m initial uncertainty with proper covariance

### 4. Motion Detection ✅
**What:** Better detection of moving vs. stationary targets  
**Factors:** Position change (50m) OR RSSI variance (10dBm) OR velocity (2m/s)  
**Display:** Shows "🚶 MOTION" flag when target is moving

---

## Test Results

### test_improvements.py
```
✓ PASS: Imports
✓ PASS: Outlier Filtering
✓ PASS: Time Decay Weighting
✓ PASS: RSSI to Distance
✓ PASS: Kalman Filter
✓ PASS: SciPy Trilateration
✓ PASS: Heatmap Binning
Total: 7/7 tests passed
```

### test_bug_fixes.py
```
✓ PASS: Heatmap Overlay
✓ PASS: Auto-heatmap Integration
✓ PASS: Improved Kalman Init
✓ PASS: Enhanced Motion Detection
Total: 4/4 tests passed
```

---

## Running Tests

```bash
# Run improvement tests
cd /home/iain/MeshLocator/MeshtasticDeviceLocator
source venv/bin/activate
python test_improvements.py

# Run bug fix tests
python test_bug_fixes.py
```

---

## Using Auto-Heatmap

```bash
# Basic usage
python mesh_tracker.py --auto-heatmap

# With debug mode
python mesh_tracker.py --auto-heatmap --debug

# With custom grid size
python mesh_tracker.py --auto-heatmap --heatmap-grid 30x15

# Full featured
python mesh_tracker.py --auto-heatmap --debug --max-samples 200 --time-decay 600
```

---

## Keyboard Commands

| Key | Action |
|-----|--------|
| `1-9` | Select node from list |
| `H` | Show heatmap (manual) |
| `B` | Back to node list |
| `Q` | Quit |

With `--auto-heatmap`: Heatmap shows automatically, 'H' still works for manual display

---

## Files Changed

- `mesh_tracker.py` - All fixes implemented (~150 lines modified)
- `test_bug_fixes.py` - New test file (320 lines)
- `BUG_FIXES_SUMMARY.md` - Detailed documentation

---

## Status: ✅ PRODUCTION READY

All bugs fixed, tested, and validated.
