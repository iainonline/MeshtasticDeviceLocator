#!/usr/bin/env python3
"""
GPS Data Reader for Raspberry Pi 5 (UDP version)
Receives GPS data from GPSd Forwarder on Android phone over WiFi LAN using UDP
"""

import sys
import socket
import json
import time
from datetime import datetime


class GPSReaderUDP:
    def __init__(self, host='192.168.4.62', port=2947):
        """
        Initialize GPS Reader for UDP
        
        Args:
            host: IP address of your phone running GPSd Forwarder
            port: GPSd port (default: 2947)
        """
        self.host = host
        self.port = port
        self.sock = None
        
    def connect(self):
        """Create UDP socket"""
        try:
            # Get this device's IP address
            import subprocess
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            pi_ip = result.stdout.strip().split()[0] if result.stdout else 'unknown'
            
            print("=" * 70)
            print("📡 GPS RECEIVER READY")
            print("=" * 70)
            print(f"\n🔧 Please configure GPSd Forwarder on your Android phone:")
            print(f"   • Server IP: {pi_ip}")
            print(f"   • Port: {self.port}")
            print(f"   • Protocol: UDP")
            print(f"   • Then start the service\n")
            print("=" * 70)
            print(f"Listening on port {self.port}...")
            print(f"Waiting for GPS data...\n")
            
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Bind to all interfaces to receive UDP packets
            self.sock.bind(('0.0.0.0', self.port))
            self.sock.settimeout(5.0)  # 5 second timeout
            return True
        except Exception as e:
            print(f"Setup failed: {e}")
            return False
    
    def parse_nmea(self, sentence):
        """Parse NMEA sentence"""
        try:
            if not sentence.startswith('$'):
                return None
            
            parts = sentence.split(',')
            sentence_type = parts[0]
            
            data = {'raw': sentence, 'type': sentence_type}
            
            # Parse GPGGA (Fix information)
            if 'GGA' in sentence_type:
                if len(parts) >= 10:
                    data['time'] = parts[1]
                    data['latitude'] = self.parse_coordinate(parts[2], parts[3])
                    data['longitude'] = self.parse_coordinate(parts[4], parts[5])
                    data['fix_quality'] = parts[6]
                    data['satellites'] = parts[7]
                    data['altitude'] = parts[9] if len(parts) > 9 else 'n/a'
            
            # Parse GPRMC (Recommended minimum)
            elif 'RMC' in sentence_type:
                if len(parts) >= 8:
                    data['time'] = parts[1]
                    data['status'] = parts[2]  # A=active, V=void
                    data['latitude'] = self.parse_coordinate(parts[3], parts[4])
                    data['longitude'] = self.parse_coordinate(parts[5], parts[6])
                    data['speed'] = parts[7]  # knots
                    data['track'] = parts[8] if len(parts) > 8 else 'n/a'
                    data['date'] = parts[9] if len(parts) > 9 else 'n/a'
            
            return data
        except Exception as e:
            return {'error': str(e), 'raw': sentence}
    
    def parse_coordinate(self, coord, direction):
        """Convert NMEA coordinate to decimal degrees"""
        try:
            if not coord or coord == '':
                return 'n/a'
            
            # NMEA format: DDMM.MMMM or DDDMM.MMMM
            if len(coord) > 0:
                if '.' in coord:
                    dot_pos = coord.index('.')
                    if dot_pos >= 4:  # Longitude (DDDMM.MMMM)
                        degrees = float(coord[:dot_pos-2])
                        minutes = float(coord[dot_pos-2:])
                    else:  # Latitude (DDMM.MMMM)
                        degrees = float(coord[:dot_pos-2])
                        minutes = float(coord[dot_pos-2:])
                    
                    decimal = degrees + (minutes / 60.0)
                    
                    # Apply direction
                    if direction in ['S', 'W']:
                        decimal = -decimal
                    
                    return f"{decimal:.6f}"
            return 'n/a'
        except:
            return 'n/a'
    
    def run_continuous(self, callback=None):
        """
        Continuously receive GPS data via UDP
        
        Args:
            callback: Optional function to call with GPS data
        """
        if not self.connect():
            return
        
        print("Receiving GPS data... (Press Ctrl+C to stop)\n")
        
        last_data = {}
        packets_received = 0
        
        try:
            while True:
                try:
                    data, addr = self.sock.recvfrom(4096)
                    packets_received += 1
                    
                    # Decode the data
                    message = data.decode('utf-8', errors='ignore').strip()
                    
                    # Split into lines (might receive multiple NMEA sentences)
                    lines = message.split('\n')
                    
                    for line in lines:
                        line = line.strip()
                        if line:
                            parsed = self.parse_nmea(line)
                            if parsed:
                                # Update last_data with new information
                                last_data.update(parsed)
                                last_data['packets_received'] = packets_received
                                last_data['source_ip'] = addr[0]
                                last_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    if callback:
                        callback(last_data)
                    else:
                        self.display_data(last_data)
                        
                except socket.timeout:
                    print("Waiting for data... (check if GPSd Forwarder is sending to this device)")
                    continue
                    
        except KeyboardInterrupt:
            print("\n\nStopping GPS reader...")
        except Exception as e:
            print(f"\nError: {e}")
        finally:
            self.close()
    
    def display_data(self, gps_data):
        """Display GPS data in terminal"""
        print("\033[H\033[J")  # Clear screen
        print("=" * 70)
        print("GPS DATA FROM PHONE (via GPSd Forwarder UDP)")
        print("=" * 70)
        
        if 'source_ip' in gps_data:
            print(f"\n📡 Source: {gps_data['source_ip']}")
            print(f"   Packets received: {gps_data.get('packets_received', 0)}")
            print(f"   Last update: {gps_data.get('timestamp', 'n/a')}")
        
        # Check if we have position data
        has_position = 'latitude' in gps_data and gps_data['latitude'] != 'n/a'
        
        if has_position:
            print(f"\n✓ GPS DATA RECEIVED")
            print(f"\n📍 Position:")
            print(f"   Latitude:  {gps_data['latitude']}°")
            print(f"   Longitude: {gps_data['longitude']}°")
            
            if 'altitude' in gps_data and gps_data['altitude'] != 'n/a':
                print(f"   Altitude:  {gps_data['altitude']} m")
            
            if 'satellites' in gps_data:
                print(f"\n🛰️  Satellites: {gps_data['satellites']}")
            
            if 'time' in gps_data:
                print(f"\n⏱️  GPS Time: {gps_data['time']}")
            
            if 'speed' in gps_data and gps_data['speed'] != 'n/a':
                try:
                    # Convert knots to m/s and km/h
                    speed_knots = float(gps_data['speed'])
                    speed_ms = speed_knots * 0.514444
                    speed_kmh = speed_knots * 1.852
                    print(f"\n🚗 Speed:")
                    print(f"   {speed_ms:.2f} m/s  ({speed_kmh:.2f} km/h)")
                except:
                    print(f"\n🚗 Speed: {gps_data['speed']} knots")
            
            if 'track' in gps_data and gps_data['track'] != 'n/a':
                print(f"   Direction: {gps_data['track']}°")
            
            if 'status' in gps_data:
                status = "Active (Valid)" if gps_data['status'] == 'A' else "Void (Invalid)"
                print(f"\n📊 Status: {status}")
            
            if 'fix_quality' in gps_data:
                quality_map = {
                    '0': 'Invalid',
                    '1': 'GPS fix (SPS)',
                    '2': 'DGPS fix',
                    '3': 'PPS fix',
                    '4': 'Real Time Kinematic',
                    '5': 'Float RTK',
                    '6': 'Estimated',
                    '7': 'Manual input',
                    '8': 'Simulation'
                }
                quality = quality_map.get(gps_data['fix_quality'], f"Unknown ({gps_data['fix_quality']})")
                print(f"   Fix Quality: {quality}")
        else:
            print("\n⚠️  NO POSITION DATA YET")
            print("   Waiting for GPS fix from phone...")
            print("   Make sure:")
            print("   - GPS is enabled on your phone")
            print("   - Phone has clear view of sky")
            print("   - GPSd Forwarder is configured to send to this Pi's IP")
        
        if 'type' in gps_data:
            print(f"\n🔤 Last sentence type: {gps_data['type']}")
        
        print("\n" + "=" * 70)
        print("Press Ctrl+C to stop")
    
    def close(self):
        """Close the UDP socket"""
        try:
            if self.sock:
                self.sock.close()
            print("Connection closed.")
        except:
            pass


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Read GPS data from phone via GPSd Forwarder (UDP)'
    )
    parser.add_argument(
        '--host',
        default='192.168.4.62',
        help='IP address of phone running GPSd Forwarder (default: 192.168.4.62)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=2947,
        help='GPSd UDP port (default: 2947)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON instead of formatted display'
    )
    
    args = parser.parse_args()
    
    reader = GPSReaderUDP(host=args.host, port=args.port)
    
    if args.json:
        # JSON output mode
        def json_callback(data):
            print(json.dumps(data, indent=2))
        
        reader.run_continuous(callback=json_callback)
    else:
        # Normal display mode
        reader.run_continuous()


if __name__ == '__main__':
    main()
