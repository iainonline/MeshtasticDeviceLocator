#!/usr/bin/env python3
"""
Meshtastic Node Tracker with GPS - GUI Version
Windows-style GUI with embedded map for tracking mesh nodes
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import tkintermapview
import threading
import socket
import json
import time
import math
import argparse
import re
import subprocess
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.optimize import least_squares
from filterpy.kalman import KalmanFilter

try:
    import meshtastic
    import meshtastic.serial_interface
except ImportError:
    print("Warning: meshtastic library not found")
    meshtastic = None


def check_device_timeout_errors(port: str) -> bool:
    """Check if device is reporting timeout errors in kernel log"""
    try:
        # Check dmesg for recent timeout errors on this port
        result = subprocess.run(
            ['dmesg', '|', 'tail', '-50'],
            shell=True,
            capture_output=True,
            text=True,
            timeout=2
        )
        output = result.stdout.lower()
        
        # Extract port name (e.g., ttyUSB0 from /dev/ttyUSB0)
        port_name = port.split('/')[-1] if '/' in port else port
        
        # Look for timeout errors (error -110 is ETIMEDOUT)
        if port_name.lower() in output and (
            'status: -110' in output or 
            'etimedout' in output or
            'timed out' in output or
            'failed set request' in output
        ):
            return True
    except Exception as e:
        print(f"[DEBUG] Could not check device status: {e}")
    return False


def parse_nmea_coordinate(coord_str: str, direction: str) -> Optional[float]:
    """Parse NMEA coordinate format (DDMM.MMMM) to decimal degrees"""
    try:
        if not coord_str or coord_str == '':
            return None
        
        # NMEA format: latitude DDMM.MMMM, longitude DDDMM.MMMM
        if len(coord_str) < 4:
            return None
            
        # Find decimal point
        dot_pos = coord_str.find('.')
        if dot_pos == -1:
            return None
        
        # For latitude: DDMM.MMMM (degrees = 2 digits before minutes)
        # For longitude: DDDMM.MMMM (degrees = 3 digits before minutes)
        # Minutes are always the last 2 digits before decimal + fractional part
        if dot_pos <= 4:  # Latitude (format: DDMM.MMMM, dot at position 4)
            degrees = int(coord_str[:dot_pos-2])
            minutes = float(coord_str[dot_pos-2:])
        else:  # Longitude (format: DDDMM.MMMM, dot at position 5)
            degrees = int(coord_str[:dot_pos-2])
            minutes = float(coord_str[dot_pos-2:])
        
        decimal = degrees + (minutes / 60.0)
        
        # Apply direction
        if direction in ['S', 'W']:
            decimal = -decimal
            
        return decimal
    except (ValueError, IndexError) as e:
        print(f"[ERROR] Coordinate parse error: {e} for '{coord_str}'")
        return None


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
                self.altitude = float(data['altitude']) * 3.28084  # Convert m to ft
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
        self.rssi_min: Optional[int] = None
        self.rssi_max: Optional[int] = None
        self.snr: Optional[float] = None
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.altitude: Optional[float] = None
        self.battery: Optional[int] = None
        self.packet_count: int = 0
        self.estimation_samples: List[dict] = []
        self.estimated_position: Optional[Tuple[float, float]] = None
        self.estimated_distance: Optional[float] = None
        self.previous_position: Optional[Tuple[float, float]] = None
        self.estimation_log: List[str] = []
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
        self.kalman_filter: Optional[KalmanFilter] = None
        self.kalman_initialized: bool = False
        self.last_update_time: Optional[float] = None
        self.signal_history: List[dict] = []
        
    def update(self, packet: dict, gps_data: Optional['GPSData'] = None):
        """Update node information from packet"""
        current_time = time.time()
        self.last_seen = current_time
        self.packet_count += 1
        
        if 'fromId' in packet:
            self.node_id = packet['fromId']
            
        if 'from' in packet and hasattr(packet.get('from'), 'user'):
            user = packet['from'].user
            if hasattr(user, 'shortName'):
                self.short_name = user.shortName
            if hasattr(user, 'longName'):
                self.long_name = user.longName
        
        # Extract position from packet if present
        if 'decoded' in packet:
            decoded = packet['decoded']
            if 'position' in decoded:
                pos = decoded['position']
                # Check for position data
                if 'latitude' in pos and 'longitude' in pos:
                    self.latitude = pos['latitude']
                    self.longitude = pos['longitude']
                    print(f"[DEBUG] Node {self.node_id} position from packet: {self.latitude:.6f}, {self.longitude:.6f}")
                if 'altitude' in pos:
                    self.altitude = pos['altitude']
        
        if self.rssi is not None:
            history_entry = {
                'timestamp': current_time,
                'rssi': self.rssi,
                'snr': self.snr if self.snr else 0
            }
            if gps_data and gps_data.fix:
                history_entry['gps_lat'] = gps_data.latitude
                history_entry['gps_lon'] = gps_data.longitude
            self.signal_history.append(history_entry)
            if len(self.signal_history) > 100:
                self.signal_history.pop(0)
    
    def init_kalman_filter(self, initial_lat: float, initial_lon: float, initial_uncertainty: float = 50.0):
        """Initialize Kalman filter for position tracking"""
        self.kalman_filter = KalmanFilter(dim_x=4, dim_z=2)
        
        dt = 1.0
        self.kalman_filter.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        
        self.kalman_filter.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])
        
        self.kalman_filter.x = np.array([initial_lat, initial_lon, 0, 0])
        
        initial_noise_deg = initial_uncertainty / 111000.0
        self.kalman_filter.R = np.eye(2) * (initial_noise_deg ** 2)
        
        process_noise_deg = 1.0 / 111000.0
        self.kalman_filter.Q = np.array([
            [process_noise_deg**2, 0, 0, 0],
            [0, process_noise_deg**2, 0, 0],
            [0, 0, (process_noise_deg/10)**2, 0],
            [0, 0, 0, (process_noise_deg/10)**2]
        ])
        
        initial_cov_deg = initial_uncertainty / 111000.0
        self.kalman_filter.P = np.array([
            [initial_cov_deg**2, 0, 0, 0],
            [0, initial_cov_deg**2, 0, 0],
            [0, 0, (initial_cov_deg/5)**2, 0],
            [0, 0, 0, (initial_cov_deg/5)**2]
        ])
        
        self.last_update_time = time.time()
        self.kalman_initialized = True


def estimate_distance_from_rssi(rssi: int, tx_power: int = 20, path_loss_exponent: float = 2.5) -> float:
    """
    Estimate distance from RSSI using path loss formula
    
    Args:
        rssi: Received signal strength in dBm
        tx_power: Transmit power in dBm (typically 20-30 for Meshtastic)
        path_loss_exponent: Path loss exponent (2=free space, 2-3=outdoor, 3-4=indoor)
    
    Returns:
        Estimated distance in meters
    """
    if rssi >= tx_power:
        return 1.0  # Very close
    
    # Path loss formula: RSSI = TxPower - 10 * n * log10(distance)
    # Solving for distance: distance = 10^((TxPower - RSSI) / (10 * n))
    distance = 10 ** ((tx_power - rssi) / (10 * path_loss_exponent))
    
    return distance


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS coordinates using Haversine formula"""
    R = 6371000
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
    """Calculate bearing from point 1 to point 2"""
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
    feet = meters * 3.28084
    if feet < 5280:
        return f"{feet:.0f}ft"
    else:
        miles = feet / 5280
        return f"{miles:.2f}mi"


def calculate_destination(lat: float, lon: float, distance_meters: float, bearing_degrees: float) -> Tuple[float, float]:
    """Calculate destination GPS coordinates given starting point, distance, and bearing"""
    R = 6371000  # Earth radius in meters
    
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing_degrees)
    
    lat2_rad = math.asin(
        math.sin(lat_rad) * math.cos(distance_meters / R) +
        math.cos(lat_rad) * math.sin(distance_meters / R) * math.cos(bearing_rad)
    )
    
    lon2_rad = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(distance_meters / R) * math.cos(lat_rad),
        math.cos(distance_meters / R) - math.sin(lat_rad) * math.sin(lat2_rad)
    )
    
    return math.degrees(lat2_rad), math.degrees(lon2_rad)


class TestGPSDialog:
    """Dialog for creating test GPS movement samples"""
    def __init__(self, parent, current_gps, test_node_location=None, node_info=None):
        self.parent = parent
        self.current_gps = current_gps  # (lat, lon)
        self.result = None
        self.test_node_location = test_node_location
        self.node_info = node_info  # {'id': node_id, 'name': name, 'samples': count}
        
        # If no test node location, place it at current location
        if self.test_node_location is None:
            self.test_node_location = current_gps
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Test GPS Movement Simulator")
        self.dialog.geometry("700x450")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self._create_widgets()
        self._populate_default_readings()
        
    def _create_widgets(self):
        # Node being tested
        if self.node_info:
            node_header = ttk.Frame(self.dialog, padding=10)
            node_header.pack(fill=tk.X)
            
            node_text = f"Testing Node: {self.node_info['name']} ({self.node_info['id']})"
            if self.node_info.get('samples', 0) > 0:
                node_text += f" - Current samples: {self.node_info['samples']}"
            
            ttk.Label(node_header, text=node_text,
                     font=('Arial', 11, 'bold'), foreground='blue').pack()
        
        # Instructions
        info_frame = ttk.Frame(self.dialog, padding=(10, 5, 10, 10))
        info_frame.pack(fill=tk.X)
        
        ttk.Label(info_frame, text="Create simulated GPS readings for testing position estimation",
                 font=('Arial', 10, 'bold')).pack()
        ttk.Label(info_frame, text="Default: 3 readings at 1 mile from test node at 0°, 160°, 245°",
                 font=('Arial', 9)).pack()
        
        # Node location info
        node_frame = ttk.LabelFrame(self.dialog, text="Test Node Location", padding=10)
        node_frame.pack(fill=tk.X, padx=10, pady=5)
        
        node_loc_frame = ttk.Frame(node_frame)
        node_loc_frame.pack()
        ttk.Label(node_loc_frame, text=f"Lat: {self.test_node_location[0]:.6f}°  "
                                  f"Lon: {self.test_node_location[1]:.6f}°").pack()
        
        # Readings frame
        readings_frame = ttk.LabelFrame(self.dialog, text="Simulated Readings", padding=10)
        readings_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Headers
        header_frame = ttk.Frame(readings_frame)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(header_frame, text="Reading", width=8).grid(row=0, column=0, padx=2)
        ttk.Label(header_frame, text="Latitude", width=12).grid(row=0, column=1, padx=2)
        ttk.Label(header_frame, text="Longitude", width=12).grid(row=0, column=2, padx=2)
        ttk.Label(header_frame, text="RSSI (dBm)", width=10).grid(row=0, column=3, padx=2)
        ttk.Label(header_frame, text="Distance", width=10).grid(row=0, column=4, padx=2)
        
        # Create 3 reading rows
        self.reading_entries = []
        for i in range(3):
            row_frame = ttk.Frame(readings_frame)
            row_frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(row_frame, text=f"#{i+1}", width=8).grid(row=0, column=0, padx=2)
            
            lat_entry = ttk.Entry(row_frame, width=12)
            lat_entry.grid(row=0, column=1, padx=2)
            
            lon_entry = ttk.Entry(row_frame, width=12)
            lon_entry.grid(row=0, column=2, padx=2)
            
            rssi_entry = ttk.Entry(row_frame, width=10)
            rssi_entry.grid(row=0, column=3, padx=2)
            
            dist_label = ttk.Label(row_frame, text="", width=10)
            dist_label.grid(row=0, column=4, padx=2)
            
            self.reading_entries.append({
                'lat': lat_entry,
                'lon': lon_entry,
                'rssi': rssi_entry,
                'dist_label': dist_label
            })
        
        # Buttons
        button_frame = ttk.Frame(self.dialog, padding=10)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Random Shift Node", 
                  command=self._random_shift).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear All Readings", 
                  command=self._clear_readings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Create Readings", 
                  command=self._create_readings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
        
    def _populate_default_readings(self):
        """Create default readings at 1 mile distance at specific bearings"""
        mile_in_meters = 1609.34
        bearings = [0, 160, 245]
        
        for i, bearing in enumerate(bearings):
            # Calculate GPS position 1 mile from test node
            lat, lon = calculate_destination(
                self.test_node_location[0], 
                self.test_node_location[1],
                mile_in_meters,
                bearing
            )
            
            # Calculate distance from current GPS
            dist = calculate_distance(
                self.current_gps[0], self.current_gps[1],
                lat, lon
            )
            
            # Default RSSI at 1 mile (~50% signal, assuming -100 dBm range)
            rssi = -95
            
            self.reading_entries[i]['lat'].insert(0, f"{lat:.6f}")
            self.reading_entries[i]['lon'].insert(0, f"{lon:.6f}")
            self.reading_entries[i]['rssi'].insert(0, str(rssi))
            self.reading_entries[i]['dist_label'].config(text=format_distance(dist))
    
    def _random_shift(self):
        """Randomly shift test node location by up to 0.5 miles and regenerate readings"""
        import random
        
        # Shift node up to 0.5 miles in random direction
        shift_distance = random.uniform(0, 804.67)  # 0-0.5 miles in meters
        shift_bearing = random.uniform(0, 360)
        
        new_lat, new_lon = calculate_destination(
            self.test_node_location[0],
            self.test_node_location[1],
            shift_distance,
            shift_bearing
        )
        
        self.test_node_location = (new_lat, new_lon)
        
        # Clear existing entries
        for entry_set in self.reading_entries:
            entry_set['lat'].delete(0, tk.END)
            entry_set['lon'].delete(0, tk.END)
            entry_set['rssi'].delete(0, tk.END)
        
        # Regenerate readings with adjusted RSSI based on new distances
        mile_in_meters = 1609.34
        bearings = [random.uniform(0, 360) for _ in range(3)]
        
        for i, bearing in enumerate(bearings):
            # Random distance between 0.5 and 1.5 miles
            reading_distance = random.uniform(804.67, 2414.01)
            
            lat, lon = calculate_destination(
                self.test_node_location[0],
                self.test_node_location[1],
                reading_distance,
                bearing
            )
            
            dist = calculate_distance(
                self.current_gps[0], self.current_gps[1],
                lat, lon
            )
            
            # Adjust RSSI based on distance (roughly -6dB per doubling of distance)
            base_rssi = -90
            distance_factor = reading_distance / mile_in_meters
            rssi = int(base_rssi - (20 * math.log10(distance_factor)))
            rssi = max(-120, min(-60, rssi))  # Clamp to reasonable range
            
            self.reading_entries[i]['lat'].insert(0, f"{lat:.6f}")
            self.reading_entries[i]['lon'].insert(0, f"{lon:.6f}")
            self.reading_entries[i]['rssi'].insert(0, str(rssi))
            self.reading_entries[i]['dist_label'].config(text=format_distance(dist))
    
    def _clear_readings(self):
        """Clear all reading entries"""
        for entry_set in self.reading_entries:
            entry_set['lat'].delete(0, tk.END)
            entry_set['lon'].delete(0, tk.END)
            entry_set['rssi'].delete(0, tk.END)
            entry_set['dist_label'].config(text="")
    
    def _create_readings(self):
        """Collect readings and close dialog"""
        readings = []
        for i, entry_set in enumerate(self.reading_entries):
            try:
                lat = float(entry_set['lat'].get())
                lon = float(entry_set['lon'].get())
                rssi = int(entry_set['rssi'].get())
                
                readings.append({
                    'gps_lat': lat,
                    'gps_lon': lon,
                    'rssi': rssi,
                    'snr': 5.0,  # Default SNR
                    'timestamp': time.time()
                })
            except ValueError as e:
                messagebox.showerror("Invalid Input", f"Reading #{i+1} has invalid values: {e}")
                return
        
        self.result = {
            'readings': readings,
            'test_node_location': self.test_node_location
        }
        self.dialog.destroy()


class MeshTrackerGUI:
    """Main GUI application"""
    
    def __init__(self, root, gps_port=2947, meshtastic_port=None, 
                 path_loss_exp=2.5, tx_power=14.0, freq_mhz=915.0):
        self.root = root
        self.root.title("Meshtastic Node Tracker")
        
        # Set reasonable window size (fits most screens)
        window_width = 1000
        window_height = 650
        
        # Center the window on screen
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(800, 500)  # Set minimum size
        
        self.gps_port = gps_port
        self.meshtastic_port = meshtastic_port
        self.path_loss_exp = path_loss_exp
        self.tx_power = tx_power
        self.freq_mhz = freq_mhz
        
        self.gps_data = GPSData()
        self.nodes: Dict[str, MeshNode] = {}
        self.selected_node: Optional[str] = None
        self.mesh_interface = None
        self.mesh_connected = False
        self.local_node_name = "Connecting..."
        self.running = True
        
        # Map markers
        self.tracker_marker = None
        self.target_marker = None
        self.last_marker_position = None  # Track last marker position to reduce flicker
        self.last_gps_position = None  # Track last valid GPS position for when fix is lost
        
        self.setup_gui()
        self.start_background_threads()
        
    def setup_gui(self):
        """Setup the GUI layout"""
        # Create menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Reconnect USB", command=self.reconnect_usb, accelerator="Ctrl+R")
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.quit_app, accelerator="Ctrl+Q")
        
        # Bind shortcuts
        self.root.bind('<Control-q>', lambda e: self.quit_app())
        self.root.bind('<Control-r>', lambda e: self.reconnect_usb())
        
        # Create main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel - Node list
        left_frame = ttk.LabelFrame(main_frame, text="Mesh Nodes", padding=10)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0, 5))
        left_frame.config(width=300)
        
        # Node list with scrollbar (limited to 5 lines)
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=False)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.node_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                        font=('Courier', 10), height=5)
        self.node_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.node_listbox.yview)
        
        self.node_listbox.bind('<<ListboxSelect>>', self.on_node_select)
        
        # Test GPS button
        test_button_frame = ttk.Frame(left_frame)
        test_button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(test_button_frame, text="Test GPS Movement",
                  command=self.open_test_gps_dialog).pack(fill=tk.X)
        
        # Right panel - Tracking view
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Top: Info panel
        info_frame = ttk.LabelFrame(right_frame, text="Tracking Information", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        self.info_text = scrolledtext.ScrolledText(info_frame, height=8, 
                                                    font=('Courier', 9),
                                                    wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True)
        
        # Bottom row: Traffic logs on left, map on right
        bottom_frame = ttk.Frame(right_frame)
        bottom_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Left side of bottom: stacked logs
        logs_frame = ttk.Frame(bottom_frame)
        logs_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Mesh traffic log
        traffic_frame = ttk.LabelFrame(logs_frame, text="Mesh Traffic", padding=5)
        traffic_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        self.traffic_text = scrolledtext.ScrolledText(traffic_frame, height=6, 
                                                       font=('Courier', 8),
                                                       wrap=tk.WORD,
                                                       state='disabled')
        self.traffic_text.pack(fill=tk.BOTH, expand=True)
        
        # Calculation progress log
        calc_frame = ttk.LabelFrame(logs_frame, text="Position Calculation Progress", padding=5)
        calc_frame.pack(fill=tk.BOTH, expand=True)
        
        self.calc_text = scrolledtext.ScrolledText(calc_frame, height=6, 
                                                    font=('Courier', 8),
                                                    wrap=tk.WORD,
                                                    state='disabled')
        self.calc_text.pack(fill=tk.BOTH, expand=True)
        
        # Right side of bottom: Square map (fixed size)
        map_frame = ttk.LabelFrame(bottom_frame, text="Map View", padding=5)
        map_frame.pack(side=tk.RIGHT, fill=tk.NONE, expand=False)
        
        # Create map widget with fixed square dimensions
        self.map_widget = tkintermapview.TkinterMapView(map_frame, width=400, height=400, corner_radius=0)
        self.map_widget.pack()
        
        # Set default position (will be updated with GPS)
        self.map_widget.set_position(37.7749, -122.4194)
        self.map_widget.set_zoom(15)
        
        # Bottom: Status bar
        status_frame = ttk.Frame(right_frame)
        status_frame.pack(fill=tk.X)
        
        self.status_label = ttk.Label(status_frame, text="Initializing...", 
                                      font=('Arial', 9))
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        # Update timer - delay initial update to allow connection threads to start
        # First update will happen after 2 seconds
        self.root.after(2000, self.update_display)
        
    def start_background_threads(self):
        """Start GPS and Meshtastic receiver threads"""
        gps_thread = threading.Thread(target=self.gps_receiver_thread, daemon=True)
        gps_thread.start()
        
        mesh_thread = threading.Thread(target=self.mesh_receiver_thread, daemon=True)
        mesh_thread.start()
        
    def gps_receiver_thread(self):
        """Receive GPS data via UDP"""
        print(f"[DEBUG] Starting GPS receiver on port {self.gps_port}")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind(('', self.gps_port))
            sock.settimeout(1.0)
            print(f"[DEBUG] GPS receiver bound to port {self.gps_port}")
        except Exception as e:
            print(f"[ERROR] Failed to bind GPS port {self.gps_port}: {e}")
            print(f"[INFO] Will continue without GPS - check if gpsd forwarder is running")
            return
        
        while self.running:
            try:
                data, _ = sock.recvfrom(1024)
                raw_data = data.decode().strip()
                
                # Skip empty data
                if not raw_data:
                    continue
                
                # Check if it's NMEA format (starts with $)
                if raw_data.startswith('$'):
                    self.parse_nmea_sentence(raw_data)
                else:
                    # Try JSON format
                    try:
                        nmea_data = json.loads(raw_data)
                        self.gps_data.update_from_nmea(nmea_data)
                    except json.JSONDecodeError:
                        continue
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[ERROR] GPS error: {e}")
                time.sleep(1)
                
    def parse_nmea_sentence(self, sentence: str):
        """Parse NMEA sentence and update GPS data"""
        try:
            parts = sentence.split(',')
            sentence_type = parts[0]
            
            # GGA - Fix data
            if sentence_type == '$GPGGA' or sentence_type == '$GNGGA':
                if len(parts) >= 10:
                    # parts[1] = time
                    # parts[2] = latitude, parts[3] = N/S
                    # parts[4] = longitude, parts[5] = E/W
                    # parts[6] = fix quality
                    # parts[7] = satellites
                    # parts[9] = altitude
                    
                    if parts[6] in ['1', '2']:  # Valid fix
                        lat = parse_nmea_coordinate(parts[2], parts[3])
                        lon = parse_nmea_coordinate(parts[4], parts[5])
                        
                        if lat and lon:
                            self.gps_data.latitude = lat
                            self.gps_data.longitude = lon
                            self.gps_data.fix = True
                            
                            try:
                                self.gps_data.satellites = int(parts[7])
                            except:
                                pass
                                
                            try:
                                alt_m = float(parts[9])
                                self.gps_data.altitude = alt_m * 3.28084  # m to ft
                            except:
                                pass
                                
                            print(f"[DEBUG] GPS Fix: {lat:.6f}, {lon:.6f}, Sats: {parts[7]}")
            
            # RMC - Recommended minimum
            elif sentence_type == '$GPRMC' or sentence_type == '$GNRMC':
                if len(parts) >= 8:
                    # parts[2] = status (A=valid, V=invalid)
                    # parts[3] = latitude, parts[4] = N/S
                    # parts[5] = longitude, parts[6] = E/W
                    # parts[7] = speed in knots
                    
                    if parts[2] == 'A':  # Valid
                        lat = parse_nmea_coordinate(parts[3], parts[4])
                        lon = parse_nmea_coordinate(parts[5], parts[6])
                        
                        if lat and lon:
                            self.gps_data.latitude = lat
                            self.gps_data.longitude = lon
                            self.gps_data.fix = True
                            
                            try:
                                speed_knots = float(parts[7])
                                self.gps_data.speed = speed_knots * 1.15078  # knots to mph
                            except:
                                pass
                                
        except Exception as e:
            print(f"[DEBUG] NMEA parse error: {e}")
                
    def connect_meshtastic(self):
        """Connect or reconnect to Meshtastic device"""
        try:
            if meshtastic is None:
                print("[WARNING] Meshtastic library not available")
                return False
                
            print(f"[DEBUG] Connecting to Meshtastic port: {self.meshtastic_port or 'auto-detect'}")
            
            # Subscribe to packets using pubsub BEFORE creating interface
            # This must be done before the interface is created to catch all packets
            from pubsub import pub
            
            # Only subscribe once - check if already subscribed
            if not hasattr(self, '_pubsub_subscribed'):
                pub.subscribe(self._packet_handler_callback, "meshtastic.receive")
                self._pubsub_subscribed = True
                print("[DEBUG] Meshtastic packet handler registered via pubsub")
            
            # Close existing connection if any
            if self.mesh_interface:
                try:
                    print("[DEBUG] Closing existing Meshtastic connection...")
                    self.mesh_interface.close()
                except:
                    pass
                self.mesh_interface = None
                self.mesh_connected = False
                self.local_node_name = "Not Connected"
            
            # Attempt new connection
            try:
                if self.meshtastic_port:
                    self.mesh_interface = meshtastic.serial_interface.SerialInterface(self.meshtastic_port)
                else:
                    self.mesh_interface = meshtastic.serial_interface.SerialInterface()
            except Exception as conn_error:
                error_str = str(conn_error)
                print(f"[WARNING] Could not connect to Meshtastic: {error_str}")
                self.log_traffic(f"✗ USB connection failed: {error_str}")
                
                # Check for common errors
                if "Permission denied" in error_str:
                    self.log_traffic("Hint: Add user to 'dialout' group: sudo usermod -a -G dialout $USER")
                elif "No such file" in error_str or "cannot find" in error_str.lower():
                    self.log_traffic("Hint: Device unplugged or wrong port specified")
                elif "busy" in error_str.lower() or "in use" in error_str.lower() or "exclusively lock" in error_str.lower():
                    self.log_traffic("Hint: Close other apps using the device (meshtastic CLI, etc.)")
                    
                    # Check if device is hung/frozen (timeout errors)
                    device_port = self.meshtastic_port if self.meshtastic_port else "/dev/ttyUSB0"
                    if check_device_timeout_errors(device_port):
                        error_msg = (
                            "⚠️ DEVICE TIMEOUT DETECTED ⚠️\n\n"
                            "Your Meshtastic device appears to be frozen/hung.\n"
                            "The USB-to-serial chip is not responding (ETIMEDOUT error).\n\n"
                            "TO FIX THIS:\n"
                            "1. Unplug the Meshtastic USB cable\n"
                            "2. Wait 5 seconds\n"
                            "3. Plug it back in\n"
                            "4. Close this window and restart the application\n\n"
                            "The device needs a hardware reset to recover."
                        )
                        self.log_traffic("⚠️ Device appears frozen - unplug and replug USB cable!")
                        print(f"[ERROR] {error_msg}")
                        
                        # Show popup dialog
                        self.root.after(100, lambda: messagebox.showwarning(
                            "Meshtastic Device Frozen",
                            error_msg
                        ))
                    else:
                        self.log_traffic("Hint: If problem persists, try unplugging and replugging the USB cable")
                
                return False
            
            print("[DEBUG] Meshtastic connected, waiting for nodeDB...")
            time.sleep(3)  # Wait for nodeDB to populate
            
            # Get local node info
            self.mesh_connected = True
            try:
                if hasattr(self.mesh_interface, 'myInfo') and self.mesh_interface.myInfo:
                    my_node_num = self.mesh_interface.myInfo.my_node_num
                    # Convert node number to hex ID format (e.g., !9e7656a8)
                    my_node_id = f'!{my_node_num:08x}'
                    print(f"[DEBUG] Local node: {my_node_id}")
                    
                    # Default to node ID, will be overridden if name found
                    self.local_node_name = my_node_id
                    
                    if my_node_id and my_node_id in self.mesh_interface.nodes:
                        my_node = self.mesh_interface.nodes[my_node_id]
                        print(f"[DEBUG] Found local node in nodeDB")
                        if hasattr(my_node, 'user') and my_node.user:
                            print(f"[DEBUG] Local node has user info")
                            if hasattr(my_node.user, 'longName') and my_node.user.longName:
                                self.local_node_name = my_node.user.longName
                                print(f"[DEBUG] Local node longName: {self.local_node_name}")
                            elif hasattr(my_node.user, 'shortName') and my_node.user.shortName:
                                self.local_node_name = my_node.user.shortName
                                print(f"[DEBUG] Local node shortName: {self.local_node_name}")
                            else:
                                print(f"[DEBUG] Local node user has no name, using ID: {my_node_id}")
                        else:
                            print(f"[DEBUG] Local node has no user info, using ID: {my_node_id}")
                    else:
                        print(f"[DEBUG] Local node {my_node_id} not found in nodeDB, using ID")
            except Exception as e:
                print(f"[DEBUG] Could not get local node name: {e}")
                import traceback
                traceback.print_exc()
            
            # Load existing nodes
            if self.mesh_interface and hasattr(self.mesh_interface, 'nodes'):
                print(f"[DEBUG] NodeDB has {len(self.mesh_interface.nodes)} nodes")
                for node_id, node_info in self.mesh_interface.nodes.items():
                    try:
                        print(f"[DEBUG] Found existing node: {node_id}")
                        # Create node objects for all nodes in database
                        if node_id not in self.nodes:
                            self.nodes[node_id] = MeshNode(node_id)
                            
                            # Set last_seen from nodeDB lastHeard time if available
                            if hasattr(node_info, 'lastHeard') and node_info.lastHeard:
                                try:
                                    self.nodes[node_id].last_seen = node_info.lastHeard.ToSeconds()
                                except:
                                    pass  # Keep default current time if conversion fails
                            
                            # Update with info from nodeDB - wrap in try/except
                            try:
                                if hasattr(node_info, 'user') and node_info.user:
                                    if hasattr(node_info.user, 'longName') and node_info.user.longName:
                                        self.nodes[node_id].long_name = node_info.user.longName
                                        print(f"[DEBUG] Set long_name for {node_id}: {node_info.user.longName}")
                                    if hasattr(node_info.user, 'shortName') and node_info.user.shortName:
                                        self.nodes[node_id].short_name = node_info.user.shortName
                                        print(f"[DEBUG] Set short_name for {node_id}: {node_info.user.shortName}")
                            except Exception as attr_error:
                                print(f"[DEBUG] Could not read user info for {node_id}: {attr_error}")
                    except Exception as e:
                        print(f"[ERROR] Failed to load node {node_id}: {e}")
                        continue
                
                print(f"[DEBUG] Loaded {len(self.nodes)} nodes from nodeDB")
                
                # Log summary of recent activity
                current_time = time.time()
                recent_count = sum(1 for n in self.nodes.values() if (current_time - n.last_seen) < 600)
                if recent_count > 0:
                    self.log_traffic(f"ℹ {recent_count} nodes heard in last 10 min")
                else:
                    self.log_traffic(f"ℹ No recent mesh activity detected")
            
            if self.mesh_interface:
                self.log_traffic(f"✓ USB connected: {self.local_node_name} ({len(self.nodes)} nodes loaded)")
                self.log_traffic(f"⟳ Listening for mesh packets...")
                # Update display immediately to show connected status
                if hasattr(self, 'root'):
                    self.root.after(100, self.update_display)
                return True
            
            return False
            
        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def check_usb_device(self):
        """Check if USB device is available"""
        import glob
        import os
        
        # Check for common USB serial device patterns
        usb_patterns = [
            '/dev/ttyUSB*',
            '/dev/ttyACM*',
            '/dev/cu.usbserial*',  # macOS
            '/dev/cu.usbmodem*'     # macOS
        ]
        
        for pattern in usb_patterns:
            devices = glob.glob(pattern)
            if devices:
                print(f"[DEBUG] Found USB device(s): {devices}")
                return True
        
        print("[DEBUG] No USB devices found")
        return False
    
    def open_test_gps_dialog(self):
        """Open dialog to create test GPS movement samples"""
        if not self.gps_data.fix:
            messagebox.showwarning("No GPS Fix", 
                                  "GPS must have a valid fix before creating test readings.")
            return
        
        if not self.selected_node:
            messagebox.showwarning("No Node Selected",
                                  "Please select a node from the list first.")
            return
        
        node = self.nodes.get(self.selected_node)
        if not node:
            return
        
        # Prepare node information for display
        node_name = node.long_name if node.long_name != "Unknown" else \
                   (node.short_name if node.short_name != "Unknown" else self.selected_node[-4:])
        node_info = {
            'id': self.selected_node,
            'name': node_name,
            'samples': len(node.estimation_samples)
        }
        
        # Use existing test node location if available, otherwise current GPS
        test_node_loc = getattr(self, '_test_node_location', None)
        if test_node_loc is None:
            test_node_loc = (self.gps_data.latitude, self.gps_data.longitude)
        
        dialog = TestGPSDialog(
            self.root,
            (self.gps_data.latitude, self.gps_data.longitude),
            test_node_loc,
            node_info
        )
        
        # Wait for dialog to close
        self.root.wait_window(dialog.dialog)
        
        # Process results if any
        if dialog.result:
            self._test_node_location = dialog.result['test_node_location']
            readings = dialog.result['readings']
            
            # Add readings to selected node
            for reading in readings:
                node.estimation_samples.append(reading)
            
            sample_count = len(readings)
            node_name = node.short_name if node.short_name != "Unknown" else self.selected_node[-4:]
            
            self.log_calc(f"TEST: Added {sample_count} simulated readings for {node_name}")
            self.log_calc(f"TEST: Test node at {self._test_node_location[0]:.6f}, {self._test_node_location[1]:.6f}")
            
            # Trigger position estimation if enough samples
            total_samples = len(node.estimation_samples)
            if total_samples >= 3:
                self.log_calc(f"{node_name}: 📍 Calculating position with {total_samples} samples...")
                self.estimate_node_position(node)
            else:
                self.log_calc(f"{node_name}: Need {3 - total_samples} more samples for estimation")
    
    def reconnect_usb(self):
        """Reconnect to Meshtastic USB device"""
        print("[DEBUG] Reconnect USB requested")
        self.log_traffic("Reconnecting USB...")
        
        # Update status bar immediately
        self.status_label.config(text="Reconnecting to USB...")
        
        # Check if USB device is available
        if not self.check_usb_device():
            error_msg = "No USB device found - check connection"
            self.log_traffic(error_msg)
            self.status_label.config(text=f"ERROR: {error_msg}")
            print("[WARNING] No USB device found")
            return
        
        # Run connection in separate thread to avoid blocking UI
        def reconnect_thread():
            success = self.connect_meshtastic()
            if success:
                print("[DEBUG] Reconnection successful")
                self.log_traffic(f"✓ USB connected: {self.local_node_name}")
                # Force immediate status update
                self.root.after(100, self.update_display)
            else:
                print("[DEBUG] Reconnection failed")
                error_msg = "USB reconnection failed - check device"
                self.log_traffic(error_msg)
                self.status_label.config(text=f"ERROR: {error_msg}")
        
        threading.Thread(target=reconnect_thread, daemon=True).start()
    
    def mesh_receiver_thread(self):
        """Receive Meshtastic packets"""
        print("[DEBUG] Starting Meshtastic receiver")
        try:
            self.connect_meshtastic()
        except Exception as e:
            print(f"[ERROR] Meshtastic thread error: {e}")
            print("[INFO] Continuing without Meshtastic connection")
            import traceback
            traceback.print_exc()
    
    def _packet_handler_callback(self, packet, interface):
        """Callback for pubsub mesh packet reception"""
        try:
            print(f"[DEBUG] Packet received: {packet.get('fromId', 'unknown')}")
            self.handle_mesh_packet(packet)
        except Exception as e:
            print(f"[ERROR] Packet handler exception: {e}")
            import traceback
            traceback.print_exc()
            
    def handle_mesh_packet(self, packet: dict):
        """Handle incoming Meshtastic packet"""
        try:
            node_id = packet.get('fromId', packet.get('from'))
            if not node_id:
                print(f"[DEBUG] Packet has no fromId: {packet.keys()}")
                return
            
            print(f"[DEBUG] Processing packet from {node_id}")
            
            if node_id not in self.nodes:
                print(f"[DEBUG] Creating new node: {node_id}")
                self.nodes[node_id] = MeshNode(node_id)
            
            node = self.nodes[node_id]
            
            # Update node name from mesh_interface if available
            if self.mesh_interface and hasattr(self.mesh_interface, 'nodes'):
                if node_id in self.mesh_interface.nodes:
                    try:
                        node_info = self.mesh_interface.nodes[node_id]
                        if hasattr(node_info, 'user') and node_info.user:
                            if hasattr(node_info.user, 'longName') and node.long_name == "Unknown":
                                node.long_name = node_info.user.longName
                            if hasattr(node_info.user, 'shortName') and node.short_name == "Unknown":
                                node.short_name = node_info.user.shortName
                                print(f"[DEBUG] Updated node {node_id} name: {node.short_name}")
                    except Exception as e:
                        pass
            
            # Update RSSI/SNR and track min/max
            rssi_str = ""
            if 'rxRssi' in packet:
                node.rssi = packet['rxRssi']
                
                # Track min/max RSSI
                if node.rssi_min is None or node.rssi < node.rssi_min:
                    node.rssi_min = node.rssi
                if node.rssi_max is None or node.rssi > node.rssi_max:
                    node.rssi_max = node.rssi
                
                # Estimate distance from RSSI
                estimated_dist = estimate_distance_from_rssi(node.rssi)
                node.estimated_distance = estimated_dist
                
                # Format distance string
                if estimated_dist < 1000:
                    dist_str = f"{estimated_dist:.0f}m"
                else:
                    dist_str = f"{estimated_dist/1000:.1f}km"
                
                rssi_str = f" RSSI:{node.rssi}dBm (min:{node.rssi_min}, max:{node.rssi_max}) ~{dist_str}"
                print(f"[DEBUG] Node {node_id} RSSI: {node.rssi} (min:{node.rssi_min}, max:{node.rssi_max}) Est.dist: {dist_str}")
                
            if 'rxSnr' in packet:
                node.snr = packet['rxSnr']
                print(f"[DEBUG] Node {node_id} SNR: {node.snr}")
            
            # Log packet
            node_name = node.short_name if node.short_name != "Unknown" else node_id[-4:]
            self.log_traffic(f"RX: {node_name}{rssi_str}")
            
            # Update node info
            node.update(packet, self.gps_data)
            
            # If node has its own GPS position, use it directly
            if node.latitude is not None and node.longitude is not None:
                node.estimated_position = (node.latitude, node.longitude)
                # Calculate distance if we have base station GPS
                if self.gps_data.fix:
                    distance = calculate_distance(
                        self.gps_data.latitude, self.gps_data.longitude,
                        node.latitude, node.longitude
                    )
                    distance_km = distance / 1000.0
                    if distance_km < 1.0:
                        distance_str = f"{distance:.0f}m"
                    else:
                        distance_str = f"{distance_km:.2f}km"
                    self.log_calc(f"{node_name}: Position {node.latitude:.6f}, {node.longitude:.6f} - Distance: {distance_str}")
                else:
                    self.log_calc(f"{node_name}: Using node's GPS position: {node.latitude:.6f}, {node.longitude:.6f}")
            # Otherwise collect RSSI samples for position estimation (requires moving base station)
            elif node.rssi and self.gps_data.fix:
                sample = {
                    'gps_lat': self.gps_data.latitude,
                    'gps_lon': self.gps_data.longitude,
                    'rssi': node.rssi,
                    'snr': node.snr if node.snr else 0,
                    'timestamp': time.time()
                }
                node.estimation_samples.append(sample)
                sample_count = len(node.estimation_samples)
                print(f"[DEBUG] Sample collected for {node_id}, total: {sample_count}")
                
                # Visual progress indicator
                progress_bar = "█" * min(sample_count, 10) + "░" * max(0, 10 - sample_count)
                self.log_calc(f"{node_name}: Sample {sample_count} [{progress_bar}] at ({self.gps_data.latitude:.6f}, {self.gps_data.longitude:.6f}) RSSI:{node.rssi}dBm")
                
                # Add movement suggestions
                if sample_count == 1:
                    self.log_calc(f"{node_name}: ✓ First sample! Now move 50-100m in a different direction")
                elif sample_count == 2:
                    self.log_calc(f"{node_name}: ✓ Two samples! Move to 3rd position (try forming a triangle)")
                
                if len(node.estimation_samples) > 200:
                    node.estimation_samples.pop(0)
                
                # Estimate position if we have enough samples
                if len(node.estimation_samples) >= 3:
                    print(f"[DEBUG] Estimating position for {node_id}")
                    self.log_calc(f"{node_name}: 📍 Calculating position with {sample_count} samples...")
                    self.estimate_node_position(node)
                elif sample_count < 3:
                    remaining = 3 - sample_count
                    self.log_calc(f"{node_name}: Need {remaining} more sample{'s' if remaining > 1 else ''} to start estimation")
            else:
                print(f"[DEBUG] Not collecting sample: RSSI={node.rssi}, GPS fix={self.gps_data.fix}")
                    
        except Exception as e:
            print(f"[ERROR] Packet handling error: {e}")
            import traceback
            traceback.print_exc()
            
    def estimate_node_position(self, node: MeshNode):
        """Estimate node position using trilateration"""
        try:
            samples = node.estimation_samples[-100:]  # Use recent samples
            node_name = node.short_name if node.short_name != "Unknown" else node.node_id[-4:]
            
            self.log_calc(f"{node_name}: Processing {len(samples)} samples for trilateration...")
            
            # Simple centroid method for now
            lats = [s['gps_lat'] for s in samples]
            lons = [s['gps_lon'] for s in samples]
            
            est_lat = np.mean(lats)
            est_lon = np.mean(lons)
            
            self.log_calc(f"{node_name}: Initial centroid estimate: {est_lat:.6f}, {est_lon:.6f}")
            
            # Initialize or update Kalman filter
            if not node.kalman_initialized:
                self.log_calc(f"{node_name}: Initializing Kalman filter...")
                node.init_kalman_filter(est_lat, est_lon, initial_uncertainty=50.0)
            
            if node.kalman_filter:
                node.kalman_filter.predict()
                z = np.array([est_lat, est_lon])
                node.kalman_filter.update(z)
                
                filtered_lat = node.kalman_filter.x[0]
                filtered_lon = node.kalman_filter.x[1]
                
                node.estimated_position = (filtered_lat, filtered_lon)
                
                # Calculate sample quality metrics
                rssi_values = [s['rssi'] for s in samples]
                avg_rssi = np.mean(rssi_values)
                std_rssi = np.std(rssi_values)
                
                # Determine confidence level
                confidence = "HIGH"
                if len(samples) < 5:
                    confidence = "LOW"
                elif len(samples) < 10:
                    confidence = "MEDIUM"
                elif std_rssi > 15:
                    confidence = "MEDIUM"  # High variance in signal
                
                self.log_calc(f"{node_name}: Position: {filtered_lat:.6f}, {filtered_lon:.6f}")
                self.log_calc(f"{node_name}: Confidence: {confidence} (RSSI avg:{avg_rssi:.0f}dBm, σ:{std_rssi:.1f}dB)")
                
                # Calculate distance and bearing if we have GPS
                if self.gps_data.fix:
                    dist = calculate_distance(
                        self.gps_data.latitude, self.gps_data.longitude,
                        filtered_lat, filtered_lon
                    )
                    bearing = calculate_bearing(
                        self.gps_data.latitude, self.gps_data.longitude,
                        filtered_lat, filtered_lon
                    )
                    compass = bearing_to_compass(bearing)
                    self.log_calc(f"{node_name}: 🎯 LOCATED! Distance: {format_distance(dist)}, Bearing: {bearing:.0f}° ({compass})")
                    
                    # Add improvement suggestions based on confidence
                    if confidence == "LOW":
                        self.log_calc(f"{node_name}: 💡 Collect {10-len(samples)} more samples for better accuracy")
                    elif confidence == "MEDIUM" and std_rssi > 15:
                        self.log_calc(f"{node_name}: 💡 High signal variance - try moving to more consistent locations")
                
                # Update map marker
                if node.node_id == self.selected_node:
                    self.update_target_position()
                    
        except Exception as e:
            print(f"Position estimation error: {e}")
            self.log_calc(f"ERROR: Position estimation failed - {e}")
            
    def update_tracker_position(self):
        """Update tracker (your) position on map"""
        if self.gps_data.fix:
            lat, lon = self.gps_data.latitude, self.gps_data.longitude
            
            # Only update marker if position changed significantly (>10 meters) or marker doesn't exist
            if self.last_marker_position:
                dist = calculate_distance(
                    self.last_marker_position[0], self.last_marker_position[1],
                    lat, lon
                )
                if dist < 10 and self.tracker_marker:  # Less than 10 meters, skip update
                    return
            
            print(f"[DEBUG] Updating tracker position: {lat}, {lon}")
            
            # Remove old marker
            if self.tracker_marker:
                self.tracker_marker.delete()
            
            # Add new marker
            self.tracker_marker = self.map_widget.set_marker(
                lat, lon, 
                text="📍 You",
                marker_color_circle="blue",
                marker_color_outside="darkblue"
            )
            self.last_marker_position = (lat, lon)
            self.last_gps_position = (lat, lon)  # Save last valid GPS position
            print(f"[DEBUG] Tracker marker placed at {lat}, {lon}")
            
            # Center map on first fix
            if not hasattr(self, '_map_centered'):
                self.map_widget.set_position(lat, lon)
                self._map_centered = True
                print(f"[DEBUG] Map centered on GPS position")
                
    def update_target_position(self):
        """Update target node position on map"""
        if not self.selected_node:
            print(f"[DEBUG] No node selected")
            return
            
        node = self.nodes.get(self.selected_node)
        if not node or not node.estimated_position:
            print(f"[DEBUG] Node {self.selected_node} has no estimated position")
            return
            
        target_lat, target_lon = node.estimated_position
        print(f"[DEBUG] Updating target position: {target_lat}, {target_lon}")
        
        # Remove old marker
        if self.target_marker:
            self.target_marker.delete()
        
        # Add new marker
        self.target_marker = self.map_widget.set_marker(
            target_lat, target_lon,
            text=f"🎯 {node.short_name}",
            marker_color_circle="red",
            marker_color_outside="darkred"
        )
        print(f"[DEBUG] Target marker placed at {target_lat}, {target_lon}")
        
        # Scale map to fit both markers
        # Use current GPS position if available, otherwise use last recorded position
        tracker_lat, tracker_lon = None, None
        if self.gps_data.fix:
            tracker_lat = self.gps_data.latitude
            tracker_lon = self.gps_data.longitude
        elif self.last_gps_position:
            tracker_lat, tracker_lon = self.last_gps_position
            print(f"[DEBUG] Using last recorded GPS position: {tracker_lat}, {tracker_lon}")
        
        if tracker_lat and tracker_lon:
            # Calculate bounding box
            min_lat = min(tracker_lat, target_lat)
            max_lat = max(tracker_lat, target_lat)
            min_lon = min(tracker_lon, target_lon)
            max_lon = max(tracker_lon, target_lon)
            
            # Add 20% padding to the bounding box
            lat_padding = (max_lat - min_lat) * 0.2
            lon_padding = (max_lon - min_lon) * 0.2
            
            # Ensure minimum padding (about 100 meters)
            if lat_padding < 0.001:  # ~111 meters
                lat_padding = 0.001
            if lon_padding < 0.001:
                lon_padding = 0.001
            
            # Set map to fit both markers
            self.map_widget.fit_bounding_box(
                (max_lat + lat_padding, min_lon - lon_padding),  # top-left
                (min_lat - lat_padding, max_lon + lon_padding)   # bottom-right
            )
            print(f"[DEBUG] Map scaled to fit tracker and target")
        
    def on_node_select(self, event):
        """Handle node selection from list"""
        selection = self.node_listbox.curselection()
        if not selection:
            return
            
        index = selection[0]
        # Get nodes sorted by RSSI (same as display)
        nodes_with_rssi = [(node_id, node) for node_id, node in self.nodes.items() if node.rssi is not None]
        sorted_nodes = sorted(nodes_with_rssi, key=lambda x: x[1].rssi, reverse=True)
        top_nodes = sorted_nodes[:5]
        
        if index < len(top_nodes):
            self.selected_node = top_nodes[index][0]
            node = self.nodes.get(self.selected_node)
            if node:
                print(f"[DEBUG] Node selected: {self.selected_node}, short_name={node.short_name}, long_name={node.long_name}")
            else:
                print(f"[DEBUG] Node selected: {self.selected_node}")
            self.update_target_position()
            # Update info panel immediately
            if self.selected_node in self.nodes:
                node = self.nodes[self.selected_node]
                info = self.get_node_info(node)
                self.info_text.delete('1.0', tk.END)
                self.info_text.insert('1.0', info)
            
    def update_display(self):
        """Update the display periodically"""
        try:
            # Update tracker position on map (will only update if moved >10m)
            self.update_tracker_position()
            
            # Update node list - show top 5 by signal strength
            self.node_listbox.delete(0, tk.END)
            node_count = len(self.nodes)
            print(f"[DEBUG] Updating display, {node_count} nodes")
            
            # Sort by RSSI (strongest signal first), filter out nodes without RSSI
            nodes_with_rssi = [(node_id, node) for node_id, node in self.nodes.items() if node.rssi is not None]
            sorted_nodes = sorted(nodes_with_rssi, key=lambda x: x[1].rssi, reverse=True)
            
            # Show only top 5
            top_nodes = sorted_nodes[:5]
            
            for node_id, node in top_nodes:
                age = int(time.time() - node.last_seen)
                
                # Use long name if available, otherwise short name
                if node.long_name and node.long_name != "Unknown":
                    name = node.long_name[:20]  # Truncate if too long
                elif node.short_name != "Unknown":
                    name = node.short_name
                else:
                    name = node_id[-4:]
                
                # Format RSSI with distance estimate
                rssi_str = f"{node.rssi:4d}dBm"
                if node.estimated_distance:
                    if node.estimated_distance < 1000:
                        dist_str = f" ~{node.estimated_distance:.0f}m"
                    else:
                        dist_str = f" ~{node.estimated_distance/1000:.1f}km"
                    rssi_str += dist_str
                
                # Add sample indicator if collecting
                sample_indicator = ""
                if len(node.estimation_samples) > 0:
                    sample_indicator = f" [{len(node.estimation_samples)}📍]"
                
                display = f"{name:20s} {rssi_str:20s} {age:3d}s{sample_indicator}"
                self.node_listbox.insert(tk.END, display)
            
            # Update info panel
            if self.selected_node and self.selected_node in self.nodes:
                node = self.nodes[self.selected_node]
                info = self.get_node_info(node)
                self.info_text.delete('1.0', tk.END)
                self.info_text.insert('1.0', info)
            else:
                # Show GPS info when no node selected
                info = self.get_gps_info()
                self.info_text.delete('1.0', tk.END)
                self.info_text.insert('1.0', info)
            
            # Update status
            gps_status = "GPS: Fix" if self.gps_data.fix else "GPS: No Fix"
            node_count = len(self.nodes)
            mesh_status = f"USB: {self.local_node_name}" if self.mesh_connected else "USB: Disconnected"
            self.status_label.config(
                text=f"{gps_status} | {mesh_status} | Nodes: {node_count} | Selected: {self.selected_node or 'None'}"
            )
            
        except Exception as e:
            print(f"[ERROR] Display update error: {e}")
            import traceback
            traceback.print_exc()
        
        # Schedule next update (every 10 seconds)
        if self.running:
            self.root.after(10000, self.update_display)
        
    def get_node_info(self, node: MeshNode) -> str:
        """Get formatted node information"""
        info = []
        info.append("=" * 45)
        # Use short_name if long_name is Unknown, otherwise use node_id
        display_name = node.long_name
        if display_name == "Unknown":
            display_name = node.short_name if node.short_name != "Unknown" else node.node_id[-8:]
        info.append(f"TARGET: {display_name}")
        info.append("=" * 45)
        info.append("")
        
        if node.estimated_position:
            lat, lon = node.estimated_position
            info.append("*** ESTIMATED POSITION ***")
            info.append(f"Latitude:  {lat:.6f}°")
            info.append(f"Longitude: {lon:.6f}°")
            
            # Add confidence indicator
            num_samples = len(node.estimation_samples)
            if num_samples < 5:
                confidence = "LOW (need more samples)"
            elif num_samples < 10:
                confidence = "MEDIUM"
            else:
                confidence = "HIGH"
            info.append(f"Confidence: {confidence} ({num_samples} samples)")
            info.append("")
            
            if self.gps_data.fix:
                dist = calculate_distance(
                    self.gps_data.latitude, self.gps_data.longitude,
                    lat, lon
                )
                bearing = calculate_bearing(
                    self.gps_data.latitude, self.gps_data.longitude,
                    lat, lon
                )
                compass = bearing_to_compass(bearing)
                
                info.append("*** NAVIGATION ***")
                info.append(f"Distance:  {format_distance(dist)}")
                info.append(f"Bearing:   {bearing:.0f}° ({compass})")
                info.append("")
                
            # Add improvement suggestions
            if num_samples < 10:
                info.append("💡 TIP: Collect more samples to improve accuracy")
                info.append("   Move 50-100m in different directions")
                info.append("")
        else:
            info.append("*** POSITION NOT ESTIMATED ***")
            num_samples = len(node.estimation_samples)
            info.append(f"Samples collected: {num_samples}/3 minimum")
            
            if num_samples == 0:
                info.append("")
                info.append("📍 GETTING STARTED:")
                info.append("  1. Ensure GPS has a fix (see GPS tab)")
                info.append("  2. Wait for signal from this node")
                info.append("  3. Move to a new location (50m+)")
                info.append("  4. Wait for another signal")
                info.append("  5. Repeat for 3+ different positions")
            elif num_samples == 1:
                info.append("")
                info.append("✓ First sample collected!")
                info.append("")
                info.append("📍 NEXT STEPS:")
                info.append("  • Move at least 50 meters away")
                info.append("  • Try a different direction")
                info.append("  • Wait for next signal from this node")
                info.append(f"  • Need {3-num_samples} more samples minimum")
            elif num_samples == 2:
                info.append("")
                info.append("✓ Two samples collected!")
                info.append("")
                info.append("📍 ALMOST THERE:")
                info.append("  • Move to a 3rd different location")
                info.append("  • Form a triangle pattern for best results")
                info.append("  • Wait for next signal")
                info.append("  • Position will be estimated after 3rd sample")
            info.append("")
        
        info.append("Signal Quality:")
        if node.rssi:
            info.append(f"  RSSI: {node.rssi}dBm")
            # Add RSSI-based distance estimate
            if node.estimated_distance:
                if node.estimated_distance < 1000:
                    dist_str = f"{node.estimated_distance:.0f}m"
                else:
                    dist_str = f"{node.estimated_distance/1000:.1f}km"
                info.append(f"  Est. Range: ~{dist_str} (from signal strength)")
            # Show RSSI range if available
            if node.rssi_min and node.rssi_max:
                info.append(f"  RSSI Range: {node.rssi_min} to {node.rssi_max} dBm")
        else:
            info.append("  RSSI: N/A")
        info.append(f"  SNR: {node.snr:.1f}dB" if node.snr else "  SNR: N/A")
        info.append(f"  Last: {int(time.time() - node.last_seen)}s ago")
        info.append("")
        info.append(f"ID: {node.node_id}")
        info.append(f"Samples: {len(node.estimation_samples)}")
        info.append(f"Packets: {node.packet_count}")
        
        info.append("")
        info.append("Metrics:")
        info.append(f"  Samples: {node.metrics.get('num_samples', 0)}")
        if node.metrics.get('avg_rssi'):
            info.append(f"  Avg RSSI: {node.metrics['avg_rssi']:.1f}dBm")
        if node.metrics.get('std_rssi'):
            info.append(f"  RSSI Std: {node.metrics['std_rssi']:.1f}dBm")
        
        return '\n'.join(info)
        
    def get_gps_info(self) -> str:
        """Get formatted GPS information"""
        info = []
        info.append("GPS Tracker Status")
        info.append("=" * 40)
        info.append("")
        
        if self.gps_data.fix:
            info.append("GPS Status: LOCKED")
            info.append(f"Satellites: {self.gps_data.satellites or 'N/A'}")
            info.append("")
            info.append("Current Position:")
            info.append(f"  Latitude:  {self.gps_data.latitude:.6f}°")
            info.append(f"  Longitude: {self.gps_data.longitude:.6f}°")
            if self.gps_data.altitude:
                info.append(f"  Altitude:  {self.gps_data.altitude:.1f} ft")
            if self.gps_data.speed:
                info.append(f"  Speed:     {self.gps_data.speed:.1f} mph")
        else:
            info.append("GPS Status: SEARCHING...")
            info.append("")
            info.append("Waiting for GPS fix...")
            info.append("Make sure GPS device is connected")
            info.append("and has clear view of sky.")
        
        info.append("")
        info.append(f"Mesh Nodes: {len(self.nodes)}")
        if self.mesh_interface:
            info.append("Meshtastic: Connected")
        else:
            info.append("Meshtastic: Not connected")
        
        info.append("")
        info.append("=" * 40)
        info.append("Select a node from the list to track")
        
        return '\n'.join(info)
        
    def log_calc(self, message: str):
        """Log position calculation progress to the calc text area"""
        def _log():
            try:
                # Check if widget exists and is valid
                if not hasattr(self, 'calc_text') or not self.calc_text.winfo_exists():
                    return
                    
                timestamp = time.strftime("%H:%M:%S")
                log_entry = f"[{timestamp}] {message}\n"
                
                # Enable writing, insert at beginning, then disable
                self.calc_text.config(state='normal')
                self.calc_text.insert('1.0', log_entry)
                
                # Keep only last 50 lines
                lines = self.calc_text.get('1.0', tk.END).split('\n')
                if len(lines) > 50:
                    self.calc_text.delete(f'{50}.0', tk.END)
                
                self.calc_text.config(state='disabled')
                self.calc_text.see('1.0')  # Scroll to top
            except Exception as e:
                print(f"[ERROR] Log calc error: {e}")
        
        # Schedule on main thread if we have root
        if hasattr(self, 'root'):
            self.root.after(0, _log)
        else:
            _log()
        
    def log_traffic(self, message: str):
        """Log mesh traffic to the traffic text area"""
        def _log():
            try:
                # Check if widget exists and is valid
                if not hasattr(self, 'traffic_text') or not self.traffic_text.winfo_exists():
                    return
                    
                timestamp = time.strftime("%H:%M:%S")
                log_entry = f"[{timestamp}] {message}\n"
                
                # Enable writing, insert at beginning, then disable
                self.traffic_text.config(state='normal')
                self.traffic_text.insert('1.0', log_entry)
                
                # Keep only last 50 lines
                lines = self.traffic_text.get('1.0', tk.END).split('\n')
                if len(lines) > 50:
                    self.traffic_text.delete(f'{50}.0', tk.END)
                
                self.traffic_text.config(state='disabled')
                self.traffic_text.see('1.0')  # Scroll to top
            except Exception as e:
                print(f"[ERROR] Log traffic error: {e}")
        
        # Schedule on main thread if we have root
        if hasattr(self, 'root'):
            self.root.after(0, _log)
        else:
            _log()
        
    def quit_app(self):
        """Gracefully quit the application"""
        print("[DEBUG] Quit requested")
        self.cleanup()
        self.root.quit()
        self.root.destroy()
        
    def cleanup(self):
        """Cleanup on exit"""
        print("[DEBUG] Cleanup called")
        self.running = False
        if self.mesh_interface:
            try:
                self.mesh_interface.close()
                print("[DEBUG] Meshtastic interface closed")
            except:
                pass
        print("[DEBUG] Cleanup complete")


def main():
    """Main entry point"""
    print("[DEBUG] Starting Meshtastic Node Tracker GUI")
    parser = argparse.ArgumentParser(
        description='Meshtastic Node Tracker - GUI Version'
    )
    parser.add_argument('--gps-port', type=int, default=2947,
                        help='UDP port for GPS data (default: 2947)')
    parser.add_argument('--meshtastic-port', type=str,
                        help='Serial port for Meshtastic device')
    parser.add_argument('--path-loss', type=float, default=2.5,
                        help='Path loss exponent (default: 2.5)')
    parser.add_argument('--tx-power', type=float, default=14.0,
                        help='Transmit power in dBm (default: 14.0)')
    parser.add_argument('--freq', type=float, default=915.0,
                        help='Frequency in MHz (default: 915.0)')
    
    args = parser.parse_args()
    print(f"[DEBUG] GPS port: {args.gps_port}")
    print(f"[DEBUG] Meshtastic port: {args.meshtastic_port or 'auto-detect'}")
    
    root = tk.Tk()
    print("[DEBUG] Creating GUI application")
    app = MeshTrackerGUI(
        root,
        gps_port=args.gps_port,
        meshtastic_port=args.meshtastic_port,
        path_loss_exp=args.path_loss,
        tx_power=args.tx_power,
        freq_mhz=args.freq
    )
    
    def on_closing():
        print("[DEBUG] Window close requested")
        app.quit_app()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    print("[DEBUG] Starting GUI main loop")
    root.mainloop()
    print("[DEBUG] GUI closed")
    import sys
    sys.exit(0)


if __name__ == '__main__':
    main()
