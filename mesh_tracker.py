#!/usr/bin/env python3
"""
Meshtastic Node Tracker with GPS
Terminal GUI dashboard for tracking mesh nodes with GPS-based direction finding
"""

import sys
import socket
import json
import time
import math
import threading
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich import box
import meshtastic
import meshtastic.serial_interface


class GPSData:
    """Store current GPS position"""
    def __init__(self):
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.altitude: Optional[float] = None
        self.speed: Optional[float] = None
        self.time: Optional[str] = None
        self.satellites: Optional[int] = None
        self.fix: bool = False
        
    def update_from_nmea(self, data: dict):
        """Update GPS data from parsed NMEA"""
        if 'latitude' in data and data['latitude'] != 'n/a':
            try:
                self.latitude = float(data['latitude'])
            except (ValueError, TypeError):
                pass
                
        if 'longitude' in data and data['longitude'] != 'n/a':
            try:
                self.longitude = float(data['longitude'])
            except (ValueError, TypeError):
                pass
                
        if 'altitude' in data and data['altitude'] != 'n/a':
            try:
                # Store altitude in feet (convert from meters)
                self.altitude = float(data['altitude']) * 3.28084
            except (ValueError, TypeError):
                pass
                
        if 'satellites' in data and data['satellites'] != 'n/a':
            try:
                self.satellites = int(data['satellites'])
            except (ValueError, TypeError):
                pass
        
        if 'time' in data:
            self.time = data['time']
            
        # Consider fix valid if we have both lat and lon
        self.fix = (self.latitude is not None and 
                   self.longitude is not None)


class MeshNode:
    """Store information about a mesh node"""
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.short_name: str = "Unknown"
        self.long_name: str = "Unknown"
        self.last_seen: float = time.time()
        self.rssi: Optional[int] = None
        self.snr: Optional[float] = None
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.altitude: Optional[float] = None
        self.battery: Optional[int] = None
        self.packet_count: int = 0
        
    def update(self, packet: dict):
        """Update node information from packet"""
        self.last_seen = time.time()
        self.packet_count += 1
        
        if 'fromId' in packet:
            self.node_id = packet['fromId']
            
        if 'from' in packet and hasattr(packet['from'], 'user'):
            user = packet['from'].user
            if hasattr(user, 'shortName'):
                self.short_name = user.shortName
            if hasattr(user, 'longName'):
                self.long_name = user.longName


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two GPS coordinates using Haversine formula
    Returns distance in meters
    """
    R = 6371000  # Earth's radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(delta_lambda / 2) ** 2)
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate bearing from point 1 to point 2
    Returns bearing in degrees (0-360)
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = (math.cos(phi1) * math.sin(phi2) -
         math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda))
    
    theta = math.atan2(y, x)
    bearing = (math.degrees(theta) + 360) % 360
    
    return bearing


def bearing_to_compass(bearing: float) -> str:
    """Convert bearing in degrees to compass direction"""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    index = round(bearing / 22.5) % 16
    return directions[index]


def format_distance(meters: float) -> str:
    """Format distance in human-readable form"""
    if meters < 1000:
        return f"{meters:.1f}m"
    else:
        return f"{meters/1000:.2f}km"


class MeshTracker:
    """Main application for tracking mesh nodes"""
    
    def __init__(self, gps_port: int = 2947, meshtastic_port: Optional[str] = None):
        self.console = Console()
        self.gps_port = gps_port
        self.meshtastic_port = meshtastic_port
        
        # Data storage
        self.gps_data = GPSData()
        self.nodes: Dict[str, MeshNode] = {}
        self.selected_node: Optional[str] = None
        self.mode = "list"  # "list" or "track"
        
        # Logging
        self.log_file = f"mesh_tracker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        
        # Threading
        self.running = False
        self.gps_thread = None
        self.mesh_thread = None
        
        # UDP socket for GPS
        self.gps_socket = None
        
        # Meshtastic interface
        self.mesh_interface = None
        
    def start_gps_receiver(self):
        """Start UDP GPS receiver thread"""
        def gps_worker():
            try:
                self.gps_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.gps_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.gps_socket.bind(('0.0.0.0', self.gps_port))
                self.gps_socket.settimeout(1.0)
                
                while self.running:
                    try:
                        data, addr = self.gps_socket.recvfrom(4096)
                        message = data.decode('utf-8', errors='ignore').strip()
                        
                        # Parse NMEA sentences
                        for line in message.split('\n'):
                            if line.startswith('$'):
                                parsed = self.parse_nmea(line)
                                if parsed:
                                    self.gps_data.update_from_nmea(parsed)
                                    self.log_data('gps', parsed)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        pass
                        
            except Exception as e:
                self.console.print(f"[red]GPS receiver error: {e}[/red]")
            finally:
                if self.gps_socket:
                    self.gps_socket.close()
        
        self.gps_thread = threading.Thread(target=gps_worker, daemon=True)
        self.gps_thread.start()
    
    def parse_nmea(self, sentence: str) -> Optional[dict]:
        """Parse NMEA sentence"""
        try:
            if not sentence.startswith('$'):
                return None
            
            parts = sentence.split(',')
            sentence_type = parts[0]
            data = {'raw': sentence, 'type': sentence_type, 'timestamp': datetime.now().isoformat()}
            
            # Parse GPGGA (Fix information)
            if 'GGA' in sentence_type and len(parts) >= 10:
                data['time'] = parts[1]
                data['latitude'] = self.parse_coordinate(parts[2], parts[3])
                data['longitude'] = self.parse_coordinate(parts[4], parts[5])
                data['fix_quality'] = parts[6]
                data['satellites'] = parts[7]
                data['altitude'] = parts[9] if len(parts) > 9 else 'n/a'
            
            # Parse GPRMC (Recommended minimum)
            elif 'RMC' in sentence_type and len(parts) >= 8:
                data['time'] = parts[1]
                data['status'] = parts[2]
                data['latitude'] = self.parse_coordinate(parts[3], parts[4])
                data['longitude'] = self.parse_coordinate(parts[5], parts[6])
                data['speed'] = parts[7]
                data['track'] = parts[8] if len(parts) > 8 else 'n/a'
            
            return data
        except Exception:
            return None
    
    def parse_coordinate(self, coord: str, direction: str) -> str:
        """Convert NMEA coordinate to decimal degrees"""
        try:
            if not coord or coord == '':
                return 'n/a'
            
            if '.' in coord:
                dot_pos = coord.index('.')
                if dot_pos >= 4:  # Longitude
                    degrees = float(coord[:dot_pos-2])
                    minutes = float(coord[dot_pos-2:])
                else:  # Latitude
                    degrees = float(coord[:dot_pos-2])
                    minutes = float(coord[dot_pos-2:])
                
                decimal = degrees + (minutes / 60.0)
                
                if direction in ['S', 'W']:
                    decimal = -decimal
                
                return str(decimal)
        except Exception:
            pass
        
        return 'n/a'
    
    def start_meshtastic_receiver(self):
        """Start Meshtastic receiver thread"""
        def mesh_worker():
            try:
                from pubsub import pub
                
                # Set up packet callback using pubsub
                def on_receive(packet, interface):
                    try:
                        self.handle_mesh_packet(packet)
                    except Exception as e:
                        pass
                
                def on_connection(interface, topic=pub.AUTO_TOPIC):
                    # Connection established
                    pass
                
                # Subscribe to mesh packets
                pub.subscribe(on_receive, "meshtastic.receive")
                pub.subscribe(on_connection, "meshtastic.connection.established")
                
                # Connect to Meshtastic device
                if self.meshtastic_port:
                    self.mesh_interface = meshtastic.serial_interface.SerialInterface(self.meshtastic_port)
                else:
                    self.mesh_interface = meshtastic.serial_interface.SerialInterface()
                
                # Also get existing nodes from nodeDB
                if self.mesh_interface and hasattr(self.mesh_interface, 'nodes'):
                    for node_id, node_info in self.mesh_interface.nodes.items():
                        try:
                            # Create packet for existing nodes with proper user info
                            fake_packet = {
                                'from': node_id,
                                'fromId': node_id,
                                'decoded': {}
                            }
                            
                            # Extract user info
                            if hasattr(node_info, 'user') and node_info.user:
                                user_dict = {}
                                if hasattr(node_info['user'], 'shortName'):
                                    user_dict['shortName'] = node_info['user'].get('shortName', 'Unknown')
                                elif 'shortName' in node_info['user']:
                                    user_dict['shortName'] = node_info['user']['shortName']
                                    
                                if hasattr(node_info['user'], 'longName'):
                                    user_dict['longName'] = node_info['user'].get('longName', 'Unknown')
                                elif 'longName' in node_info['user']:
                                    user_dict['longName'] = node_info['user']['longName']
                                    
                                fake_packet['user'] = user_dict
                            
                            # Extract position
                            if hasattr(node_info, 'position') and node_info.get('position'):
                                pos = node_info['position']
                                lat = pos.get('latitudeI', 0)
                                lon = pos.get('longitudeI', 0)
                                if lat != 0 and lon != 0:
                                    fake_packet['decoded']['position'] = {
                                        'latitude': lat / 1e7,
                                        'longitude': lon / 1e7,
                                        'altitude': pos.get('altitude', 0)
                                    }
                            
                            self.handle_mesh_packet(fake_packet)
                        except Exception:
                            pass
                
                # Keep thread alive
                while self.running:
                    time.sleep(1)
                    
            except Exception as e:
                # Silently continue if no Meshtastic device - user may be testing GPS only
                pass
            finally:
                if self.mesh_interface:
                    try:
                        self.mesh_interface.close()
                    except:
                        pass
        
        self.mesh_thread = threading.Thread(target=mesh_worker, daemon=True)
        self.mesh_thread.start()
    
    def handle_mesh_packet(self, packet: dict):
        """Handle incoming Meshtastic packet"""
        try:
            # Extract node ID
            node_id = None
            if 'fromId' in packet:
                node_id = packet['fromId']
            elif 'from' in packet:
                node_id = str(packet['from']) if not isinstance(packet['from'], str) else packet['from']
            
            if not node_id:
                return
            
            # Update or create node
            if node_id not in self.nodes:
                self.nodes[node_id] = MeshNode(node_id)
            
            node = self.nodes[node_id]
            node.last_seen = time.time()
            node.packet_count += 1
            
            # Extract user info if available
            if 'user' in packet:
                user = packet['user']
                if isinstance(user, dict):
                    if 'shortName' in user:
                        node.short_name = user['shortName']
                    if 'longName' in user:
                        node.long_name = user['longName']
                elif hasattr(user, 'shortName'):
                    node.short_name = user.shortName
                if hasattr(user, 'longName'):
                    node.long_name = user.longName
            
            # Extract position if available
            if 'decoded' in packet and 'position' in packet['decoded']:
                pos = packet['decoded']['position']
                if isinstance(pos, dict):
                    if 'latitude' in pos and pos['latitude'] != 0:
                        node.latitude = pos['latitude']
                    if 'longitude' in pos and pos['longitude'] != 0:
                        node.longitude = pos['longitude']
                    if 'altitude' in pos:
                        node.altitude = pos['altitude']
            
            # Extract signal info
            if 'rxRssi' in packet:
                node.rssi = packet['rxRssi']
            if 'rxSnr' in packet:
                node.snr = packet['rxSnr']
            
            # Log packet
            self.log_data('mesh', packet)
            
        except Exception:
            pass
    
    def log_data(self, data_type: str, data: dict):
        """Log data to file for ML analysis"""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'type': data_type,
                'data': data,
                'gps_position': {
                    'latitude': self.gps_data.latitude,
                    'longitude': self.gps_data.longitude,
                    'altitude': self.gps_data.altitude,
                } if self.gps_data.fix else None
            }
            
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass
    
    def generate_node_list_view(self) -> Layout:
        """Generate the node list view"""
        layout = Layout()
        
        # Header
        header = Panel(
            Text("🛰️  MESHTASTIC NODE TRACKER", justify="center", style="bold cyan"),
            box=box.DOUBLE
        )
        
        # GPS Status
        gps_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        gps_table.add_column("Key", style="cyan")
        gps_table.add_column("Value", style="white")
        
        if self.gps_data.fix:
            gps_table.add_row("GPS", f"✓ FIX ({self.gps_data.satellites or 0} sats)")
            gps_table.add_row("Position", f"{self.gps_data.latitude:.6f}, {self.gps_data.longitude:.6f}")
            if self.gps_data.altitude:
                gps_table.add_row("Altitude", f"{self.gps_data.altitude:.1f}ft")
        else:
            gps_table.add_row("GPS", "✗ NO FIX")
        
        gps_panel = Panel(gps_table, title="GPS Status", border_style="green")
        
        # Node List
        node_table = Table(show_header=True, box=box.SIMPLE_HEAD, padding=(0, 1))
        node_table.add_column("#", style="cyan", width=3)
        node_table.add_column("Node ID", style="yellow", width=12)
        node_table.add_column("Name", style="white", width=20)
        node_table.add_column("Last Seen", style="white", width=10)
        node_table.add_column("Packets", style="white", width=8)
        node_table.add_column("RSSI", style="white", width=6)
        
        sorted_nodes = sorted(self.nodes.values(), key=lambda n: n.last_seen, reverse=True)
        
        for idx, node in enumerate(sorted_nodes[:20], 1):
            age = int(time.time() - node.last_seen)
            age_str = f"{age}s" if age < 60 else f"{age//60}m"
            rssi_str = f"{node.rssi}" if node.rssi else "N/A"
            
            node_table.add_row(
                str(idx),
                node.node_id[:12],
                node.short_name[:20],
                age_str,
                str(node.packet_count),
                rssi_str
            )
        
        if not sorted_nodes:
            node_table.add_row("", "No nodes detected yet...", "", "", "", "")
        
        node_panel = Panel(node_table, title=f"Detected Nodes ({len(self.nodes)})", border_style="blue")
        
        # Instructions
        instructions = Text()
        instructions.append("Press ", style="white")
        instructions.append("1-9", style="bold yellow")
        instructions.append(" to track node  |  ", style="white")
        instructions.append("Q", style="bold yellow")
        instructions.append(" to quit", style="white")
        
        instr_panel = Panel(instructions, border_style="dim")
        
        # Combine
        layout.split_column(
            Layout(header, size=3),
            Layout(gps_panel, size=7),
            Layout(node_panel),
            Layout(instr_panel, size=3)
        )
        
        return layout
    
    def generate_tracking_view(self) -> Layout:
        """Generate the node tracking view"""
        layout = Layout()
        
        if not self.selected_node or self.selected_node not in self.nodes:
            return layout
        
        node = self.nodes[self.selected_node]
        
        # Header
        header = Panel(
            Text(f"📡 TRACKING: {node.short_name} ({node.node_id[:12]})", justify="center", style="bold green"),
            box=box.DOUBLE
        )
        
        # Calculate distance and bearing if we have positions
        distance = None
        bearing = None
        compass = None
        
        if (self.gps_data.fix and 
            node.latitude is not None and 
            node.longitude is not None):
            distance = calculate_distance(
                self.gps_data.latitude,
                self.gps_data.longitude,
                node.latitude,
                node.longitude
            )
            bearing = calculate_bearing(
                self.gps_data.latitude,
                self.gps_data.longitude,
                node.latitude,
                node.longitude
            )
            compass = bearing_to_compass(bearing)
        
        # Main info panel
        info_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        info_table.add_column("Key", style="cyan", width=20)
        info_table.add_column("Value", style="white bold", width=30)
        
        if distance is not None:
            info_table.add_row("DISTANCE", format_distance(distance))
        else:
            info_table.add_row("DISTANCE", "Unknown - No position data")
        
        if bearing is not None and compass is not None:
            info_table.add_row("BEARING", f"{bearing:.1f}° ({compass})")
            # Create compass visual
            compass_visual = self.create_compass_visual(bearing)
            info_table.add_row("DIRECTION", compass_visual)
        else:
            info_table.add_row("BEARING", "Unknown - No position data")
        
        info_panel = Panel(info_table, title="Navigation", border_style="green", box=box.DOUBLE)
        
        # Node details
        detail_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        detail_table.add_column("Key", style="cyan")
        detail_table.add_column("Value", style="white")
        
        age = int(time.time() - node.last_seen)
        age_str = f"{age}s ago" if age < 60 else f"{age//60}m ago"
        
        detail_table.add_row("Last Seen", age_str)
        detail_table.add_row("Packets Received", str(node.packet_count))
        if node.rssi:
            detail_table.add_row("RSSI", f"{node.rssi} dBm")
        if node.snr:
            detail_table.add_row("SNR", f"{node.snr:.1f} dB")
        if node.latitude and node.longitude:
            detail_table.add_row("Node Position", f"{node.latitude:.6f}, {node.longitude:.6f}")
        
        detail_panel = Panel(detail_table, title="Node Details", border_style="blue")
        
        # Your GPS
        gps_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        gps_table.add_column("Key", style="cyan")
        gps_table.add_column("Value", style="white")
        
        if self.gps_data.fix:
            gps_table.add_row("Your Position", f"{self.gps_data.latitude:.6f}, {self.gps_data.longitude:.6f}")
            gps_table.add_row("Satellites", str(self.gps_data.satellites or 0))
            if self.gps_data.altitude:
                gps_table.add_row("Altitude", f"{self.gps_data.altitude:.1f}ft")
        else:
            gps_table.add_row("Status", "⚠️  NO GPS FIX")
        
        gps_panel = Panel(gps_table, title="Your GPS", border_style="yellow")
        
        # Instructions
        instructions = Text()
        instructions.append("Press ", style="white")
        instructions.append("B", style="bold yellow")
        instructions.append(" to go back  |  ", style="white")
        instructions.append("Q", style="bold yellow")
        instructions.append(" to quit", style="white")
        
        instr_panel = Panel(instructions, border_style="dim")
        
        # Combine
        layout.split_column(
            Layout(header, size=3),
            Layout(info_panel, size=10),
            Layout(detail_panel, size=10),
            Layout(gps_panel, size=8),
            Layout(instr_panel, size=3)
        )
        
        return layout
    
    def create_compass_visual(self, bearing: float) -> str:
        """Create ASCII compass visual pointing to bearing"""
        # Simplified compass arrow
        arrows = ['↑', '↗', '→', '↘', '↓', '↙', '←', '↖']
        index = round(bearing / 45) % 8
        arrow = arrows[index]
        return f"{arrow} {arrow} {arrow}"
    
    def run(self):
        """Run the main application"""
        try:
            self.running = True
            
            # Start background threads
            self.console.print("[cyan]Starting GPS receiver...[/cyan]")
            self.start_gps_receiver()
            
            self.console.print("[cyan]Starting Meshtastic receiver...[/cyan]")
            self.start_meshtastic_receiver()
            
            time.sleep(2)  # Give threads time to start
            
            # Main display loop
            with Live(self.generate_node_list_view(), refresh_per_second=2, console=self.console) as live:
                while self.running:
                    try:
                        if self.mode == "list":
                            live.update(self.generate_node_list_view())
                        elif self.mode == "track":
                            live.update(self.generate_tracking_view())
                        
                        time.sleep(0.5)
                        
                    except KeyboardInterrupt:
                        break
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
        finally:
            self.running = False
            self.console.print("\n[yellow]Shutting down...[/yellow]")
            if self.gps_socket:
                self.gps_socket.close()
            if self.mesh_interface:
                self.mesh_interface.close()
            self.console.print(f"[green]Data logged to: {self.log_file}[/green]")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Meshtastic Node Tracker with GPS Direction Finding'
    )
    parser.add_argument(
        '--gps-port',
        type=int,
        default=2947,
        help='UDP port for GPS data (default: 2947)'
    )
    parser.add_argument(
        '--meshtastic-port',
        type=str,
        help='Serial port for Meshtastic device (auto-detect if not specified)'
    )
    
    args = parser.parse_args()
    
    console = Console()
    console.clear()
    
    tracker = MeshTracker(gps_port=args.gps_port, meshtastic_port=args.meshtastic_port)
    
    try:
        tracker.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
