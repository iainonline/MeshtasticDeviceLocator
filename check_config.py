#!/usr/bin/env python3
"""
Meshtastic Configuration Checker
Shows your radio's current settings
"""

import sys
import time

try:
    import meshtastic
    import meshtastic.serial_interface
except ImportError:
    print("ERROR: meshtastic library not found")
    sys.exit(1)

print("=" * 70)
print("MESHTASTIC CONFIGURATION CHECK")
print("=" * 70)
print()

try:
    print("Connecting...")
    interface = meshtastic.serial_interface.SerialInterface('/dev/ttyUSB0')
    time.sleep(3)
    
    print("✓ Connected\n")
    
    # Get node info
    if hasattr(interface, 'myInfo') and interface.myInfo:
        print("LOCAL NODE INFO:")
        print("-" * 40)
        my_node_num = interface.myInfo.my_node_num
        my_node_id = f'!{my_node_num:08x}'
        print(f"  Node ID: {my_node_id}")
        
        if hasattr(interface.myInfo, 'firmware_version'):
            print(f"  Firmware: {interface.myInfo.firmware_version}")
        
        print()
    
    # Get channel info
    print("CHANNEL CONFIGURATION:")
    print("-" * 40)
    
    if hasattr(interface, 'localNode') and interface.localNode:
        local = interface.localNode
        
        # Try to get channel info
        if hasattr(local, 'channels'):
            for i, ch in enumerate(local.channels):
                if hasattr(ch, 'settings') and ch.settings:
                    settings = ch.settings
                    print(f"\n  Channel {i}:")
                    if hasattr(settings, 'name') and settings.name:
                        print(f"    Name: {settings.name}")
                    if hasattr(settings, 'channel_num'):
                        print(f"    Number: {settings.channel_num}")
                    if hasattr(settings, 'modem_config'):
                        print(f"    Modem: {settings.modem_config}")
                    if hasattr(settings, 'psk'):
                        psk_hex = settings.psk.hex() if settings.psk else "default"
                        print(f"    PSK: {psk_hex[:16]}...")
        
        # Get LoRa config
        if hasattr(local, 'radioConfig') and local.radioConfig:
            print("\n  LoRa Settings:")
            radio = local.radioConfig
            if hasattr(radio, 'preferences'):
                prefs = radio.preferences
                if hasattr(prefs, 'region'):
                    print(f"    Region: {prefs.region}")
                if hasattr(prefs, 'lora_config'):
                    lora = prefs.lora_config
                    if hasattr(lora, 'bandwidth'):
                        print(f"    Bandwidth: {lora.bandwidth}")
                    if hasattr(lora, 'spread_factor'):
                        print(f"    Spread Factor: {lora.spread_factor}")
                    if hasattr(lora, 'coding_rate'):
                        print(f"    Coding Rate: {lora.coding_rate}")
    
    print()
    
    # NodeDB stats
    print("NODE DATABASE:")
    print("-" * 40)
    if hasattr(interface, 'nodes'):
        print(f"  Total nodes: {len(interface.nodes)}")
        
        # Count nodes by last heard time
        current_time = time.time()
        recent = []
        for node_id, node in interface.nodes.items():
            if hasattr(node, 'lastHeard') and node.lastHeard:
                try:
                    last_heard = node.lastHeard.ToSeconds()
                    age_minutes = (current_time - last_heard) / 60
                    if age_minutes < 60:  # Within last hour
                        recent.append((node_id, age_minutes))
                except:
                    pass
        
        if recent:
            print(f"  Nodes heard in last hour: {len(recent)}")
            print("\n  Recently active nodes:")
            for node_id, age in sorted(recent, key=lambda x: x[1])[:5]:
                print(f"    {node_id}: {int(age)} minutes ago")
        else:
            print("  ⚠ No nodes heard in the last hour")
            print("  This suggests the mesh may be quiet or you're out of range")
    
    print()
    print("=" * 70)
    
    interface.close()
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
