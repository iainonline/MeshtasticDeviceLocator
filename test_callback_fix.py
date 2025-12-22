#!/usr/bin/env python3
"""Test if the fixed callback signature works"""

import sys
import time
import meshtastic.serial_interface

print("Testing fixed callback signature...")
print("=" * 60)

received_packets = []

# The CORRECT callback signature - must accept both packet and interface!
def packet_handler(packet, interface):
    received_packets.append(packet)
    from_id = packet.get('fromId', packet.get('from', 'unknown'))
    print(f"[{len(received_packets)}] Packet from: {from_id}")

print("\nConnecting to /dev/ttyUSB0...")
interface = meshtastic.serial_interface.SerialInterface('/dev/ttyUSB0')

# Register the handler using on_receive
interface.on_receive = packet_handler

print("✓ Connected!")
print(f"✓ Callback registered")
print(f"\nListening for 30 seconds...\n")

try:
    time.sleep(30)
except KeyboardInterrupt:
    pass

print(f"\n{'='*60}")
print(f"RESULT: Received {len(received_packets)} packets!")
print(f"{'='*60}")

if len(received_packets) > 0:
    print("\n✓ SUCCESS - Packets are being received!")
    print("\nSample packets:")
    for i, pkt in enumerate(received_packets[:3]):
        from_id = pkt.get('fromId', 'unknown')
        to_id = pkt.get('toId', 'unknown')
        print(f"  {i+1}. From: {from_id}, To: {to_id}")
else:
    print("\n⚠ No packets received - mesh may be quiet")

interface.close()
