# Functional Issues Analysis
**Date:** 22 December 2025  
**Analysis Type:** Code Review + Data Log Analysis

## Issues Found

### 1. 🔴 CRITICAL: Position Estimation Uses Only Centroid (No Trilateration)
**File:** [mesh_tracker_gui.py](mesh_tracker_gui.py#L1573-1671)  
**Lines:** 1590-1595

**Problem:**
```python
# Simple centroid method for now
lats = [s['gps_lat'] for s in samples]
lons = [s['gps_lon'] for s in samples]

est_lat = np.mean(lats)
est_lon = np.mean(lons)
```

The GUI version uses a simple centroid (average of GPS positions) instead of actual RSSI-based trilateration. This means:
- RSSI values are collected but **never used** for distance estimation
- Position accuracy is **no better than random GPS averaging**
- The entire premise of "move around to triangulate" is ineffective
- `tx_power`, `freq_mhz`, and `path_loss_exp` parameters are completely ignored

**Expected Behavior:**
Should use SciPy `least_squares` optimization like the terminal version ([mesh_tracker.py](mesh_tracker.py#L907-950)):
1. Convert RSSI to distance using FSPL model
2. Apply SNR-based weighting
3. Use least squares to find optimal position
4. Calculate RMSE error estimate

**Impact:** **HIGH** - Core functionality is broken

**Fix Required:** Implement actual trilateration algorithm in `estimate_node_position()`

---

### 2. 🟡 MEDIUM: Missing Time Decay Weighting
**File:** [mesh_tracker_gui.py](mesh_tracker_gui.py#L1573)  
**Lines:** 1574 (entire function)

**Problem:**
No time-based decay for old samples. The GUI version keeps up to 200 samples (line 1553) with no preference for recent data.

**Expected Behavior:**
Terminal version applies exponential decay: `weight *= exp(-age / tau)` where tau ≈ 300-600s

**Impact:** **MEDIUM** - Old samples equally weighted with fresh ones, reducing accuracy when moving

**Fix Required:** Add time decay factor in weight calculation

---

### 3. 🟡 MEDIUM: No SNR Weighting
**File:** [mesh_tracker_gui.py](mesh_tracker_gui.py#L1590-1595)

**Problem:**
SNR values are collected (line 1534) but never used in calculations.

**Expected Behavior:**
Terminal version multiplies weight by `(SNR + 10)` to prefer high-quality signals

**Impact:** **MEDIUM** - Poor quality samples weighted same as good ones

**Fix Required:** Incorporate SNR into sample weighting

---

### 4. 🟡 MEDIUM: No Outlier Filtering
**File:** [mesh_tracker_gui.py](mesh_tracker_gui.py#L1590-1595)

**Problem:**
All samples used directly with no statistical filtering.

**Expected Behavior:**
Terminal version filters samples >2 standard deviations from mean RSSI (mesh_tracker.py#L837-848)

**Impact:** **MEDIUM** - Bad readings can significantly skew results

**Fix Required:** Add outlier filtering before position calculation

---

### 5. 🟡 MEDIUM: No Diversity Checking
**File:** [mesh_tracker_gui.py](mesh_tracker_gui.py#L1573-1671)

**Problem:**
No bearing spread analysis to ensure samples are geometrically diverse.

**Expected Behavior:**
Terminal version requires >30° bearing spread (mesh_tracker.py#L862-872), warns user if samples too clustered

**Impact:** **MEDIUM** - Can estimate position from clustered samples (geometrically weak)

**Fix Required:** Calculate bearing spread and warn if insufficient

---

### 6. 🟡 MEDIUM: No RMSE Error Estimate
**File:** [mesh_tracker_gui.py](mesh_tracker_gui.py#L1638-1639)

**Problem:**
Confidence level is based only on sample count and RSSI std dev, not actual fit quality.

```python
confidence = "HIGH"
if len(samples) < 5:
    confidence = "LOW"
elif len(samples) < 10:
    confidence = "MEDIUM"
elif std_rssi > 15:
    confidence = "MEDIUM"
```

**Expected Behavior:**
Terminal version calculates RMSE from optimization residuals, providing actual meters of uncertainty

**Impact:** **MEDIUM** - User has no idea if position is accurate (could be 10m or 1000m off)

**Fix Required:** Calculate and display RMSE from trilateration residuals

---

### 7. 🟢 LOW: Unused Distance Function
**File:** [mesh_tracker_gui.py](mesh_tracker_gui.py#L360-378)

**Problem:**
Function `estimate_distance_from_rssi()` exists but is never called. Parameters `tx_power`, `path_loss_exp`, `freq_mhz` are set but unused.

**Impact:** **LOW** - Code bloat, but not affecting functionality since trilateration is missing anyway

**Fix Required:** Remove function or integrate into proper trilateration

---

### 8. 🟢 LOW: Inconsistent Sample Limits
**File:** [mesh_tracker_gui.py](mesh_tracker_gui.py#L1553-1574)

**Problem:**
- Line 1553: Keeps max 200 samples
- Line 1574: Uses last 100 samples for estimation
- No configuration option (terminal version has `--max-samples`)

**Impact:** **LOW** - Works, but arbitrary limits with no user control

**Fix Required:** Make limits configurable via command-line args

---

### 9. 🟢 LOW: Log File Doesn't Record Sample Collection
**File:** [mesh_tracker_gui.py](mesh_tracker_gui.py#L1537)

**Problem:**
Samples appended to `node.estimation_samples` are not logged to JSONL file. Only raw mesh packets are logged.

**Impact:** **LOW** - Can't replay/analyze estimation from logs

**Fix Required:** Add log entry when sample is collected for estimation

---

## Data Log Analysis

### Log File: mesh_tracker_20251222_084342.jsonl
- **Total entries:** 3
- **Mesh packets:** 3 (with position: 1, with user: 1)
- **GPS entries:** 0
- **Duration:** Very short session (likely test run)

### Observations:
1. No GPS data logged - explains why no samples were collected
2. Received mesh packet with node position (35.9684°N, 115.0814°W)
3. Node identified as "Test" / "Test Node"
4. RSSI: -94 dBm, SNR: 5.5 dB

---

## Comparison: GUI vs Terminal Version

| Feature | Terminal (mesh_tracker.py) | GUI (mesh_tracker_gui.py) | Status |
|---------|---------------------------|---------------------------|--------|
| RSSI→Distance Conversion | ✅ FSPL model | ❌ Not used | **BROKEN** |
| Trilateration | ✅ SciPy least_squares | ❌ Simple centroid | **BROKEN** |
| SNR Weighting | ✅ Yes | ❌ No | Missing |
| Time Decay | ✅ Exponential | ❌ No | Missing |
| Outlier Filtering | ✅ 2σ filter | ❌ No | Missing |
| Diversity Check | ✅ 30° requirement | ❌ No | Missing |
| RMSE Calculation | ✅ Yes | ❌ No | Missing |
| Motion Detection | ✅ Multi-factor | ✅ Multi-factor | ✅ OK |
| Kalman Filtering | ✅ Yes | ✅ Yes | ✅ OK |
| Sample Limiting | ✅ Configurable | ⚠️ Hardcoded | Partial |

---

## Root Cause

Looking at the code history, the GUI version was likely created as a simplified prototype with placeholder trilateration ("centroid for now" - line 1590 comment). The comment suggests this was meant to be temporary, but the actual algorithm was never implemented.

---

## Recommended Fix Priority

### Immediate (Before Any Field Testing):
1. ✅ **Fix #1**: Implement proper RSSI-based trilateration
   - Port algorithm from terminal version
   - Use `scipy.optimize.least_squares`
   - Calculate RMSE and return error estimate

### High Priority:
2. ✅ **Fix #2-5**: Add outlier filtering, SNR weighting, time decay, diversity checks
   - Ensures position accuracy
   - Prevents bad data from corrupting results

### Medium Priority:
3. ✅ **Fix #6**: Display RMSE in UI
   - Give user confidence indication
   - Show in "Tracking Info" panel

### Low Priority:
4. ✅ **Fix #7-9**: Code cleanup
   - Remove unused functions
   - Make limits configurable
   - Improve logging

---

## Testing Recommendation

**DO NOT** field test GUI version until Fix #1 is implemented. Current implementation:
- Will produce random results (centroid of your walking path)
- Cannot accurately locate stationary nodes
- Wastes time collecting RSSI samples that aren't used

The signal trends feature works (shows hot/cold correctly) but position estimation is fundamentally broken.

---

## Positive Findings

✅ Signal history tracking works correctly  
✅ Kalman filtering implementation looks good  
✅ Motion detection algorithm is sound  
✅ GPS parsing and data collection works  
✅ USB connection handling improved with retry logic  
✅ UI displays data correctly (just not calculating it right)

The infrastructure is solid - just need to connect RSSI data to position calculation properly.
