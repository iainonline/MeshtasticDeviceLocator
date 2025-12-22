#!/bin/bash
# GUI Testing Script with Screenshots
# This script runs the mesh tracker GUI in test mode and captures screenshots

set -e

# Configuration
TEST_DIR="test_screenshots"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_SESSION="${TEST_DIR}/session_${TIMESTAMP}"
SCREENSHOT_DELAY=3  # Seconds to wait before taking screenshot

# Create test directory
mkdir -p "${TEST_SESSION}"

echo "=========================================="
echo "Mesh Tracker GUI Test Suite"
echo "Session: ${TIMESTAMP}"
echo "Output: ${TEST_SESSION}"
echo "=========================================="
echo ""

# Check for screenshot tool
SCREENSHOT_CMD=""
if command -v scrot &> /dev/null; then
    SCREENSHOT_CMD="scrot"
    echo "Using scrot for screenshots"
elif command -v gnome-screenshot &> /dev/null; then
    SCREENSHOT_CMD="gnome-screenshot"
    echo "Using gnome-screenshot for screenshots"
elif command -v import &> /dev/null; then
    SCREENSHOT_CMD="import"
    echo "Using ImageMagick import for screenshots"
else
    echo "ERROR: No screenshot tool found!"
    echo "Please install one of: scrot, gnome-screenshot, or imagemagick"
    exit 1
fi

# Function to take screenshot
take_screenshot() {
    local name=$1
    local description=$2
    local filename="${TEST_SESSION}/${name}.png"
    
    echo "Taking screenshot: ${name}"
    echo "  Description: ${description}"
    
    sleep ${SCREENSHOT_DELAY}
    
    case ${SCREENSHOT_CMD} in
        scrot)
            scrot -u "${filename}" 2>/dev/null || scrot "${filename}" 2>/dev/null
            ;;
        gnome-screenshot)
            gnome-screenshot -w -f "${filename}" 2>/dev/null
            ;;
        import)
            import -window root "${filename}" 2>/dev/null
            ;;
    esac
    
    if [ -f "${filename}" ]; then
        echo "  ✓ Saved: ${filename}"
        echo "${name}|${description}|${filename}" >> "${TEST_SESSION}/manifest.txt"
    else
        echo "  ✗ Failed to capture screenshot"
    fi
    echo ""
}

# Function to get window ID of GUI
get_gui_window() {
    xdotool search --name "Mesh Tracker" 2>/dev/null | head -1
}

# Start the GUI in test mode with logging
echo "Starting GUI in test mode..."
./run_gui.sh --log-data --verbose > "${TEST_SESSION}/gui_output.log" 2>&1 &
GUI_PID=$!
echo "GUI started with PID: ${GUI_PID}"
echo ""

# Wait for GUI to initialize
echo "Waiting for GUI to initialize (10 seconds)..."
sleep 10

# Check if GUI is still running
if ! ps -p ${GUI_PID} > /dev/null; then
    echo "ERROR: GUI failed to start"
    cat "${TEST_SESSION}/gui_output.log"
    exit 1
fi

# Test 1: Initial state
take_screenshot "01_initial_state" "GUI initial state after startup"

# Test 2: Wait for GPS lock (if available)
echo "Waiting 15 seconds for GPS lock..."
sleep 15
take_screenshot "02_gps_lock" "GUI after waiting for GPS lock"

# Test 3: Wait for node discovery
echo "Waiting 20 seconds for node discovery..."
sleep 20
take_screenshot "03_nodes_discovered" "GUI after node discovery period"

# Test 4: Simulate node selection (if window manager supports it)
if command -v xdotool &> /dev/null; then
    echo "Attempting to select first node..."
    WINDOW_ID=$(get_gui_window)
    if [ -n "${WINDOW_ID}" ]; then
        # Focus window
        xdotool windowactivate ${WINDOW_ID}
        sleep 1
        
        # Try to click on node list (approximate position)
        xdotool mousemove --window ${WINDOW_ID} 150 200
        xdotool click 1
        sleep 2
        
        take_screenshot "04_node_selected" "GUI with node selected"
    fi
fi

# Test 5: Let it run for data collection
echo "Running for 30 seconds to collect data..."
sleep 30
take_screenshot "05_data_collection" "GUI after 30 seconds of data collection"

# Test 6: Check signal plot
echo "Waiting for signal history to build..."
sleep 20
take_screenshot "06_signal_plot" "GUI showing signal history plot"

# Functional Tests
echo "=========================================="
echo "Running Functional Tests"
echo "=========================================="

# Test 7: Check for errors in logs
echo "Test 7: Checking for errors in output..."
ERROR_COUNT=$(grep -c "ERROR" "${TEST_SESSION}/gui_output.log" || echo "0")
TRACEBACK_COUNT=$(grep -c "Traceback" "${TEST_SESSION}/gui_output.log" || echo "0")
echo "  Errors found: ${ERROR_COUNT}"
echo "  Tracebacks found: ${TRACEBACK_COUNT}"

if [ ${ERROR_COUNT} -gt 0 ]; then
    echo "  ✗ FAIL: Errors detected in log"
    grep "ERROR" "${TEST_SESSION}/gui_output.log" | head -5 > "${TEST_SESSION}/errors.txt"
else
    echo "  ✓ PASS: No errors detected"
fi

# Test 8: Verify node discovery
echo "Test 8: Verifying node discovery..."
NODE_COUNT=$(grep "Displaying.*nodes in list" "${TEST_SESSION}/gui_output.log" | tail -1 | grep -oP '\d+' | head -1 || echo "0")
echo "  Nodes discovered: ${NODE_COUNT}"

if [ ${NODE_COUNT} -gt 0 ]; then
    echo "  ✓ PASS: Nodes discovered (${NODE_COUNT})"
else
    echo "  ✗ FAIL: No nodes discovered"
fi

# Test 9: Verify GPS functionality
echo "Test 9: Verifying GPS lock..."
GPS_COUNT=$(grep -c "GPS Fix:" "${TEST_SESSION}/gui_output.log" || echo "0")
echo "  GPS readings: ${GPS_COUNT}"

if [ ${GPS_COUNT} -gt 5 ]; then
    echo "  ✓ PASS: GPS lock achieved"
    GPS_SAMPLE=$(grep "GPS Fix:" "${TEST_SESSION}/gui_output.log" | tail -1)
    echo "  Sample: ${GPS_SAMPLE}"
else
    echo "  ✗ FAIL: No GPS lock"
fi

# Test 10: Check RSSI/SNR data collection
echo "Test 10: Checking RSSI/SNR data..."
RSSI_COUNT=$(grep -c "RSSI:" "${TEST_SESSION}/gui_output.log" || echo "0")
SNR_COUNT=$(grep -c "SNR:" "${TEST_SESSION}/gui_output.log" || echo "0")
echo "  RSSI readings: ${RSSI_COUNT}"
echo "  SNR readings: ${SNR_COUNT}"

if [ ${RSSI_COUNT} -gt 0 ] && [ ${SNR_COUNT} -gt 0 ]; then
    echo "  ✓ PASS: Signal data collected"
else
    echo "  ✗ WARN: Limited signal data"
fi

# Test 11: Check hop count feature
echo "Test 11: Checking hop count feature..."
HOP_COUNT=$(grep -c "hops:" "${TEST_SESSION}/gui_output.log" || echo "0")
echo "  Hop count readings: ${HOP_COUNT}"

if [ ${HOP_COUNT} -gt 0 ]; then
    echo "  ✓ PASS: Hop count tracking working"
    grep "hops:" "${TEST_SESSION}/gui_output.log" | head -3
else
    echo "  ✗ WARN: No hop count data"
fi

# Test 12: Check direct connections
echo "Test 12: Checking for direct connections..."
DIRECT_COUNT=$(grep "hops: 0" "${TEST_SESSION}/gui_output.log" | wc -l || echo "0")
echo "  Direct connections: ${DIRECT_COUNT}"

if [ ${DIRECT_COUNT} -gt 0 ]; then
    echo "  ✓ PASS: Direct connections detected"
else
    echo "  ✗ INFO: All connections are relayed"
fi

# Test 13: Verify logging subsystem
echo "Test 13: Checking JSON packet logging..."
if [ -f mesh_tracker_*.jsonl ]; then
    LATEST_LOG=$(ls -t mesh_tracker_*.jsonl | head -1)
    LOG_LINES=$(wc -l < "${LATEST_LOG}" || echo "0")
    echo "  Latest log: ${LATEST_LOG}"
    echo "  Log entries: ${LOG_LINES}"
    
    if [ ${LOG_LINES} -gt 10 ]; then
        echo "  ✓ PASS: Packet logging functional"
    else
        echo "  ✗ WARN: Limited packet logging"
    fi
else
    echo "  ✗ FAIL: No packet logs found"
fi

# Test 14: Memory/Resource check
echo "Test 14: Checking resource usage..."
if ps -p ${GUI_PID} > /dev/null 2>&1; then
    MEM_USAGE=$(ps -p ${GUI_PID} -o rss= | awk '{print $1/1024}' || echo "0")
    echo "  Memory usage: ${MEM_USAGE} MB"
    echo "  ✓ PASS: Process running stable"
else
    echo "  ✗ FAIL: Process died during testing"
fi

# Create summary report
echo ""
echo "=========================================="
echo "Generating test report..."
echo "=========================================="

cat > "${TEST_SESSION}/README.md" << EOF
# Mesh Tracker GUI Test Session

**Date**: $(date)
**Session ID**: ${TIMESTAMP}

## Test Environment
- OS: $(uname -s) $(uname -r)
- Screenshot Tool: ${SCREENSHOT_CMD}
- GUI Process: ${GUI_PID}

## Functional Test Results

### Error Detection
- Errors: ${ERROR_COUNT}
- Tracebacks: ${TRACEBACK_COUNT}

### Node Discovery
- Nodes discovered: ${NODE_COUNT}

### GPS Functionality
- GPS readings: ${GPS_COUNT}

### Signal Data
- RSSI readings: ${RSSI_COUNT}
- SNR readings: ${SNR_COUNT}

### Hop Count
- Hop count readings: ${HOP_COUNT}
- Direct connections: ${DIRECT_COUNT}

### Logging
- JSON log entries: ${LOG_LINES:-0}

### Resource Usage
- Memory usage: ${MEM_USAGE:-N/A} MB

## Screenshots

EOF

# Add screenshots to report
if [ -f "${TEST_SESSION}/manifest.txt" ]; then
    while IFS='|' read -r name description filename; do
        cat >> "${TEST_SESSION}/README.md" << EOF
### ${name}
**Description**: ${description}

![${name}]($(basename ${filename}))

EOF
    done < "${TEST_SESSION}/manifest.txt"
fi

# Add log excerpt
cat >> "${TEST_SESSION}/README.md" << EOF

## GUI Output Log (last 50 lines)

\`\`\`
$(tail -50 "${TEST_SESSION}/gui_output.log")
\`\`\`

## Test Completion

Test session completed at: $(date)

EOF

# Cleanup: Kill the GUI
echo ""
echo "Stopping GUI..."
kill ${GUI_PID} 2>/dev/null || true
sleep 2
kill -9 ${GUI_PID} 2>/dev/null || true

echo ""
echo "=========================================="
echo "Test Complete!"
echo "=========================================="
echo ""
echo "Results saved to: ${TEST_SESSION}"
echo ""
echo "Screenshots taken:"
ls -lh "${TEST_SESSION}"/*.png 2>/dev/null || echo "  No screenshots captured"
echo ""
echo "View report: ${TEST_SESSION}/README.md"
echo "View logs: ${TEST_SESSION}/gui_output.log"
echo ""
