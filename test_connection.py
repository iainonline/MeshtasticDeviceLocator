#!/usr/bin/env python3
"""Test Meshtastic connection"""

import sys
import time

print("Testing Meshtastic Device Connection...")
print("=" * 60)

# Test 1: Check serial port
print("\n1. Checking serial port...")
try:
    import serial
    s = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    print("   ✓ /dev/ttyUSB0 is accessible")
    s.close()
except Exception as e:
    print(f"   ✗ Cannot access serial port: {e}")
    sys.exit(1)

# Test 2: Check meshtastic library
print("\n2. Checking meshtastic library...")
try:
    import meshtastic
    import meshtastic.serial_interface
    version = getattr(meshtastic, '__version__', 'unknown')
    print(f"   ✓ Meshtastic library loaded (version: {version})")
except Exception as e:
    print(f"   ✗ Cannot import meshtastic: {e}")
    sys.exit(1)

# Test 3: Try to connect
print("\n3. Attempting to connect to Meshtastic device...")
print("   This may take 10-15 seconds...")
interface = None
try:
    interface = meshtastic.serial_interface.SerialInterface('/dev/ttyUSB0')
    print("   ✓ Connection established!")
    
    # Wait for nodeDB to populate
    print("\n4. Waiting for node database...")
    time.sleep(5)
    
    # Check if we got node info
    if hasattr(interface, 'nodes'):
        print(f"   ✓ NodeDB loaded: {len(interface.nodes)} nodes")
        
        # Show first few nodes
        if len(interface.nodes) > 0:
            print("\n5. Sample nodes:")
            for i, (node_id, node_info) in enumerate(list(interface.nodes.items())[:5]):
                name = "Unknown"
                if hasattr(node_info, 'user') and node_info.user:
                    if hasattr(node_info.user, 'longName'):
                        name = node_info.user.longName
                print(f"   - {node_id}: {name}")
    else:
        print("   ! No nodeDB found (this is unusual)")
    
    # Get local node info
    if hasattr(interface, 'myInfo'):
        my_node_num = interface.myInfo.my_node_num
        my_node_id = f'!{my_node_num:08x}'
        print(f"\n6. Local node: {my_node_id}")
    
    print("\n" + "=" * 60)
    print("SUCCESS: Meshtastic device is working!")
    print("=" * 60)
    
    # Keep connection open to test for incoming packets
    print("\nListening for packets for 10 seconds...")
    print("(Press Ctrl+C to exit early)\n")
    
    packet_count = [0]  # Use list to allow modification in nested function
    def on_receive(packet, iface):
        packet_count[0] += 1
        from_id = packet.get('fromId', packet.get('from', 'unknown'))
        print(f"   [{packet_count[0]}] Packet from: {from_id}")
    
    interface.on_receive = on_receive
    
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        pass
    
    if packet_count[0] > 0:
        print(f"\n✓ Received {packet_count[0]} packets - mesh network is active!")
    else:
        print("\n! No packets received in 10 seconds")
        print("  This is normal if the mesh is quiet right now")
    
except Exception as e:
    print(f"   ✗ Connection failed: {e}")
    print(f"\nError type: {type(e).__name__}")
    import traceback
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)
finally:
    if interface:
        try:
            interface.close()
            print("\nConnection closed.")
        except:
            pass
