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
        # For position estimation
        self.estimation_samples: List[dict] = []  # Store RSSI samples with GPS positions
        self.estimated_position: Optional[Tuple[float, float]] = None
        self.estimation_log: List[str] = []  # Log of estimation process
        # For signal tracking (hotter/colder)
        self.signal_history: List[dict] = []  # Timestamped RSSI/SNR history with GPS positions
        
    def update(self, packet: dict, gps_data: Optional['GPSData'] = None):
        """Update node information from packet"""
        current_time = time.time()
        self.last_seen = current_time
        self.packet_count += 1
        
        if 'fromId' in packet:
            self.node_id = packet['fromId']
            
        if 'from' in packet and hasattr(packet['from'], 'user'):
            user = packet['from'].user
            if hasattr(user, 'shortName'):
                self.short_name = user.shortName
            if hasattr(user, 'longName'):
                self.long_name = user.longName
        
        # Record signal history with GPS position for tracking
        if self.rssi is not None:
            history_entry = {
                'timestamp': current_time,
                'rssi': self.rssi,
                'snr': self.snr,
                'latitude': gps_data.latitude if gps_data and gps_data.fix else None,
                'longitude': gps_data.longitude if gps_data and gps_data.fix else None
            }
            self.signal_history.append(history_entry)
            # Keep only last 30 minutes of history
            cutoff_time = current_time - 1800
            self.signal_history = [h for h in self.signal_history if h['timestamp'] > cutoff_time]
    
    def get_signal_trend(self, time_window: int) -> Optional[str]:
        """Get signal trend over specified time window in seconds
        Returns: 'hotter', 'colder', 'stable', or None if insufficient data
        """
        if len(self.signal_history) < 2:
            return None
        
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        # Get recent readings
        recent_readings = [h for h in self.signal_history if h['timestamp'] > cutoff_time]
        
        if len(recent_readings) < 2:
            return None
        
        # Compare average of first half vs second half
        mid_point = len(recent_readings) // 2
        first_half = recent_readings[:mid_point]
        second_half = recent_readings[mid_point:]
        
        avg_first = sum(h['rssi'] for h in first_half) / len(first_half)
        avg_second = sum(h['rssi'] for h in second_half) / len(second_half)
        
        # RSSI is negative, so higher (less negative) is better
        diff = avg_second - avg_first
        
        # Threshold for "significant" change (3 dBm)
        if diff > 3:
            return 'hotter'
        elif diff < -3:
            return 'colder'
        else:
            return 'stable'
    
    def get_signal_strength_change(self, time_window: int) -> Optional[float]:
        """Get the actual dBm change over the time window"""
        if len(self.signal_history) < 2:
            return None
        
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        recent_readings = [h for h in self.signal_history if h['timestamp'] > cutoff_time]
        
        if len(recent_readings) < 2:
            return None
        
        # Compare average of first half vs second half
        mid_point = len(recent_readings) // 2
        first_half = recent_readings[:mid_point]
        second_half = recent_readings[mid_point:]
        
        avg_first = sum(h['rssi'] for h in first_half) / len(first_half)
        avg_second = sum(h['rssi'] for h in second_half) / len(second_half)
        
        return avg_second - avg_first


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
    """Format distance in human-readable form (feet/miles)"""
    feet = meters * 3.28084
    if feet < 5280:  # Less than 1 mile
        return f"{feet:.1f}ft"
    else:
        miles = feet / 5280
        return f"{miles:.2f}mi"


class MeshTracker:
    """Main application for tracking mesh nodes"""
    
    def __init__(self, gps_port: int = 2947, meshtastic_port: Optional[str] = None, debug: bool = False):
        self.console = Console()
        self.gps_port = gps_port
        self.meshtastic_port = meshtastic_port
        self.debug = debug
        
        # Data storage
        self.gps_data = GPSData()
        self.nodes: Dict[str, MeshNode] = {}
        self.selected_node: Optional[str] = None
        self.mode = "list"  # "list" or "track"
        
        # GPS position history for stationary detection
        self.gps_history: List[dict] = []  # Store Pi5's GPS positions with timestamps
        
        # Auto-selection
        self.last_selected_file = "last_selected_node.txt"
        self.startup_time = time.time()
        self.auto_selected = False
        
        # Logging
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = f'mesh_tracker_{timestamp}.jsonl'
        self.debug_log_file = f'mesh_tracker_debug_{timestamp}.log' if debug else None
        self.screen_capture_file = f'mesh_tracker_screen_{timestamp}.txt' if debug else None
        
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
                            
                            # Extract user info - node_info is a dict
                            if 'user' in node_info and node_info['user']:
                                user_dict = {}
                                user_data = node_info['user']
                                if 'shortName' in user_data and user_data['shortName']:
                                    user_dict['shortName'] = user_data['shortName']
                                if 'longName' in user_data and user_data['longName']:
                                    user_dict['longName'] = user_data['longName']
                                    
                                if user_dict:
                                    fake_packet['user'] = user_dict
                            
                            # Extract position
                            if 'position' in node_info and node_info['position']:
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
            # Debug: Log raw packet structure
            if self.debug:
                self.debug_log(f"\n=== RAW PACKET ===")
                self.debug_log(f"Type: {type(packet)}")
                self.debug_log(f"Keys: {list(packet.keys()) if isinstance(packet, dict) else 'Not a dict'}")
                self.debug_log(f"Full packet: {packet}")
                
                # Check for various possible RSSI/SNR field names
                rssi_fields = ['rxRssi', 'rssi', 'rxrssi', 'RSSI', 'signal']
                snr_fields = ['rxSnr', 'snr', 'rxsnr', 'SNR']
                
                self.debug_log(f"\nLooking for RSSI in: {rssi_fields}")
                for field in rssi_fields:
                    if field in packet:
                        self.debug_log(f"  FOUND {field}: {packet[field]}")
                
                self.debug_log(f"\nLooking for SNR in: {snr_fields}")
                for field in snr_fields:
                    if field in packet:
                        self.debug_log(f"  FOUND {field}: {packet[field]}")
            
            # Extract node ID
            node_id = None
            if 'fromId' in packet:
                node_id = packet['fromId']
            elif 'from' in packet:
                node_id = str(packet['from']) if not isinstance(packet['from'], str) else packet['from']
            
            if not node_id:
                self.debug_log(f"No node_id found in packet")
                return
            
            self.debug_log(f"Processing packet from node: {node_id}")
            
            # Update or create node
            if node_id not in self.nodes:
                self.nodes[node_id] = MeshNode(node_id)
                self.debug_log(f"Created new node: {node_id}")
            
            node = self.nodes[node_id]
            
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
            
            # Extract signal info and collect for estimation
            # Try multiple possible field names for RSSI
            rssi_value = None
            for field in ['rxRssi', 'rssi', 'rxrssi']:
                if field in packet:
                    rssi_value = packet[field]
                    break
            
            if rssi_value is not None:
                node.rssi = rssi_value
                self.debug_log(f"Set RSSI to {rssi_value} for node {node_id}")
                # Collect RSSI sample if we have GPS fix
                if self.gps_data.fix and node.latitude is None:
                    sample = {
                        'timestamp': time.time(),
                        'rssi': rssi_value,
                        'gps_lat': self.gps_data.latitude,
                        'gps_lon': self.gps_data.longitude,
                        'snr': packet.get('rxSnr', packet.get('snr', 0))
                    }
                    node.estimation_samples.append(sample)
                    self.debug_log(f"Added estimation sample for {node_id}")
                    # Keep last 100 samples
                    if len(node.estimation_samples) > 100:
                        node.estimation_samples.pop(0)
                    
                    # Try to estimate position if we have enough samples
                    if len(node.estimation_samples) >= 3:
                        self.estimate_node_position(node)
            else:
                self.debug_log(f"WARNING: No RSSI found in packet from {node_id}")
            
            # Try multiple possible field names for SNR
            snr_value = None
            for field in ['rxSnr', 'snr', 'rxsnr']:
                if field in packet:
                    snr_value = packet[field]
                    break
            
            if snr_value is not None:
                node.snr = snr_value
                self.debug_log(f"Set SNR to {snr_value} for node {node_id}")
            
            # Update node with tracking data (includes signal history)
            node.update(packet, self.gps_data)
            
            # Debug: Check if signal history was updated
            if self.debug:
                self.debug_log(f"Node {node_id} signal history length: {len(node.signal_history)}")
                if len(node.signal_history) > 0:
                    self.debug_log(f"Latest signal history entry: {node.signal_history[-1]}")
            
            # Log packet
            self.log_data('mesh', packet)
            
        except Exception:
            pass
    
    def estimate_node_position(self, node: MeshNode):
        """Estimate node position using RSSI triangulation"""
        try:
            samples = node.estimation_samples
            if len(samples) < 3:
                return
            
            # Add log entry
            timestamp_str = datetime.now().strftime("%H:%M:%S")
            node.estimation_log.append(f"{timestamp_str} - Collected {len(samples)} RSSI samples")
            
            # Simple weighted centroid based on signal strength
            # Stronger signals (less negative RSSI) indicate closer proximity
            total_weight = 0
            weighted_lat = 0
            weighted_lon = 0
            
            for sample in samples[-10:]:  # Use last 10 samples
                # Convert RSSI to weight (stronger signal = higher weight)
                # RSSI typically ranges from -120 (weak) to -30 (strong)
                weight = 10 ** (sample['rssi'] / 20.0)  # Exponential weighting
                weighted_lat += sample['gps_lat'] * weight
                weighted_lon += sample['gps_lon'] * weight
                total_weight += weight
            
            if total_weight > 0:
                est_lat = weighted_lat / total_weight
                est_lon = weighted_lon / total_weight
                node.estimated_position = (est_lat, est_lon)
                
                node.estimation_log.append(f"{timestamp_str} - Estimated position: {est_lat:.6f}, {est_lon:.6f}")
                node.estimation_log.append(f"{timestamp_str} - Using signal strength from {len(samples[-10:])} measurements")
                node.estimation_log.append(f"{timestamp_str} - Average RSSI: {sum(s['rssi'] for s in samples[-10:]) / len(samples[-10:]):.1f} dBm")
            
            # Keep only last 5 log entries
            if len(node.estimation_log) > 5:
                node.estimation_log = node.estimation_log[-5:]
                
        except Exception:
            pass
    
    def save_last_selected_node(self):
        """Save the last selected node ID to file"""
        try:
            if self.selected_node:
                with open(self.last_selected_file, 'w') as f:
                    f.write(self.selected_node)
        except Exception:
            pass
    
    def load_last_selected_node(self) -> Optional[str]:
        """Load the last selected node ID from file"""
        try:
            import os
            if os.path.exists(self.last_selected_file):
                with open(self.last_selected_file, 'r') as f:
                    return f.read().strip()
        except Exception:
            pass
        return None
    
    def debug_log(self, message: str):
        """Log debug messages"""
        if not self.debug or not self.debug_log_file:
            return
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
            with open(self.debug_log_file, 'a') as f:
                f.write(f"[{timestamp}] {message}\n")
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
            
            # Track GPS position history for stationary detection
            if self.gps_data.fix:
                self.track_gps_position()
                
        except Exception:
            pass
    
    def track_gps_position(self):
        """Track Pi5's GPS position for stationary detection"""
        current_time = time.time()
        
        if self.gps_data.fix:
            self.gps_history.append({
                'timestamp': current_time,
                'latitude': self.gps_data.latitude,
                'longitude': self.gps_data.longitude
            })
            
            # Keep only last 5 minutes of history
            cutoff_time = current_time - 300
            self.gps_history = [h for h in self.gps_history if h['timestamp'] > cutoff_time]
    
    def is_pi_stationary(self, time_window: int = 60, max_movement_meters: float = 10.0) -> bool:
        """
        Determine if the Pi5 is stationary based on GPS history
        Returns True if Pi hasn't moved more than max_movement_meters in the time window
        """
        if len(self.gps_history) < 2:
            return False  # Not enough data
        
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        recent_positions = [h for h in self.gps_history if h['timestamp'] > cutoff_time]
        
        if len(recent_positions) < 2:
            return False
        
        # Calculate max distance moved from any point to any other point
        max_distance = 0
        for i in range(len(recent_positions)):
            for j in range(i + 1, len(recent_positions)):
                dist = calculate_distance(
                    recent_positions[i]['latitude'],
                    recent_positions[i]['longitude'],
                    recent_positions[j]['latitude'],
                    recent_positions[j]['longitude']
                )
                max_distance = max(max_distance, dist)
        
        return max_distance <= max_movement_meters
    
    def is_target_node_moving(self, node: MeshNode, time_window: int = 60) -> Optional[str]:
        """
        Determine if the target node is moving or stationary
        Returns: 'moving', 'stationary', or None if insufficient data
        """
        # Need to be tracking this node with signal history
        if len(node.signal_history) < 3:
            return None
        
        # Check if Pi5 is stationary
        if not self.is_pi_stationary(time_window):
            return None  # Can't determine if both are moving
        
        # Pi is stationary, check if signal is changing significantly
        signal_change = node.get_signal_strength_change(time_window)
        
        if signal_change is None:
            return None
        
        # If signal is changing significantly while Pi is stationary, target is moving
        if abs(signal_change) > 3.0:  # More than 3 dBm change
            return 'moving'
        else:
            return 'stationary'
    
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
            sats = self.gps_data.satellites or 0
            gps_table.add_row("GPS", f"✓ FIX ({sats} sats)")
            gps_table.add_row("Position", f"{self.gps_data.latitude:.6f}, {self.gps_data.longitude:.6f}")
            if self.gps_data.altitude:
                gps_table.add_row("Altitude", f"{self.gps_data.altitude:.1f}ft")
            # Warn about GPS accuracy
            if sats < 6:
                gps_table.add_row("⚠️  Warning", "Low satellite count - position may be inaccurate")
        else:
            gps_table.add_row("GPS", "✗ NO FIX")
            gps_table.add_row("⚠️  Warning", "No GPS fix - cannot calculate distance/bearing")
        
        gps_panel = Panel(gps_table, title="GPS Status", border_style="green")
        
        # Node List
        node_table = Table(show_header=True, box=box.SIMPLE_HEAD, padding=(0, 1))
        node_table.add_column("#", style="cyan", width=3)
        node_table.add_column("Node ID", style="yellow", width=12)
        node_table.add_column("Short Name", style="white", width=12)
        node_table.add_column("Long Name", style="dim white", width=20)
        node_table.add_column("Last", style="white", width=6)
        node_table.add_column("Pkts", style="white", width=5)
        node_table.add_column("RSSI", style="white", width=6)
        
        sorted_nodes = sorted(self.nodes.values(), key=lambda n: n.last_seen, reverse=True)
        
        for idx, node in enumerate(sorted_nodes[:20], 1):
            age = int(time.time() - node.last_seen)
            age_str = f"{age}s" if age < 60 else f"{age//60}m"
            rssi_str = f"{node.rssi}" if node.rssi else "N/A"
            
            # Truncate long name if too long
            long_name = node.long_name[:20] if len(node.long_name) <= 20 else node.long_name[:17] + "..."
            
            node_table.add_row(
                str(idx),
                node.node_id[:12],
                node.short_name[:12],
                long_name,
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
        
        # Header with both short and long names
        header_text = f"📡 TRACKING: {node.short_name}"
        if node.long_name and node.long_name != node.short_name and node.long_name != "Unknown":
            header_text += f" ({node.long_name})"
        header_text += f" [{node.node_id[:12]}]"
        header = Panel(
            Text(header_text, justify="center", style="bold green"),
            box=box.DOUBLE
        )
        
        # Calculate distance and bearing if we have positions
        distance = None
        bearing = None
        compass = None
        
        # Use GPS position if available, otherwise use estimated position
        node_lat = node.latitude
        node_lon = node.longitude
        position_type = "GPS"
        
        if node_lat is None and node.estimated_position:
            node_lat, node_lon = node.estimated_position
            position_type = "ESTIMATED"
        
        if (self.gps_data.fix and 
            node_lat is not None and 
            node_lon is not None):
            distance = calculate_distance(
                self.gps_data.latitude,
                self.gps_data.longitude,
                node_lat,
                node_lon
            )
            bearing = calculate_bearing(
                self.gps_data.latitude,
                self.gps_data.longitude,
                node_lat,
                node_lon
            )
            compass = bearing_to_compass(bearing)
        
        # Main info panel
        info_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        info_table.add_column("Key", style="cyan", width=20)
        info_table.add_column("Value", style="white bold", width=30)
        
        # Signal Tracking Panel - Show hotter/colder trends
        tracking_info = []
        
        # Get trends for different time windows
        trend_10s = node.get_signal_trend(10)
        trend_60s = node.get_signal_trend(60)
        trend_5m = node.get_signal_trend(300)
        
        change_10s = node.get_signal_strength_change(10)
        change_60s = node.get_signal_strength_change(60)
        change_5m = node.get_signal_strength_change(300)
        
        def get_trend_emoji(trend):
            if trend == 'hotter':
                return '🔥'
            elif trend == 'colder':
                return '🧊'
            elif trend == 'stable':
                return '➡️'
            else:
                return '⏳'
        
        def get_trend_style(trend):
            if trend == 'hotter':
                return 'bold green'
            elif trend == 'colder':
                return 'bold blue'
            elif trend == 'stable':
                return 'yellow'
            else:
                return 'dim white'
        
        if distance is not None:
            dist_str = format_distance(distance)
            # Show which position source was used for calculation
            if position_type == "ESTIMATED":
                info_table.add_row("DISTANCE", f"{dist_str} (using estimated location)")
            else:
                info_table.add_row("DISTANCE", f"{dist_str} (using GPS location)")
        else:
            # Show why we can't calculate distance
            reason = ""
            if not self.gps_data.fix:
                reason = "No GPS fix on Pi"
            elif node.latitude is None or node.longitude is None:
                reason = "Node has no position data"
            else:
                reason = "Unknown"
            info_table.add_row("DISTANCE", f"Unknown ({reason})")
        
        if bearing is not None and compass is not None:
            info_table.add_row("BEARING", f"{bearing:.1f}° ({compass})")
            # Create compass visual
            compass_visual = self.create_compass_visual(bearing)
            info_table.add_row("DIRECTION", compass_visual)
        else:
            info_table.add_row("BEARING", "Waiting for position data...")
        
        # Add signal tracking trends
        info_table.add_row("", "")  # Spacer
        if trend_10s:
            change_str = f"{change_10s:+.1f} dBm" if change_10s else ""
            info_table.add_row(f"Last 10 seconds {get_trend_emoji(trend_10s)}", 
                             Text(f"{trend_10s.upper()} {change_str}", style=get_trend_style(trend_10s)))
        
        if trend_60s:
            change_str = f"{change_60s:+.1f} dBm" if change_60s else ""
            info_table.add_row(f"Last 60 seconds {get_trend_emoji(trend_60s)}", 
                             Text(f"{trend_60s.upper()} {change_str}", style=get_trend_style(trend_60s)))
        
        if trend_5m:
            change_str = f"{change_5m:+.1f} dBm" if change_5m else ""
            info_table.add_row(f"Last 5 minutes {get_trend_emoji(trend_5m)}", 
                             Text(f"{trend_5m.upper()} {change_str}", style=get_trend_style(trend_5m)))
        
        if not trend_10s and not trend_60s and not trend_5m:
            info_table.add_row("Signal Trend", Text("Collecting data...", style="dim white"))
        
        # Add target node movement status
        info_table.add_row("", "")  # Spacer
        node_movement = self.is_target_node_moving(node, 60)
        
        if node_movement == 'moving':
            info_table.add_row("Target Node Status", 
                             Text("🚶 MOVING (signal changing, Pi stationary)", style="bold yellow"))
        elif node_movement == 'stationary':
            info_table.add_row("Target Node Status", 
                             Text("🏠 STATIONARY (stable signal, Pi stationary)", style="bold cyan"))
        else:
            # Check if Pi itself is stationary
            if self.is_pi_stationary(60):
                info_table.add_row("Your Status", Text("📍 You are stationary", style="dim cyan"))
            else:
                info_table.add_row("Your Status", Text("🚗 You are moving", style="dim yellow"))
        
        info_panel = Panel(info_table, title="Navigation & Signal Tracking", border_style="green", box=box.DOUBLE)
        
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
        
        # Show position - both GPS and estimated if available
        if node.latitude and node.longitude:
            detail_table.add_row("Last GPS Location", f"{node.latitude:.6f}, {node.longitude:.6f}")
            if node.altitude:
                altitude_ft = node.altitude * 3.28084
                detail_table.add_row("GPS Altitude", f"{altitude_ft:.1f}ft")
        else:
            detail_table.add_row("Last GPS Location", "⚠️  No GPS data from node")
        
        detail_panel = Panel(detail_table, title="Node Details", border_style="blue")
        
        # Dedicated Estimated Position Panel with rolling algorithm updates
        est_position_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        est_position_table.add_column("Info", style="white", width=70)
        
        if node.estimated_position or (not node.latitude and not node.longitude and len(node.estimation_samples) > 0):
            # Show estimated position if available
            if node.estimated_position:
                est_lat, est_lon = node.estimated_position
                est_position_table.add_row(Text(f"📍 Estimated: {est_lat:.6f}, {est_lon:.6f}", style="bold green"))
                est_position_table.add_row(Text(f"Confidence: {'Medium' if len(node.estimation_samples) >= 10 else 'Low'} ({len(node.estimation_samples)} RSSI samples)", style="yellow"))
            else:
                est_position_table.add_row(Text(f"⏳ Calculating... ({len(node.estimation_samples)} samples collected)", style="yellow"))
            
            est_position_table.add_row(Text("", style="dim"))  # Spacer
            
            # Show rolling 5-line algorithm updates
            if node.estimation_log and len(node.estimation_log) > 0:
                est_position_table.add_row(Text("Algorithm Updates (last 5):", style="cyan"))
                for log_entry in node.estimation_log[-5:]:
                    est_position_table.add_row(Text(f"  {log_entry}", style="dim white"))
            else:
                est_position_table.add_row(Text("Waiting for RSSI samples to calculate position...", style="dim white"))
        elif not node.latitude and not node.longitude:
            # Node has no GPS and we're trying to estimate
            est_position_table.add_row(Text("🎯 Position Estimation Active", style="bold cyan"))
            est_position_table.add_row(Text(f"Status: Collecting RSSI samples ({len(node.estimation_samples)}/3 minimum)", style="yellow"))
            est_position_table.add_row(Text("", style="dim"))
            if self.gps_data.fix:
                est_position_table.add_row(Text("Algorithm: Weighted RSSI triangulation", style="dim white"))
                est_position_table.add_row(Text("Waiting for node to transmit packets...", style="dim white"))
            else:
                est_position_table.add_row(Text("⚠️  GPS fix required on Pi to start estimation", style="bold red"))
        else:
            # Node has GPS, no estimation needed
            est_position_table.add_row(Text("✓ Node has GPS coordinates", style="bold green"))
            est_position_table.add_row(Text("Position estimation not needed", style="dim white"))
        
        est_position_panel = Panel(est_position_table, title="🎯 Estimated Position & Algorithm", border_style="magenta", box=box.ROUNDED)
        
        # Your GPS
        gps_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        gps_table.add_column("Key", style="cyan")
        gps_table.add_column("Value", style="white")
        
        if self.gps_data.fix:
            gps_table.add_row("Your Position", f"{self.gps_data.latitude:.6f}, {self.gps_data.longitude:.6f}")
            sats = self.gps_data.satellites or 0
            gps_table.add_row("Satellites", str(sats))
            if sats < 6:
                gps_table.add_row("⚠️  Accuracy", "Low - position may be aged or inaccurate")
            if self.gps_data.altitude:
                gps_table.add_row("Altitude", f"{self.gps_data.altitude:.1f}ft")
        else:
            gps_table.add_row("Status", "⚠️  NO GPS FIX")
            gps_table.add_row("Note", "Cannot calculate distance/bearing")
        
        gps_panel = Panel(gps_table, title="Your GPS", border_style="yellow")
        
        # Instructions - make more prominent
        instructions = Text()
        instructions.append("📍 ", style="bold cyan")
        instructions.append("Press ", style="white")
        instructions.append("B", style="bold yellow on blue")
        instructions.append(" to go BACK to node list  |  Press ", style="white")
        instructions.append("Q", style="bold yellow on red")
        instructions.append(" to QUIT", style="white")
        
        instr_panel = Panel(instructions, border_style="bold yellow", title="⌨️  Controls")
        
        # Layout with estimated position panel always visible
        layout.split_column(
            Layout(header, size=3),
            Layout(info_panel, size=9),
            Layout(detail_panel, size=9),
            Layout(est_position_panel, size=9),
            Layout(gps_panel, size=7),
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
    
    def capture_screen_state(self):
        """Capture current screen state for debugging"""
        if not self.debug or not self.screen_capture_file:
            return
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Build debug info
            debug_info = []
            debug_info.append(f"\n{'='*80}")
            debug_info.append(f"Screen capture at {timestamp}")
            debug_info.append(f"{'='*80}")
            debug_info.append(f"Mode: {self.mode}")
            debug_info.append(f"GPS Fix: {self.gps_data.fix}")
            debug_info.append(f"GPS Lat/Lon: {self.gps_data.latitude}, {self.gps_data.longitude}")
            debug_info.append(f"Total Nodes: {len(self.nodes)}")
            debug_info.append(f"Selected Node: {self.selected_node}")
            
            if self.selected_node and self.selected_node in self.nodes:
                node = self.nodes[self.selected_node]
                debug_info.append(f"\nTracked Node Details:")
                debug_info.append(f"  ID: {node.node_id}")
                debug_info.append(f"  Short Name: {node.short_name}")
                debug_info.append(f"  RSSI: {node.rssi}")
                debug_info.append(f"  SNR: {node.snr}")
                debug_info.append(f"  Signal History Length: {len(node.signal_history)}")
                debug_info.append(f"  Last 3 signal entries: {node.signal_history[-3:] if len(node.signal_history) >= 3 else node.signal_history}")
                
                # Show trends
                trend_10s = node.get_signal_trend(10)
                trend_60s = node.get_signal_trend(60)
                debug_info.append(f"  Trend (10s): {trend_10s}")
                debug_info.append(f"  Trend (60s): {trend_60s}")
            
            with open(self.screen_capture_file, 'a') as f:
                f.write('\n'.join(debug_info) + '\n')
        except Exception as e:
            self.debug_log(f"Error capturing screen: {e}")
    
    def run(self):
        """Run the main application"""
        try:
            self.running = True
            
            # Start background threads
            self.console.print("[cyan]Starting GPS receiver...[/cyan]")
            self.start_gps_receiver()
            
            self.console.print("[cyan]Starting Meshtastic receiver...[/cyan]")
            self.start_meshtastic_receiver()
            
            time.sleep(3)  # Give threads time to start and populate nodeDB
            
            # Main display loop with keyboard input
            import sys
            import select
            import termios
            import tty
            
            # Set terminal to raw mode for immediate key capture
            old_settings = termios.tcgetattr(sys.stdin)
            capture_counter = 0
            
            try:
                tty.setcbreak(sys.stdin.fileno())
                
                with Live(self.generate_node_list_view(), refresh_per_second=2, console=self.console, screen=True) as live:
                    while self.running:
                        try:
                            # Auto-select last node after 10 seconds if user hasn't done anything
                            if (not self.auto_selected and 
                                time.time() - self.startup_time > 10 and 
                                self.mode == "list" and 
                                len(self.nodes) > 0):
                                # Prefer nodes with signal history (actively transmitting)
                                nodes_with_signal = [n for n in self.nodes.values() if len(n.signal_history) > 0]
                                
                                if nodes_with_signal:
                                    # Select most recently seen node with signal data
                                    selected = max(nodes_with_signal, key=lambda n: n.last_seen)
                                    self.selected_node = selected.node_id
                                    self.debug_log(f"Auto-selected node with signal data: {self.selected_node}")
                                else:
                                    # Fall back to last saved node
                                    last_node_id = self.load_last_selected_node()
                                    if last_node_id and last_node_id in self.nodes:
                                        self.selected_node = last_node_id
                                        self.debug_log(f"Auto-selected last saved node: {self.selected_node}")
                                
                                if self.selected_node:
                                    self.mode = "track"
                                    self.auto_selected = True
                            
                            # Update display
                            if self.mode == "list":
                                live.update(self.generate_node_list_view())
                            elif self.mode == "track":
                                live.update(self.generate_tracking_view())
                            
                            # Capture screen periodically in debug mode
                            if self.debug:
                                capture_counter += 1
                                if capture_counter >= 10:  # Every ~2 seconds
                                    self.capture_screen_state()
                                    capture_counter = 0
                            
                            # Check for keyboard input (non-blocking)
                            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                            if rlist:
                                key = sys.stdin.read(1)
                                
                                if key.lower() == 'q':
                                    break
                                elif key.lower() == 'b' and self.mode == "track":
                                    self.mode = "list"
                                    self.selected_node = None
                                elif key.isdigit() and self.mode == "list":
                                    # Select node by number
                                    idx = int(key) - 1
                                    if 0 <= idx < min(9, len(self.nodes)):
                                        sorted_nodes = sorted(self.nodes.keys(), 
                                                            key=lambda k: self.nodes[k].last_seen, 
                                                            reverse=True)
                                        if idx < len(sorted_nodes):
                                            self.selected_node = sorted_nodes[idx]
                                            self.mode = "track"
                                            self.save_last_selected_node()
                                            self.auto_selected = True  # Prevent auto-select after manual selection
                            
                            time.sleep(0.3)
                            
                        except KeyboardInterrupt:
                            break
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            
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
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging and screen capture'
    )
    
    args = parser.parse_args()
    
    console = Console()
    console.clear()
    
    if args.debug:
        console.print("[yellow]Debug mode enabled[/yellow]")
    
    tracker = MeshTracker(gps_port=args.gps_port, meshtastic_port=args.meshtastic_port, debug=args.debug)
    
    if args.debug:
        console.print(f"[yellow]Debug log: {tracker.debug_log_file}[/yellow]")
        console.print(f"[yellow]Screen capture: {tracker.screen_capture_file}[/yellow]")
    
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
