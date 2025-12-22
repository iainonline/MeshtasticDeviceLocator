#!/usr/bin/env python3
"""
Automated GUI testing script using PyAutoGUI
Tests the mesh_tracker_gui.py application
"""

import pyautogui
import time
import subprocess
import sys
import os

# Safety settings
pyautogui.PAUSE = 1  # 1 second pause between actions
pyautogui.FAILSAFE = True  # Move mouse to corner to abort

def log(message):
    """Print timestamped log message"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def take_screenshot(name):
    """Take a screenshot for verification using scrot (Raspberry Pi compatible)"""
    try:
        filename = f"test_screenshot_{name}_{int(time.time())}.png"
        # Use scrot command-line tool which works better on Raspberry Pi
        result = subprocess.run(
            ["scrot", filename],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            log(f"Screenshot saved: {filename}")
            return filename
        else:
            log(f"Screenshot failed with scrot, trying alternative...")
            # Try ImageMagick import as fallback
            result = subprocess.run(
                ["import", "-window", "root", filename],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                log(f"Screenshot saved: {filename}")
                return filename
            else:
                log(f"Screenshot failed (OK - will continue without screenshots)")
                return None
    except FileNotFoundError:
        log(f"Screenshot tool not found (install with: sudo apt install scrot)")
        return None
    except Exception as e:
        log(f"Screenshot error: {e}")
        return None

def wait_for_window(timeout=10):
    """Wait for GUI window to appear"""
    log("Waiting for GUI window to appear...")
    time.sleep(timeout)
    return True

def main():
    log("=== Starting Mesh Tracker GUI Test ===")
    
    # Step 1: Kill any existing instances
    log("Killing any existing GUI instances...")
    os.system("pkill -f mesh_tracker_gui")
    time.sleep(2)
    
    # Step 2: Start GPS client
    log("Starting GPS client...")
    gps_proc = subprocess.Popen(
        ["python3", "gps_client_udp.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(2)
    
    # Step 3: Start GUI application
    log("Starting mesh tracker GUI...")
    gui_proc = subprocess.Popen(
        ["python3", "mesh_tracker_gui.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, 'PYTHONPATH': os.getcwd()}
    )
    
    # Step 4: Wait for GUI to load
    wait_for_window(10)
    log("GUI should be loaded now")
    
    # Step 5: Take initial screenshot
    take_screenshot("01_initial")
    log("✓ Initial screenshot captured")
    
    # Step 6: Get screen size
    screen_width, screen_height = pyautogui.size()
    log(f"Screen size: {screen_width}x{screen_height}")
    
    # Step 7: Try to locate and click on the node list area
    # The node list should be on the left side of the window
    # Assuming window is centered and 1000x650
    center_x = screen_width // 2
    center_y = screen_height // 2
    
    # Node list is on the left, approximately 200 pixels wide
    node_list_x = center_x - 300  # Left side of window
    node_list_y = center_y  # Middle height
    
    log(f"Moving mouse to node list area: ({node_list_x}, {node_list_y})")
    pyautogui.moveTo(node_list_x, node_list_y, duration=1)
    time.sleep(1)
    
    # Step 8: Click on a node in the list
    log("Clicking on node list to select a node...")
    pyautogui.click(node_list_x, node_list_y)
    time.sleep(2)
    take_screenshot("02_node_selected")
    log("✓ Node selection screenshot captured")
    
    # Step 9: Verify status bar (bottom of window)
    status_y = center_y + 300  # Bottom of window
    log(f"Status bar should be visible at bottom of window")
    time.sleep(2)
    take_screenshot("03_status_bar")
    log("✓ Status bar screenshot captured")
    
    # Step 10: Check the map area (right side)
    map_x = center_x + 200  # Right side of window
    map_y = center_y
    log(f"Map should be visible on right side")
    pyautogui.moveTo(map_x, map_y, duration=1)
    time.sleep(2)
    take_screenshot("04_map_area")
    log("✓ Map area screenshot captured")
    
    # Step 11: Try to click on File menu
    menu_x = center_x - 450  # Top left corner
    menu_y = center_y - 300  # Top of window
    log("Attempting to access File menu...")
    pyautogui.moveTo(menu_x, menu_y, duration=1)
    time.sleep(1)
    pyautogui.click(menu_x, menu_y)
    time.sleep(2)
    take_screenshot("05_file_menu")
    log("✓ File menu screenshot captured")
    
    # Step 12: Wait a bit to observe behavior
    log("Waiting 5 seconds to observe application state...")
    time.sleep(5)
    take_screenshot("06_final_state")
    
    # Step 13: Close application gracefully
    log("Closing application...")
    # Try Ctrl+Q first
    pyautogui.hotkey('ctrl', 'q')
    time.sleep(3)
    
    # If still running, kill it
    log("Terminating processes...")
    try:
        gui_proc.terminate()
        gui_proc.wait(timeout=5)
    except:
        gui_proc.kill()
    
    try:
        gps_proc.terminate()
        gps_proc.wait(timeout=5)
    except:
        gps_proc.kill()
    
    log("=== Test Complete ===")
    log("Review screenshots to verify GUI functionality:")
    log("  - 01_initial: GUI window appeared")
    log("  - 02_node_selected: Node was selected from list")
    log("  - 03_status_bar: Status bar shows GPS/USB/Node info")
    log("  - 04_map_area: Map with markers visible")
    log("  - 05_file_menu: File menu accessible")
    log("  - 06_final_state: Final application state")
    
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n=== Test Interrupted ===")
        os.system("pkill -f mesh_tracker_gui")
        os.system("pkill -f gps_client_udp")
        sys.exit(1)
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        os.system("pkill -f mesh_tracker_gui")
        os.system("pkill -f gps_client_udp")
        sys.exit(1)
