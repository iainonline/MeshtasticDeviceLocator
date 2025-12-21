#!/usr/bin/env python3
"""
GPS Data Reader for Raspberry Pi 5
Connects to GPSd Forwarder on Android phone over WiFi LAN
"""

import sys
import time
import json
from gps3 import agps3


class GPSReader:
    def __init__(self, host='192.168.1.100', port=2947):
        """
        Initialize GPS Reader
        
        Args:
            host: IP address of your phone running GPSd Forwarder
            port: GPSd port (default: 2947)
        """
        self.host = host
        self.port = port
        self.gps_socket = agps3.GPSDSocket()
        self.data_stream = agps3.DataStream()
        
    def connect(self):
        """Connect to GPSd server"""
        try:
            print(f"Connecting to GPSd at {self.host}:{self.port}...")
            self.gps_socket.connect(host=self.host, port=self.port)
            self.gps_socket.watch()
            print("Connected successfully!")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    def get_gps_data(self):
        """Get current GPS data"""
        return {
            'latitude': self.data_stream.lat,
            'longitude': self.data_stream.lon,
            'altitude': self.data_stream.alt,
            'speed': self.data_stream.speed,
            'time': self.data_stream.time,
            'mode': self.data_stream.mode,
            'satellites': self.data_stream.satellites_used,
            'track': self.data_stream.track,
            'climb': self.data_stream.climb,
            'epx': self.data_stream.epx,  # Longitude error estimate
            'epy': self.data_stream.epy,  # Latitude error estimate
            'epv': self.data_stream.epv,  # Altitude error estimate
        }
    
    def is_fix_valid(self):
        """Check if GPS has a valid fix (mode 2 or 3)"""
        return self.data_stream.mode in ['2', '3']
    
    def run_continuous(self, callback=None, interval=1.0):
        """
        Continuously read GPS data
        
        Args:
            callback: Optional function to call with GPS data
            interval: Update interval in seconds
        """
        if not self.connect():
            return
        
        print("\nReading GPS data... (Press Ctrl+C to stop)\n")
        
        try:
            while True:
                new_data = self.gps_socket.next()
                if new_data:
                    self.data_stream.unpack(new_data)
                    
                    gps_data = self.get_gps_data()
                    
                    if callback:
                        callback(gps_data)
                    else:
                        self.display_data(gps_data)
                    
                    time.sleep(interval)
                    
        except KeyboardInterrupt:
            print("\n\nStopping GPS reader...")
        except Exception as e:
            print(f"\nError: {e}")
        finally:
            self.close()
    
    def display_data(self, gps_data):
        """Display GPS data in terminal"""
        print("\033[H\033[J")  # Clear screen
        print("=" * 60)
        print("GPS DATA FROM PHONE (via GPSd Forwarder)")
        print("=" * 60)
        
        mode = gps_data['mode']
        if mode == 'n/a' or mode == '0' or mode == '1':
            print("\n⚠️  NO GPS FIX - Waiting for satellite lock...")
            print(f"   Mode: {mode} (0=no fix, 1=no fix, 2=2D fix, 3=3D fix)")
        else:
            fix_type = "2D Fix" if mode == '2' else "3D Fix"
            print(f"\n✓ GPS FIX: {fix_type}")
            print(f"\n📍 Position:")
            print(f"   Latitude:  {gps_data['latitude']}")
            print(f"   Longitude: {gps_data['longitude']}")
            print(f"   Altitude:  {gps_data['altitude']} m")
            
            print(f"\n🛰️  Satellites: {gps_data['satellites']}")
            
            print(f"\n⏱️  Time: {gps_data['time']}")
            
            if gps_data['speed'] != 'n/a':
                print(f"\n🚗 Movement:")
                print(f"   Speed:     {gps_data['speed']} m/s")
                print(f"   Track:     {gps_data['track']}°")
                print(f"   Climb:     {gps_data['climb']} m/s")
            
            print(f"\n📊 Accuracy:")
            print(f"   Long err:  {gps_data['epx']} m")
            print(f"   Lat err:   {gps_data['epy']} m")
            print(f"   Alt err:   {gps_data['epv']} m")
        
        print("\n" + "=" * 60)
        print("Press Ctrl+C to stop")
    
    def close(self):
        """Close the GPS connection"""
        try:
            self.gps_socket.close()
            print("Connection closed.")
        except:
            pass


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Read GPS data from phone via GPSd Forwarder'
    )
    parser.add_argument(
        '--host',
        default='192.168.1.100',
        help='IP address of phone running GPSd Forwarder (default: 192.168.1.100)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=2947,
        help='GPSd port (default: 2947)'
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=1.0,
        help='Update interval in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON instead of formatted display'
    )
    
    args = parser.parse_args()
    
    reader = GPSReader(host=args.host, port=args.port)
    
    if args.json:
        # JSON output mode
        def json_callback(data):
            print(json.dumps(data, indent=2))
        
        reader.run_continuous(callback=json_callback, interval=args.interval)
    else:
        # Normal display mode
        reader.run_continuous(interval=args.interval)


if __name__ == '__main__':
    main()
