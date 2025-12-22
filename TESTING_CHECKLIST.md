# Testing Checklist for RSSI Improvements

**Branch:** `feature/rssi-improvements`  
**Status:** Ready for testing - DO NOT MERGE until tested

## Pre-Testing Setup

### 1. Pull the Branch
```bash
cd /home/iain/MeshLocator/MeshtasticDeviceLocator
git fetch origin
git checkout feature/rssi-improvements
```

### 2. Set Up Virtual Environment
```bash
# Automated setup (recommended)
./install.sh

# This will:
# - Create venv if needed
# - Install all dependencies
# - Run validation tests
```

### 3. Verify Installation
Expected output from install.sh:
```
✓ All tests passed!
```

If tests fail, dependencies may not be installed correctly.

---

## Testing Checklist

### ✅ Basic Functionality Tests

- [ ] **Start tracker with defaults**
  ```bash
  ./run.sh
  ```
  - Should start without errors
  - GPS should connect
  - Meshtastic should connect
  - Nodes should appear in list

- [ ] **Select and track a node**
  - Press 1-9 to select a node
  - Should switch to tracking view
  - Should show node details

- [ ] **Press 'B' to go back**
  - Should return to node list
  - Should deselect node

- [ ] **Press 'Q' to quit**
  - Should exit cleanly
  - Should close connections

### ✅ Priority 1: RSSI Triangulation

- [ ] **Collect samples from different positions**
  - Move to 3-5 different locations
  - Stay at each location for 30 seconds
  - GPS should show your movement
  - Sample count should increase

- [ ] **Check diversity warning**
  - If samples too close together:
    - Should show "Insufficient sample diversity" message
    - Should display bearing spread < 30°
  - Move to more diverse positions

- [ ] **Verify metrics panel appears**
  - Should show after first estimation
  - Check for these metrics:
    - [ ] Total Samples Collected
    - [ ] Valid Samples Used
    - [ ] Avg RSSI (dBm)
    - [ ] RSSI Std Dev
    - [ ] Est. Error (RMSE in meters)
    - [ ] Sample Diversity (degrees)
    - [ ] Avg Sample Age

- [ ] **Test outlier filtering**
  - If RSSI has high variance:
    - Should see "After outlier filtering: X samples" in logs
    - Used samples should be < total samples

- [ ] **Test SNR incorporation**
  - If node reports SNR:
    - Should see SNR values in node details
    - Estimation should use enhanced weights

### ✅ Priority 2: Sample Storage & Time Decay

- [ ] **Unlimited sample collection**
  - Collect >100 samples (let it run 10+ minutes)
  - Should not cap at 100
  - Check "Total Samples Collected" in metrics

- [ ] **Verify downsampling at 500**
  - Collect >500 samples (may take 30+ minutes)
  - Should auto-downsample to ~250
  - Should see debug message if --debug enabled

- [ ] **Test time decay weighting**
  - Collect samples, then wait 5-10 minutes
  - Collect more samples
  - "Avg Sample Age" should show mixed ages
  - Recent samples should influence estimate more

- [ ] **Test max-samples limit**
  ```bash
  ./run.sh --max-samples 50
  ```
  - Should only use last 50 samples for estimation
  - Total collected can be higher

### ✅ Priority 3: Kalman Filter & Motion Detection

- [ ] **Static target (node not moving)**
  - Collect ≥5 samples while stationary
  - Should see "Method: SciPy + Kalman filter" in logs
  - Motion Status should show "No"
  - Should show "Tracking error: ±X m (Kalman)"

- [ ] **Moving target simulation**
  - Option A: Actually move the target node
  - Option B: Simulate by having high RSSI variance
  - Should detect motion:
    - [ ] "Motion Detected: Yes" in metrics
    - [ ] "🚶 MOTION" flag in estimation logs
  - Kalman filter should adapt (higher process noise)

- [ ] **Verify Kalman smoothing**
  - Position updates should be smoother than raw estimates
  - Compare "Est. error (RMSE)" vs "Tracking error (Kalman)"
  - Kalman error usually lower (more confident)

### ✅ Priority 4: Terminal Heatmap

- [ ] **Generate heatmap with 'H' key**
  - Collect ≥10 samples from different positions
  - Press 'H' while tracking
  - Should see:
    - [ ] Colored grid (green to red)
    - [ ] Legend showing RSSI range
    - [ ] Grid dimensions
    - [ ] Sample count
    - [ ] Range in meters

- [ ] **Verify color mapping**
  - Strong signal areas (close) = RED
  - Weak signal areas (far) = GREEN
  - Empty cells = blank space

- [ ] **Test custom grid size**
  ```bash
  ./run.sh --heatmap-grid 30x15
  ```
  - Should show 30 columns x 15 rows
  - More detail than default 20x10

- [ ] **Exit heatmap**
  - Press any key
  - Should return to tracking view

### ✅ CLI Arguments Testing

- [ ] **Test path loss adjustment**
  ```bash
  ./run.sh --path-loss 3.5
  ```
  - Indoor/urban: Should estimate longer distances for same RSSI

- [ ] **Test frequency change**
  ```bash
  ./run.sh --freq 868.0  # European
  ```
  - Should use EU frequency in calculations

- [ ] **Test tx power**
  ```bash
  ./run.sh --tx-power 10.0  # Lower power
  ```
  - Should estimate shorter distances

- [ ] **Test time decay**
  ```bash
  ./run.sh --time-decay 120  # 2-minute decay
  ```
  - Older samples should lose weight faster

- [ ] **Test debug mode**
  ```bash
  ./run.sh --debug
  ```
  - Should create debug log file
  - Should show debug messages

### ✅ Edge Cases & Error Handling

- [ ] **No GPS fix**
  - Disconnect GPS or go indoors
  - Should show "NO GPS FIX" warning
  - Should not attempt estimation

- [ ] **Insufficient samples**
  - Track node with <3 samples
  - Should show "Need 3 samples minimum" message

- [ ] **Poor diversity**
  - Collect samples from same location
  - Should warn about insufficient diversity
  - Should prompt to move

- [ ] **No RSSI data**
  - If node doesn't report RSSI
  - Should handle gracefully (no crash)

### ✅ Performance Tests

- [ ] **CPU usage**
  - Monitor with `top` while running
  - Should be <20% CPU on Pi
  - Spikes during estimation are normal (<1 second)

- [ ] **Memory usage**
  - Monitor with `free -h`
  - Should use <100 MB for 500 samples

- [ ] **UI responsiveness**
  - Display should update smoothly
  - Keyboard input should be responsive
  - No lag when pressing keys

---

## Expected Issues (Known Limitations)

1. **Heatmap position overlay**: Estimated position shown in text, not overlaid on grid
2. **Auto-heatmap**: Flag exists but not fully integrated in main loop
3. **Kalman first update**: May jump slightly on initialization
4. **Motion detection**: Simple threshold-based, may false-positive with signal instability

---

## Success Criteria

✅ **Must Pass:**
- [ ] No crashes or exceptions
- [ ] All metrics display correctly
- [ ] Position estimates improve with more samples
- [ ] Heatmap renders correctly
- [ ] Kalman filter activates with ≥5 samples

✅ **Should Work:**
- [ ] RMSE error <100m for 20+ diverse samples
- [ ] Outlier filtering removes bad samples
- [ ] Time decay prioritizes recent data
- [ ] Motion detection works for large changes

✅ **Good to Have:**
- [ ] RMSE error <50m for 50+ samples
- [ ] Kalman tracking smoother than raw estimates
- [ ] Heatmap clearly shows signal gradient

---

## Testing Report Template

After testing, document results:

```markdown
## Testing Results - [Date]

**Hardware:** [Raspberry Pi model, Meshtastic device]  
**Environment:** [Indoor/Outdoor, Urban/Rural]  
**GPS Quality:** [Satellites, fix quality]

### Priorities Tested
- [ ] Priority 1: RSSI Triangulation - PASS / FAIL / PARTIAL
- [ ] Priority 2: Sample Storage - PASS / FAIL / PARTIAL
- [ ] Priority 3: Kalman Filter - PASS / FAIL / PARTIAL
- [ ] Priority 4: Heatmap - PASS / FAIL / PARTIAL

### Issues Found
1. [Issue description]
   - Expected: [what should happen]
   - Actual: [what happened]
   - Severity: HIGH / MEDIUM / LOW

### Performance Notes
- CPU usage: [%]
- Memory usage: [MB]
- Sample collection rate: [samples/minute]
- Estimation accuracy: [RMSE in meters]

### Recommendations
- [ ] Merge to main
- [ ] Needs fixes (see issues)
- [ ] Needs more testing

### Screenshots/Logs
[Attach relevant screenshots or log excerpts]
```

---

## If Issues Found

**Report in GitHub:**
1. Create issue on `feature/rssi-improvements` branch
2. Include testing report
3. Attach logs if available (`mesh_tracker_debug_*.log`)

**Quick Fixes:**
1. Make changes on `feature/rssi-improvements` branch
2. Commit and push
3. Re-test

**Major Issues:**
1. Don't merge to main
2. Discuss alternatives
3. Consider reverting specific changes

---

## Post-Testing: Merge Process

**Only after successful testing:**

```bash
# Switch to main branch
git checkout main

# Merge feature branch
git merge feature/rssi-improvements

# Push to GitHub
git push origin main
```

**Or create Pull Request on GitHub:**
1. Go to repository
2. Create PR from `feature/rssi-improvements` to `main`
3. Add testing results to PR description
4. Merge when approved

---

## Quick Test (Minimal)

If short on time, minimum test:

```bash
# 1. Install
./install.sh

# 2. Run with debug
./run.sh --debug

# 3. Track a node for 5 minutes
#    - Collect samples from 3-4 positions
#    - Press H to see heatmap
#    - Check metrics panel

# 4. Verify no errors in logs
tail -f mesh_tracker_debug_*.log

# 5. If all looks good, merge
```

---

**Testing Date:** _______________  
**Tested By:** _______________  
**Result:** PASS / FAIL / NEEDS_WORK  
**Ready to Merge:** YES / NO
