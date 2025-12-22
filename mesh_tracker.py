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

import numpy as np
from scipy.optimize import least_squares
from filterpy.kalman import KalmanFilter

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
        self.previous_position: Optional[Tuple[float, float]] = None  # For motion detection
        self.estimation_log: List[str] = []  # Log of estimation process
        # Real-time metrics
        self.metrics: dict = {
            'num_samples': 0,
            'avg_rssi': None,
            'std_rssi': None,
            'rmse_error': None,
            'bearing_spread': None,
            'avg_sample_age': None,
            'motion_detected': False,
            'kalman_error': None
        }
        # Kalman filter for tracking
        self.kalman_filter: Optional[KalmanFilter] = None
        self.last_update_time: Optional[float] = None
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
    
    def init_kalman_filter(self, initial_lat: float, initial_lon: float):
        """Initialize Kalman filter for position tracking"""
        # State: [lat, lon, vel_lat, vel_lon]
        # Constant velocity model
        self.kalman_filter = KalmanFilter(dim_x=4, dim_z=2)
        
        # State transition matrix (constant velocity)
        dt = 1.0  # Time step (will be updated dynamically)
        self.kalman_filter.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        
        # Measurement matrix (we measure position only)
        self.kalman_filter.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])
        
        # Initial state
        self.kalman_filter.x = np.array([initial_lat, initial_lon, 0, 0])
        
        # Measurement noise (RMSE from trilateration)
        self.kalman_filter.R = np.eye(2) * 0.0001  # Will be updated based on RMSE
        
        # Process noise (motion uncertainty)
        self.kalman_filter.Q = np.eye(4) * 0.00001
        
        # Initial covariance
        self.kalman_filter.P = np.eye(4) * 0.01
        
        self.last_update_time = time.time()
    
    def update_kalman_filter(self, measured_lat: float, measured_lon: float, measurement_noise: float):
        """Update Kalman filter with new measurement"""
        current_time = time.time()
        
        if self.kalman_filter is None:
            self.init_kalman_filter(measured_lat, measured_lon)
            return (measured_lat, measured_lon)
        
        # Update dt based on actual time elapsed
        if self.last_update_time is not None:
            dt = current_time - self.last_update_time
            if dt > 0:
                self.kalman_filter.F[0, 2] = dt
                self.kalman_filter.F[1, 3] = dt
        
        # Predict step
        self.kalman_filter.predict()
        
        # Update measurement noise based on RMSE
        # Convert meters to approximate degrees (rough conversion at mid-latitudes)
        noise_deg = measurement_noise / 111000  # meters to degrees
        self.kalman_filter.R = np.eye(2) * (noise_deg ** 2)
        
        # Update step
        z = np.array([measured_lat, measured_lon])
        self.kalman_filter.update(z)
        
        self.last_update_time = current_time
        
        # Return filtered position
        filtered_lat = self.kalman_filter.x[0]
        filtered_lon = self.kalman_filter.x[1]
        
        # Calculate Kalman uncertainty from covariance
        pos_variance = (self.kalman_filter.P[0, 0] + self.kalman_filter.P[1, 1]) / 2
        kalman_error_deg = np.sqrt(pos_variance)
        kalman_error_m = kalman_error_deg * 111000  # degrees to meters
        
        return (filtered_lat, filtered_lon, kalman_error_m)


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
    
    def __init__(self, gps_port: int = 2947, meshtastic_port: Optional[str] = None, debug: bool = False,
                 path_loss_exp: float = 2.5, tx_power: float = 14.0, freq_mhz: float = 915.0,
                 max_samples: Optional[int] = None, time_decay: float = 300.0,
                 heatmap_grid: Tuple[int, int] = (20, 10), auto_heatmap: bool = False):
        self.console = Console()
        self.gps_port = gps_port
        self.meshtastic_port = meshtastic_port
        self.debug = debug
        
        # RSSI to distance conversion parameters
        self.path_loss_exp = path_loss_exp
        self.tx_power = tx_power
        self.freq_mhz = freq_mhz
        
        # Data inclusion parameters
        self.max_samples = max_samples  # None = all samples, or limit for performance
        self.time_decay = time_decay  # Time constant for exponential decay (seconds)
        
        # Heatmap parameters
        self.heatmap_grid = heatmap_grid
        self.auto_heatmap = auto_heatmap
        
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
            
            # Extract user info if available in packet
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
            
            # If we still don't have proper names, try to get them from mesh interface's nodeDB
            if (node.long_name == "Unknown" or node.short_name == "Unknown"):
                if self.mesh_interface and hasattr(self.mesh_interface, 'nodes'):
                    # Try both with and without '!' prefix
                    lookup_ids = [node_id]
                    if node_id.startswith('!'):
                        lookup_ids.append(node_id[1:])
                    else:
                        lookup_ids.append('!' + node_id)
                    
                    for lookup_id in lookup_ids:
                        if lookup_id in self.mesh_interface.nodes:
                            node_info = self.mesh_interface.nodes[lookup_id]
                            if 'user' in node_info and node_info['user']:
                                user_data = node_info['user']
                                if 'shortName' in user_data and user_data['shortName'] and node.short_name == "Unknown":
                                    node.short_name = user_data['shortName']
                                    self.debug_log(f"Updated short name from nodeDB: {node.short_name}")
                                if 'longName' in user_data and user_data['longName'] and node.long_name == "Unknown":
                                    node.long_name = user_data['longName']
                                    self.debug_log(f"Updated long name from nodeDB: {node.long_name}")
                            break
            
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
                # Collect RSSI sample if we have GPS fix - ALWAYS collect for estimation
                if self.gps_data.fix:
                    sample = {
                        'timestamp': time.time(),
                        'rssi': rssi_value,
                        'gps_lat': self.gps_data.latitude,
                        'gps_lon': self.gps_data.longitude,
                        'snr': packet.get('rxSnr', packet.get('snr', 0))
                    }
                    node.estimation_samples.append(sample)
                    self.debug_log(f"Added estimation sample for {node_id}")
                    
                    # Optional downsampling if >500 samples for performance
                    if len(node.estimation_samples) > 500:
                        # Keep every other sample
                        node.estimation_samples = node.estimation_samples[::2]
                        self.debug_log(f"Downsampled to {len(node.estimation_samples)} samples")
                    
                    # Try to estimate position if we have enough samples - ALWAYS estimate
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
    
    def rssi_to_distance(self, rssi: float, tx_power: float = 14.0, freq_mhz: float = 915.0, path_loss_exp: float = 2.5) -> float:
        """
        Convert RSSI to estimated distance using log-distance path loss model with FSPL
        
        Args:
            rssi: Received signal strength in dBm (typically -30 to -120)
            tx_power: Transmit power in dBm (Meshtastic default ~14 dBm for US)
            freq_mhz: Frequency in MHz (915 for US, 868 for EU)
            path_loss_exp: Path loss exponent (2=free space, 2.5=outdoor, 3-4=urban)
        
        Returns:
            Estimated distance in meters
        
        Formula: RSSI = TxPower - FSPL - 10*n*log10(d/d0)
        FSPL at 1m: 20*log10(freq_MHz) + 20*log10(1) - 27.55
        """
        # Free space path loss at 1 meter reference distance
        fspl_1m = 20 * math.log10(freq_mhz) + 20 * math.log10(1) - 27.55
        
        # Calculate distance
        path_loss = tx_power - rssi - fspl_1m
        distance = 10 ** (path_loss / (10 * path_loss_exp))
        
        return max(distance, 1.0)  # Minimum 1 meter
    
    def estimate_node_position(self, node: MeshNode):
        """
        Estimate node position using enhanced RSSI-based trilateration with:
        - Outlier filtering (>2 std dev removed)
        - SNR incorporation in weights
        - Time-based decay weighting (recent samples prioritized)
        - Diversity checks (bearing spread)
        - SciPy least_squares optimization
        - Real-time metrics (RMSE, bearing spread, etc.)
        """
        try:
            # Use configurable subset or all samples
            if self.max_samples is not None:
                samples = node.estimation_samples[-self.max_samples:]
            else:
                samples = node.estimation_samples
            
            if len(samples) < 3:
                timestamp_str = datetime.now().strftime("%H:%M:%S")
                node.estimation_log.append(f"{timestamp_str} - Need 3 samples minimum, currently have {len(samples)}")
                if len(node.estimation_log) > 10:
                    node.estimation_log = node.estimation_log[-10:]
                return
            
            timestamp_str = datetime.now().strftime("%H:%M:%S")
            current_time = time.time()
            
            # Update total samples collected metric
            node.metrics['total_samples'] = len(node.estimation_samples)
            
            # Step 1: Filter outliers using numpy
            rssi_values = np.array([s['rssi'] for s in samples])
            mean_rssi = np.mean(rssi_values)
            std_rssi = np.std(rssi_values)
            
            # Keep samples within 2 std deviations
            filtered_samples = []
            for sample in samples:
                if abs(sample['rssi'] - mean_rssi) <= 2 * std_rssi:
                    filtered_samples.append(sample)
            
            if len(filtered_samples) < 3:
                node.estimation_log.append(f"{timestamp_str} - After outlier filtering: {len(filtered_samples)} samples (need 3+)")
                if len(node.estimation_log) > 10:
                    node.estimation_log = node.estimation_log[-10:]
                return
            
            # Step 2: Calculate bearings for diversity check
            if self.gps_data.fix:
                my_lat = self.gps_data.latitude
                my_lon = self.gps_data.longitude
                bearings = []
                for sample in filtered_samples:
                    bearing = calculate_bearing(my_lat, my_lon, sample['gps_lat'], sample['gps_lon'])
                    bearings.append(bearing)
                
                # Check diversity: std dev of bearings should be > 30 degrees
                bearing_std = np.std(bearings)
                if bearing_std < 30:
                    node.estimation_log.append(f"{timestamp_str} - Insufficient sample diversity (bearing spread: {bearing_std:.1f}°, need >30°)")
                    node.estimation_log.append(f"{timestamp_str} - Move to different positions around the node")
                    if len(node.estimation_log) > 10:
                        node.estimation_log = node.estimation_log[-10:]
                    node.metrics['bearing_spread'] = bearing_std
                    return
                
                node.metrics['bearing_spread'] = bearing_std
            
            # Step 3: Incorporate SNR and time-based decay into weights
            measurements = []
            for sample in filtered_samples:
                # Base weight from RSSI
                base_weight = 10 ** (sample['rssi'] / 20.0)
                
                # Enhanced weight with SNR if available
                if sample.get('snr') is not None and sample['snr'] > 0:
                    weight = base_weight * (sample['snr'] + 10)
                else:
                    weight = base_weight
                
                # Apply time-based decay: prioritize recent samples
                sample_age = current_time - sample.get('timestamp', current_time)
                time_decay_factor = np.exp(-sample_age / self.time_decay)
                weight *= time_decay_factor
                
                distance = self.rssi_to_distance(sample['rssi'], 
                                                tx_power=self.tx_power,
                                                freq_mhz=self.freq_mhz,
                                                path_loss_exp=self.path_loss_exp)
                
                measurements.append({
                    'lat': sample['gps_lat'],
                    'lon': sample['gps_lon'],
                    'distance': distance,
                    'rssi': sample['rssi'],
                    'snr': sample.get('snr'),
                    'weight': weight,
                    'timestamp': sample.get('timestamp', current_time)
                })
            
            # Update metrics
            node.metrics['num_samples'] = len(measurements)
            node.metrics['avg_rssi'] = float(np.mean([m['rssi'] for m in measurements]))
            node.metrics['std_rssi'] = float(np.std([m['rssi'] for m in measurements]))
            
            # Calculate average sample age
            ages = [(current_time - m['timestamp']) for m in measurements]
            node.metrics['avg_sample_age'] = float(np.mean(ages))
            
            node.estimation_log.append(f"{timestamp_str} - Using {len(measurements)} samples (avg RSSI: {node.metrics['avg_rssi']:.1f}±{node.metrics['std_rssi']:.1f} dBm)")
            node.estimation_log.append(f"{timestamp_str} - Total collected: {node.metrics.get('total_samples', len(node.estimation_samples))}, avg age: {node.metrics['avg_sample_age']:.0f}s")
            
            # Step 4: SciPy least_squares trilateration
            # Initial guess: weighted centroid
            total_weight = sum(m['weight'] for m in measurements)
            init_lat = sum(m['lat'] * m['weight'] for m in measurements) / total_weight
            init_lon = sum(m['lon'] * m['weight'] for m in measurements) / total_weight
            
            # Define residual function for least_squares
            def residuals(pos):
                est_lat, est_lon = pos
                resids = []
                for m in measurements:
                    calc_dist = calculate_distance(est_lat, est_lon, m['lat'], m['lon'])
                    # Weighted residual
                    resid = (calc_dist - m['distance']) * math.sqrt(m['weight'])
                    resids.append(resid)
                return resids
            
            # Optimize using least_squares
            result = least_squares(residuals, [init_lat, init_lon], method='lm')
            
            if result.success:
                est_lat, est_lon = result.x
                
                # Calculate RMSE for confidence metric
                residual_values = np.array(residuals(result.x))
                # Unweight the residuals for RMSE calculation
                unweighted_residuals = []
                for i, m in enumerate(measurements):
                    unweighted_residuals.append(residual_values[i] / math.sqrt(m['weight']))
                rmse = float(np.sqrt(np.mean(np.array(unweighted_residuals) ** 2)))
                node.metrics['rmse_error'] = rmse
                
                # Store previous position for motion detection
                if node.estimated_position:
                    node.previous_position = node.estimated_position
                
                # Detect potential motion
                motion_detected = False
                if node.previous_position:
                    prev_lat, prev_lon = node.previous_position
                    change_m = calculate_distance(prev_lat, prev_lon, est_lat, est_lon)
                    
                    # Motion detected if moved >50m or RSSI std dev >10
                    if change_m > 50 or node.metrics['std_rssi'] > 10:
                        motion_detected = True
                        node.metrics['motion_detected'] = True
                        # Increase process noise in Kalman filter
                        if node.kalman_filter is not None:
                            node.kalman_filter.Q *= 2.0
                    else:
                        node.metrics['motion_detected'] = False
                
                # Apply Kalman filtering if we have enough samples
                if len(measurements) >= 5:
                    # Use Kalman filter for smoothing
                    kalman_result = node.update_kalman_filter(est_lat, est_lon, rmse)
                    if len(kalman_result) == 3:
                        filtered_lat, filtered_lon, kalman_error = kalman_result
                        node.metrics['kalman_error'] = kalman_error
                        
                        # Use Kalman filtered position
                        final_lat, final_lon = filtered_lat, filtered_lon
                        method_str = "SciPy + Kalman filter"
                    else:
                        # Fallback if Kalman returns only position
                        final_lat, final_lon = kalman_result
                        method_str = "SciPy + Kalman filter"
                else:
                    # Not enough samples for Kalman, use raw trilateration
                    final_lat, final_lon = est_lat, est_lon
                    method_str = "SciPy least_squares with time-decay"
                
                # Calculate change from previous estimate
                change_msg = ""
                if node.estimated_position:
                    old_lat, old_lon = node.estimated_position
                    change_m = calculate_distance(old_lat, old_lon, final_lat, final_lon)
                    change_ft = change_m * 3.28084
                    change_msg = f" (moved {change_ft:.1f}ft)"
                
                node.estimated_position = (final_lat, final_lon)
                
                motion_flag = " 🚶 MOTION" if motion_detected else ""
                node.estimation_log.append(f"{timestamp_str} - ✓ Position: {final_lat:.6f}, {final_lon:.6f}{change_msg}{motion_flag}")
                node.estimation_log.append(f"{timestamp_str} - Method: {method_str}")
                node.estimation_log.append(f"{timestamp_str} - Est. error: ±{rmse:.1f}m (RMSE)")
                if node.metrics.get('kalman_error'):
                    node.estimation_log.append(f"{timestamp_str} - Tracking error: ±{node.metrics['kalman_error']:.1f}m (Kalman)")
            else:
                # Fallback to weighted centroid if optimization fails
                node.estimation_log.append(f"{timestamp_str} - Optimization failed, using weighted centroid")
                node.estimated_position = (init_lat, init_lon)
                node.metrics['rmse_error'] = None
            
            # Keep only last 10 log entries
            if len(node.estimation_log) > 10:
                node.estimation_log = node.estimation_log[-10:]
                
        except Exception as e:
            timestamp_str = datetime.now().strftime("%H:%M:%S")
            node.estimation_log.append(f"{timestamp_str} - ⚠️ Estimation error: {str(e)}")
            if len(node.estimation_log) > 10:
                node.estimation_log = node.estimation_log[-10:]
            import traceback
            self.debug_log(f"Estimation error: {traceback.format_exc()}")
    
    def generate_terminal_heatmap(self, node: MeshNode, grid_size: Tuple[int, int] = (20, 10)):
        """
        Generate terminal-based heatmap of RSSI samples
        Uses ANSI colors (green=weak to red=strong)
        """
        try:
            if len(node.estimation_samples) < 10:
                self.console.print(f"[yellow]Not enough samples for heatmap ({len(node.estimation_samples)}/10 minimum)[/yellow]")
                return
            
            # Get all valid samples
            samples = node.estimation_samples
            
            # Extract lat/lon/rssi
            lats = np.array([s['gps_lat'] for s in samples])
            lons = np.array([s['gps_lon'] for s in samples])
            rssis = np.array([s['rssi'] for s in samples])
            
            # Calculate mean position for reference
            mean_lat = np.mean(lats)
            mean_lon = np.mean(lons)
            
            # Convert to relative x,y meters using flat-earth approximation
            # (Good enough for small areas)
            R = 6371000  # Earth radius in meters
            lat_to_m = R * np.pi / 180
            lon_to_m = R * np.pi / 180 * np.cos(np.radians(mean_lat))
            
            x = (lons - mean_lon) * lon_to_m
            y = (lats - mean_lat) * lat_to_m
            
            # Auto-scale: Find min/max x,y
            x_min, x_max = np.min(x), np.max(x)
            y_min, y_max = np.min(y), np.max(y)
            
            # Add padding
            x_range = x_max - x_min
            y_range = y_max - y_min
            if x_range < 10:  # Minimum 10m range
                x_min -= 5
                x_max += 5
                x_range = 10
            if y_range < 10:
                y_min -= 5
                y_max += 5
                y_range = 10
            
            x_min -= x_range * 0.1
            x_max += x_range * 0.1
            y_min -= y_range * 0.1
            y_max += y_range * 0.1
            
            # Create grid
            grid_width, grid_height = grid_size
            x_edges = np.linspace(x_min, x_max, grid_width + 1)
            y_edges = np.linspace(y_min, y_max, grid_height + 1)
            
            # Bin samples into grid and compute average RSSI per cell
            grid_rssi = np.full((grid_height, grid_width), np.nan)
            grid_counts = np.zeros((grid_height, grid_width))
            
            for i in range(len(x)):
                # Find which cell this sample belongs to
                x_idx = np.searchsorted(x_edges, x[i]) - 1
                y_idx = np.searchsorted(y_edges, y[i]) - 1
                
                # Bounds check
                if 0 <= x_idx < grid_width and 0 <= y_idx < grid_height:
                    if np.isnan(grid_rssi[y_idx, x_idx]):
                        grid_rssi[y_idx, x_idx] = rssis[i]
                        grid_counts[y_idx, x_idx] = 1
                    else:
                        grid_rssi[y_idx, x_idx] += rssis[i]
                        grid_counts[y_idx, x_idx] += 1
            
            # Average RSSI in each cell
            for y_idx in range(grid_height):
                for x_idx in range(grid_width):
                    if grid_counts[y_idx, x_idx] > 0:
                        grid_rssi[y_idx, x_idx] /= grid_counts[y_idx, x_idx]
            
            # Normalize RSSI for coloring
            valid_rssis = grid_rssi[~np.isnan(grid_rssi)]
            if len(valid_rssis) == 0:
                self.console.print("[yellow]No valid data for heatmap[/yellow]")
                return
            
            rssi_min, rssi_max = np.min(valid_rssis), np.max(valid_rssis)
            if rssi_min == rssi_max:
                rssi_max = rssi_min + 1
            
            # Clear screen and print heatmap
            self.console.print("\\n" + "="*80)
            self.console.print(f"[bold cyan]RSSI Heatmap for {node.short_name} ({node.node_id})[/bold cyan]")
            self.console.print(f"Grid: {grid_width}x{grid_height}, Samples: {len(samples)}, Range: {x_range:.1f}m x {y_range:.1f}m")
            self.console.print("="*80 + "\\n")
            
            # Print grid (top to bottom)
            for y_idx in reversed(range(grid_height)):
                row_str = ""
                for x_idx in range(grid_width):
                    if np.isnan(grid_rssi[y_idx, x_idx]):
                        # Empty cell
                        row_str += " "
                    else:
                        # Normalize RSSI to [0, 1]
                        norm_rssi = (grid_rssi[y_idx, x_idx] - rssi_min) / (rssi_max - rssi_min)
                        
                        # Map to green (weak) -> red (strong)
                        # norm_rssi: 0 = green, 1 = red
                        r = int(255 * norm_rssi)
                        g = int(255 * (1 - norm_rssi))
                        b = 0
                        
                        # ANSI color code
                        color_code = f"\\x1b[38;2;{r};{g};{b}m"
                        reset_code = "\\x1b[0m"
                        row_str += f"{color_code}█{reset_code}"
                
                self.console.print(row_str)
            
            # Print legend
            self.console.print("\\n" + "="*80)
            self.console.print(f"[green]Weak ({rssi_min:.1f} dBm)[/green] ← → [red]Strong ({rssi_max:.1f} dBm)[/red]")
            
            # Overlay estimated position if available
            if node.estimated_position:
                est_lat, est_lon = node.estimated_position
                est_x = (est_lon - mean_lon) * lon_to_m
                est_y = (est_lat - mean_lat) * lat_to_m
                self.console.print(f"[bold white]Estimated Position: X={est_x:.1f}m, Y={est_y:.1f}m (marked as X in white)[/bold white]")
            
            self.console.print("="*80 + "\\n")
            self.console.print("[dim]Press any key to return...[/dim]")
            
        except Exception as e:
            self.console.print(f"[red]Error generating heatmap: {e}[/red]")
            import traceback
            self.debug_log(f"Heatmap error: {traceback.format_exc()}")
    
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
            
            # Use long name, fall back to short name if long name is Unknown or same as short name
            display_name = node.long_name
            if display_name == "Unknown" or display_name == node.short_name:
                # If we still don't have a good name, format the node ID nicely
                if node.short_name != "Unknown":
                    display_name = node.short_name
                else:
                    display_name = f"Meshtastic {node.node_id[-4:]}"
            
            # Truncate if too long
            long_name = display_name[:20] if len(display_name) <= 20 else display_name[:17] + "..."
            
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
        
        # Calculate distance and bearing ONLY from estimated position (triangulated)
        distance = None
        bearing = None
        compass = None
        position_type = None
        
        # ONLY use estimated position - this is the whole point of triangulation
        if (self.gps_data.fix and node.estimated_position):
            node_lat, node_lon = node.estimated_position
            position_type = "ESTIMATED"
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
        
        # Always show estimation if we have samples or estimated position
        if node.estimated_position or len(node.estimation_samples) > 0:
            # Show estimated position if available
            if node.estimated_position:
                est_lat, est_lon = node.estimated_position
                est_position_table.add_row(Text(f"📍 Estimated: {est_lat:.6f}, {est_lon:.6f}", style="bold green"))
                
                # If node has GPS, show comparison
                if node.latitude and node.longitude:
                    # Calculate distance between GPS and estimated position
                    from math import radians, sin, cos, sqrt, atan2
                    R = 6371000  # Earth radius in meters
                    lat1, lon1 = radians(node.latitude), radians(node.longitude)
                    lat2, lon2 = radians(est_lat), radians(est_lon)
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                    c = 2 * atan2(sqrt(a), sqrt(1-a))
                    distance_m = R * c
                    distance_ft = distance_m * 3.28084
                    est_position_table.add_row(Text(f"GPS Actual: {node.latitude:.6f}, {node.longitude:.6f}", style="cyan"))
                    est_position_table.add_row(Text(f"Accuracy: ±{distance_ft:.1f}ft from GPS", style="yellow"))
                
                est_position_table.add_row(Text(f"Confidence: {'Medium' if len(node.estimation_samples) >= 10 else 'Low'} ({len(node.estimation_samples)} RSSI samples)", style="dim yellow"))
            else:
                est_position_table.add_row(Text(f"⏳ Collecting data... ({len(node.estimation_samples)}/3 samples minimum)", style="yellow"))
            
            est_position_table.add_row(Text("", style="dim"))  # Spacer
            
            # Show rolling 5-line algorithm updates
            if node.estimation_log and len(node.estimation_log) > 0:
                est_position_table.add_row(Text("Algorithm Updates (last 5):", style="cyan"))
                for log_entry in node.estimation_log[-5:]:
                    est_position_table.add_row(Text(f"  {log_entry}", style="dim white"))
            else:
                est_position_table.add_row(Text("Waiting for node to transmit more packets...", style="dim white"))
                est_position_table.add_row(Text("(Need 3 packets with RSSI data)", style="dim yellow"))
        else:
            # No samples yet
            est_position_table.add_row(Text("🎯 Position Estimation Initializing", style="bold cyan"))
            est_position_table.add_row(Text(f"Status: Waiting for RSSI data (0/3 minimum)", style="yellow"))
            est_position_table.add_row(Text("", style="dim"))
            if self.gps_data.fix:
                est_position_table.add_row(Text("Algorithm: RSSI Trilateration", style="dim white"))
                est_position_table.add_row(Text("How it works:", style="cyan"))
                est_position_table.add_row(Text("  1. Move to different locations while tracking", style="dim white"))
                est_position_table.add_row(Text("  2. RSSI converts to distance circles", style="dim white"))
                est_position_table.add_row(Text("  3. Circles intersect at target location", style="dim white"))
                est_position_table.add_row(Text("Waiting for node to transmit packets...", style="dim yellow"))
            else:
                est_position_table.add_row(Text("⚠️  GPS fix required on Pi to start estimation", style="bold red"))
        
        est_position_panel = Panel(est_position_table, title="🎯 Estimated Position & Algorithm", border_style="magenta", box=box.ROUNDED)
        
        # Metrics Panel - Show real-time estimation metrics
        metrics_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        metrics_table.add_column("Key", style="cyan", width=25)
        metrics_table.add_column("Value", style="white", width=30)
        
        if node.metrics['num_samples'] > 0:
            if node.metrics.get('total_samples'):
                metrics_table.add_row("Total Samples Collected", str(node.metrics['total_samples']))
            metrics_table.add_row("Valid Samples Used", str(node.metrics['num_samples']))
            if node.metrics['avg_rssi'] is not None:
                metrics_table.add_row("Avg RSSI", f"{node.metrics['avg_rssi']:.1f} dBm")
            if node.metrics['std_rssi'] is not None:
                metrics_table.add_row("RSSI Std Dev", f"{node.metrics['std_rssi']:.1f} dBm")
            if node.metrics['rmse_error'] is not None:
                metrics_table.add_row("Est. Error (RMSE)", f"±{node.metrics['rmse_error']:.1f} m")
            if node.metrics['bearing_spread'] is not None:
                metrics_table.add_row("Sample Diversity", f"{node.metrics['bearing_spread']:.1f}°")
            if node.metrics['avg_sample_age'] is not None:
                age_min = node.metrics['avg_sample_age'] / 60
                metrics_table.add_row("Avg Sample Age", f"{age_min:.1f} min")
            if node.metrics['motion_detected']:
                metrics_table.add_row("Motion Status", Text("⚠️  Motion Detected", style="bold yellow"))
            if node.metrics['kalman_error'] is not None:
                metrics_table.add_row("Tracking Error", f"±{node.metrics['kalman_error']:.1f} m")
        else:
            metrics_table.add_row("Status", Text("Collecting samples...", style="dim yellow"))
        
        metrics_panel = Panel(metrics_table, title="📊 Estimation Metrics", border_style="cyan", box=box.ROUNDED)
        
        # Distance & Compass panel (right side)
        distance_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        distance_table.add_column("Info", style="white", width=30)
        
        # Only show navigation data if we have a position estimate
        if node.estimated_position and distance is not None and bearing is not None and compass is not None:
            distance_table.add_row(Text("📏 DISTANCE", style="bold cyan"))
            distance_table.add_row(Text(format_distance(distance), style="bold green"))
            distance_table.add_row(Text("", style="dim"))
            distance_table.add_row(Text("🧭 BEARING", style="bold cyan"))
            distance_table.add_row(Text(f"{bearing:.1f}°", style="bold yellow"))
            distance_table.add_row(Text("", style="dim"))
            distance_table.add_row(Text("🎯 DIRECTION", style="bold cyan"))
            distance_table.add_row(Text(f"{compass}", style="bold white"))
            distance_table.add_row(Text(self.create_compass_visual(bearing), style="bold green"))
            
            # Add estimated position info
            distance_table.add_row(Text("", style="dim"))
            distance_table.add_row(Text("📍 FROM", style="bold magenta"))
            if position_type == "ESTIMATED":
                distance_table.add_row(Text("Estimated Pos.", style="dim yellow"))
            else:
                distance_table.add_row(Text("GPS Position", style="dim cyan"))
        else:
            # No navigation data until first position estimate
            distance_table.add_row(Text("⏳ Awaiting Position", style="yellow"))
            distance_table.add_row(Text("", style="dim"))
            if not node.estimated_position:
                distance_table.add_row(Text("Waiting for first", style="dim white"))
                distance_table.add_row(Text("position estimate", style="dim white"))
            elif not self.gps_data.fix:
                distance_table.add_row(Text("Need GPS fix", style="dim white"))
            elif not (node_lat and node_lon):
                distance_table.add_row(Text("Need node position", style="dim white"))
        
        distance_panel = Panel(distance_table, title="📍 Navigation", border_style="green", box=box.ROUNDED)
        
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
        instructions.append(" to go BACK  |  ", style="white")
        instructions.append("H", style="bold yellow on magenta")
        instructions.append(" for Heatmap  |  ", style="white")
        instructions.append("Q", style="bold yellow on red")
        instructions.append(" to QUIT", style="white")
        
        instr_panel = Panel(instructions, border_style="bold yellow", title="⌨️  Controls")
        
        # Create a horizontal layout for estimation and distance panels
        estimation_row = Layout()
        estimation_row.split_row(
            Layout(est_position_panel, ratio=2),
            Layout(distance_panel, ratio=1)
        )
        
        # Layout with estimated position panel and metrics panel always visible
        layout.split_column(
            Layout(header, size=3),
            Layout(info_panel, size=9),
            Layout(detail_panel, size=9),
            Layout(estimation_row, size=10),
            Layout(metrics_panel, size=8),
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
            
            # Check if we're running in a proper terminal
            if not sys.stdin.isatty():
                self.console.print("[yellow]Warning: Not running in a terminal. Interactive mode disabled.[/yellow]")
                self.console.print("[yellow]Press Ctrl+C to exit.[/yellow]")
                # Just keep running without interactive mode
                try:
                    while self.running:
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass
                return
            
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
                                elif key.lower() == 'h' and self.mode == "track" and self.selected_node:
                                    # Generate heatmap for current tracked node
                                    node = self.nodes.get(self.selected_node)
                                    if node:
                                        # Temporarily exit live display
                                        live.stop()
                                        self.generate_terminal_heatmap(node, self.heatmap_grid)
                                        # Wait for user input
                                        sys.stdin.read(1)
                                        # Resume live display
                                        live.start()
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
    parser.add_argument(
        '--path-loss',
        type=float,
        default=2.5,
        help='Path loss exponent (2=free space, 2.5=outdoor, 3-4=urban, default: 2.5)'
    )
    parser.add_argument(
        '--tx-power',
        type=float,
        default=14.0,
        help='Transmit power in dBm (default: 14.0 for US Meshtastic)'
    )
    parser.add_argument(
        '--freq',
        type=float,
        default=915.0,
        help='Frequency in MHz (default: 915.0 for US, 868.0 for EU)'
    )
    parser.add_argument(
        '--max-samples',
        type=int,
        default=None,
        help='Maximum samples to use for estimation (default: all samples)'
    )
    parser.add_argument(
        '--time-decay',
        type=float,
        default=300.0,
        help='Time decay constant in seconds for sample weighting (default: 300.0 = 5 minutes)'
    )
    parser.add_argument(
        '--heatmap-grid',
        type=str,
        default='20x10',
        help='Heatmap grid size as WIDTHxHEIGHT (default: 20x10)'
    )
    parser.add_argument(
        '--auto-heatmap',
        action='store_true',
        help='Automatically show heatmap on updates (default: manual with H key)'
    )
    
    args = parser.parse_args()
    
    # Parse heatmap grid
    try:
        grid_parts = args.heatmap_grid.split('x')
        heatmap_grid = (int(grid_parts[0]), int(grid_parts[1]))
    except:
        heatmap_grid = (20, 10)
    
    console = Console()
    console.clear()
    
    if args.debug:
        console.print("[yellow]Debug mode enabled[/yellow]")
    
    tracker = MeshTracker(
        gps_port=args.gps_port, 
        meshtastic_port=args.meshtastic_port, 
        debug=args.debug,
        path_loss_exp=args.path_loss,
        tx_power=args.tx_power,
        freq_mhz=args.freq,
        max_samples=args.max_samples,
        time_decay=args.time_decay,
        heatmap_grid=heatmap_grid,
        auto_heatmap=args.auto_heatmap
    )
    
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
