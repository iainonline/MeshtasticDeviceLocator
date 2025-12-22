#!/usr/bin/env python3
"""Quick test to verify the GUI's mesh connection will now receive packets"""

import sys
import time
sys.path.insert(0, '/home/iain/MeshLocator/MeshtasticDeviceLocator')

from mesh_tracker_gui import MeshTrackerGUI
import tkinter as tk

print("Testing GUI mesh packet reception...")
print("=" * 60)

# Create minimal GUI instance
root = tk.Tk()
root.withdraw()  # Hide the window

print("\nInitializing tracker...")
gui = MeshTrackerGUI(root, gps_port=2947)

print("Connecting to Meshtastic...")
if gui.connect_meshtastic():
    print("✓ Connected successfully!")
    print(f"✓ Local node: {gui.local_node_name}")
    print(f"✓ NodeDB has {len(gui.nodes)} nodes")
    
    print("\nListening for packets for 30 seconds...")
    print("(Watching for [DEBUG] Packet received messages)\n")
    
    start_time = time.time()
    initial_count = len(gui.nodes)
    
    try:
        for i in range(30):
            root.update()  # Process Tkinter events
            time.sleep(1)
            if i % 10 == 9:
                elapsed = int(time.time() - start_time)
                print(f"[{elapsed}s] Still listening... (nodes: {len(gui.nodes)})")
    except KeyboardInterrupt:
        pass
    
    final_count = len(gui.nodes)
    new_nodes = final_count - initial_count
    
    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Initial nodes: {initial_count}")
    print(f"  Final nodes: {final_count}")
    print(f"  New/updated nodes: {new_nodes}")
    
    if new_nodes > 0:
        print(f"\n✓ SUCCESS: Received data from {new_nodes} nodes!")
    else:
        print(f"\n⚠ No new nodes - mesh may be quiet right now")
        print("  Check console for [DEBUG] Packet received messages")
    
    if gui.mesh_interface:
        gui.mesh_interface.close()
else:
    print("✗ Failed to connect")
    sys.exit(1)

root.destroy()
