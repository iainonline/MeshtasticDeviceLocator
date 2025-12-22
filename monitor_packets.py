#!/usr/bin/env python3
"""
Live Meshtastic Packet Monitor
Displays all incoming packets in real-time to diagnose mesh connectivity
"""

import sys
import time
import json
from datetime import datetime

try:
    import meshtastic
    import meshtastic.serial_interface
except ImportError:
    print("ERROR: meshtastic library not found")
    print("Run: pip install meshtastic")
    sys.exit(1)

print("=" * 70)
print("MESHTASTIC LIVE PACKET MONITOR")
print("=" * 70)
print()

# Connect
print("Connecting to /dev/ttyUSB0...")
try:
    interface = meshtastic.serial_interface.SerialInterface('/dev/ttyUSB0')
    print("✓ Connected!")
    time.sleep(3)  # Wait for nodeDB
    
    if hasattr(interface, 'nodes'):
        print(f"✓ NodeDB loaded: {len(interface.nodes)} nodes")
    
    if hasattr(interface, 'myInfo'):
        my_node_num = interface.myInfo.my_node_num
        my_node_id = f'!{my_node_num:08x}'
        print(f"✓ Local node: {my_node_id}")
    
    print()
    print("=" * 70)
    print("LISTENING FOR PACKETS...")
    print("(Press Ctrl+C to exit)")
    print("=" * 70)
    print()
    
    packet_count = [0]
    start_time = time.time()
    
    def on_receive(packet, iface):
        """Handle incoming packet"""
        packet_count[0] += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Extract basic info
        from_id = packet.get('fromId', packet.get('from', 'unknown'))
        to_id = packet.get('toId', packet.get('to', 'unknown'))
        
        # Check for RSSI/SNR
        rssi = packet.get('rxRssi', packet.get('rssi', None))
        snr = packet.get('rxSnr', packet.get('snr', None))
        
        # Packet type
        decoded = packet.get('decoded', {})
        portnum = decoded.get('portnum', 'unknown')
        
        # Build info string
        info_parts = []
        if rssi is not None:
            info_parts.append(f"RSSI:{rssi}dBm")
        if snr is not None:
            info_parts.append(f"SNR:{snr}")
        info_parts.append(f"Port:{portnum}")
        
        info_str = " | ".join(info_parts)
        
        print(f"[{timestamp}] #{packet_count[0]:03d} FROM:{from_id} TO:{to_id}")
        print(f"          {info_str}")
        
        # Show decoded data
        if decoded:
            if 'position' in decoded:
                pos = decoded['position']
                lat = pos.get('latitude', pos.get('latitudeI', 0))
                lon = pos.get('longitude', pos.get('longitudeI', 0))
                if lat != 0 and lon != 0:
                    print(f"          Position: {lat}, {lon}")
            
            if 'text' in decoded:
                print(f"          Text: {decoded['text']}")
        
        print()
    
    interface.on_receive = on_receive
    
    # Monitor loop
    try:
        while True:
            time.sleep(1)
            elapsed = int(time.time() - start_time)
            if elapsed % 30 == 0 and elapsed > 0:  # Every 30 seconds
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Status: {packet_count[0]} packets received in {elapsed}s")
                print()
    
    except KeyboardInterrupt:
        print()
        print("=" * 70)
        print(f"SUMMARY: Received {packet_count[0]} packets in {int(time.time() - start_time)}s")
        print("=" * 70)
    
    finally:
        interface.close()

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
