#!/usr/bin/env python3
"""
Meshtastic Node Tracker with GPS - GUI Version
Windows-style GUI with embedded map for tracking mesh nodes
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import tkintermapview
import threading
import socket
import json
import time
import math
import argparse
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
        self.snr: Optional[float] = None
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.altitude: Optional[float] = None
        self.battery: Optional[int] = None
        self.packet_count: int = 0
        self.estimation_samples: List[dict] = []
        self.estimated_position: Optional[Tuple[float, float]] = None
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


class MeshTrackerGUI:
    """Main GUI application"""
    
    def __init__(self, root, gps_port=2947, meshtastic_port=None, 
                 path_loss_exp=2.5, tx_power=14.0, freq_mhz=915.0):
        self.root = root
        self.root.title("Meshtastic Node Tracker")
        self.root.geometry("1200x800")
        
        self.gps_port = gps_port
        self.meshtastic_port = meshtastic_port
        self.path_loss_exp = path_loss_exp
        self.tx_power = tx_power
        self.freq_mhz = freq_mhz
        
        self.gps_data = GPSData()
        self.nodes: Dict[str, MeshNode] = {}
        self.selected_node: Optional[str] = None
        self.mesh_interface = None
        self.running = True
        
        # Map markers
        self.tracker_marker = None
        self.target_marker = None
        
        self.setup_gui()
        self.start_background_threads()
        
    def setup_gui(self):
        """Setup the GUI layout"""
        # Create main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel - Node list
        left_frame = ttk.LabelFrame(main_frame, text="Mesh Nodes", padding=10)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        left_frame.config(width=300)
        
        # Node list with scrollbar
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.node_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                        font=('Courier', 10))
        self.node_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.node_listbox.yview)
        
        self.node_listbox.bind('<<ListboxSelect>>', self.on_node_select)
        
        # Right panel - Tracking view
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Top: Info panel
        info_frame = ttk.LabelFrame(right_frame, text="Tracking Information", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.info_text = scrolledtext.ScrolledText(info_frame, height=10, 
                                                    font=('Courier', 9),
                                                    wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True)
        
        # Middle: Map
        map_frame = ttk.LabelFrame(right_frame, text="Map View", padding=5)
        map_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Create map widget
        self.map_widget = tkintermapview.TkinterMapView(map_frame, corner_radius=0)
        self.map_widget.pack(fill=tk.BOTH, expand=True)
        
        # Set default position (will be updated with GPS)
        self.map_widget.set_position(37.7749, -122.4194)
        self.map_widget.set_zoom(15)
        
        # Bottom: Status bar
        status_frame = ttk.Frame(right_frame)
        status_frame.pack(fill=tk.X)
        
        self.status_label = ttk.Label(status_frame, text="Initializing...", 
                                      font=('Arial', 9))
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        # Update timer
        self.update_display()
        
    def start_background_threads(self):
        """Start GPS and Meshtastic receiver threads"""
        gps_thread = threading.Thread(target=self.gps_receiver_thread, daemon=True)
        gps_thread.start()
        
        mesh_thread = threading.Thread(target=self.mesh_receiver_thread, daemon=True)
        mesh_thread.start()
        
    def gps_receiver_thread(self):
        """Receive GPS data via UDP"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('', self.gps_port))
        sock.settimeout(1.0)
        
        while self.running:
            try:
                data, _ = sock.recvfrom(1024)
                nmea_data = json.loads(data.decode())
                self.gps_data.update_from_nmea(nmea_data)
                
                # Update map position if we have a fix
                if self.gps_data.fix:
                    self.update_tracker_position()
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"GPS error: {e}")
                time.sleep(1)
                
    def mesh_receiver_thread(self):
        """Receive Meshtastic packets"""
        try:
            if meshtastic is None:
                return
                
            if self.meshtastic_port:
                self.mesh_interface = meshtastic.serial_interface.SerialInterface(self.meshtastic_port)
            else:
                self.mesh_interface = meshtastic.serial_interface.SerialInterface()
            
            time.sleep(3)  # Wait for nodeDB to populate
            
            # Subscribe to packets
            def packet_handler(packet):
                self.handle_mesh_packet(packet)
            
            if self.mesh_interface:
                self.mesh_interface.on_receive = packet_handler
                
        except Exception as e:
            print(f"Meshtastic error: {e}")
            
    def handle_mesh_packet(self, packet: dict):
        """Handle incoming Meshtastic packet"""
        try:
            node_id = packet.get('fromId', packet.get('from'))
            if not node_id:
                return
            
            if node_id not in self.nodes:
                self.nodes[node_id] = MeshNode(node_id)
            
            node = self.nodes[node_id]
            
            # Update RSSI/SNR
            if 'rxRssi' in packet:
                node.rssi = packet['rxRssi']
            if 'rxSnr' in packet:
                node.snr = packet['rxSnr']
            
            # Update node info
            node.update(packet, self.gps_data)
            
            # Collect samples for position estimation
            if node.rssi and self.gps_data.fix:
                sample = {
                    'gps_lat': self.gps_data.latitude,
                    'gps_lon': self.gps_data.longitude,
                    'rssi': node.rssi,
                    'snr': node.snr if node.snr else 0,
                    'timestamp': time.time()
                }
                node.estimation_samples.append(sample)
                if len(node.estimation_samples) > 200:
                    node.estimation_samples.pop(0)
                
                # Estimate position if we have enough samples
                if len(node.estimation_samples) >= 10:
                    self.estimate_node_position(node)
                    
        except Exception as e:
            print(f"Packet handling error: {e}")
            
    def estimate_node_position(self, node: MeshNode):
        """Estimate node position using trilateration"""
        try:
            samples = node.estimation_samples[-100:]  # Use recent samples
            
            # Simple centroid method for now
            lats = [s['gps_lat'] for s in samples]
            lons = [s['gps_lon'] for s in samples]
            
            est_lat = np.mean(lats)
            est_lon = np.mean(lons)
            
            # Initialize or update Kalman filter
            if not node.kalman_initialized:
                node.init_kalman_filter(est_lat, est_lon, initial_uncertainty=50.0)
            
            if node.kalman_filter:
                node.kalman_filter.predict()
                z = np.array([est_lat, est_lon])
                node.kalman_filter.update(z)
                
                filtered_lat = node.kalman_filter.x[0]
                filtered_lon = node.kalman_filter.x[1]
                
                node.estimated_position = (filtered_lat, filtered_lon)
                
                # Update map marker
                if node.node_id == self.selected_node:
                    self.update_target_position()
                    
        except Exception as e:
            print(f"Position estimation error: {e}")
            
    def update_tracker_position(self):
        """Update tracker (your) position on map"""
        if self.gps_data.fix:
            lat, lon = self.gps_data.latitude, self.gps_data.longitude
            
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
            
            # Center map on first fix
            if not hasattr(self, '_map_centered'):
                self.map_widget.set_position(lat, lon)
                self._map_centered = True
                
    def update_target_position(self):
        """Update target node position on map"""
        if not self.selected_node:
            return
            
        node = self.nodes.get(self.selected_node)
        if not node or not node.estimated_position:
            return
            
        lat, lon = node.estimated_position
        
        # Remove old marker
        if self.target_marker:
            self.target_marker.delete()
        
        # Add new marker
        self.target_marker = self.map_widget.set_marker(
            lat, lon,
            text=f"🎯 {node.short_name}",
            marker_color_circle="red",
            marker_color_outside="darkred"
        )
        
    def on_node_select(self, event):
        """Handle node selection from list"""
        selection = self.node_listbox.curselection()
        if not selection:
            return
            
        index = selection[0]
        node_ids = list(self.nodes.keys())
        if index < len(node_ids):
            self.selected_node = node_ids[index]
            self.update_target_position()
            
    def update_display(self):
        """Update the display periodically"""
        try:
            # Update node list
            self.node_listbox.delete(0, tk.END)
            for node_id, node in sorted(self.nodes.items(), 
                                        key=lambda x: x[1].last_seen, 
                                        reverse=True):
                age = int(time.time() - node.last_seen)
                rssi = node.rssi if node.rssi else -999
                name = node.short_name if node.short_name != "Unknown" else node_id[-4:]
                
                display = f"{name:12s} {rssi:4d}dBm {age:3d}s"
                self.node_listbox.insert(tk.END, display)
            
            # Update info panel
            if self.selected_node and self.selected_node in self.nodes:
                node = self.nodes[self.selected_node]
                info = self.get_node_info(node)
                self.info_text.delete('1.0', tk.END)
                self.info_text.insert('1.0', info)
            
            # Update status
            gps_status = "GPS: Fix" if self.gps_data.fix else "GPS: No Fix"
            node_count = len(self.nodes)
            self.status_label.config(
                text=f"{gps_status} | Nodes: {node_count} | Selected: {self.selected_node or 'None'}"
            )
            
        except Exception as e:
            print(f"Display update error: {e}")
        
        # Schedule next update
        self.root.after(1000, self.update_display)
        
    def get_node_info(self, node: MeshNode) -> str:
        """Get formatted node information"""
        info = []
        info.append(f"Node: {node.long_name}")
        info.append(f"ID: {node.node_id}")
        info.append(f"Short Name: {node.short_name}")
        info.append("")
        
        info.append("Signal:")
        info.append(f"  RSSI: {node.rssi}dBm" if node.rssi else "  RSSI: N/A")
        info.append(f"  SNR: {node.snr:.1f}dB" if node.snr else "  SNR: N/A")
        info.append(f"  Last Seen: {int(time.time() - node.last_seen)}s ago")
        info.append(f"  Packets: {node.packet_count}")
        info.append("")
        
        if node.estimated_position:
            lat, lon = node.estimated_position
            info.append("Estimated Position:")
            info.append(f"  Lat: {lat:.6f}")
            info.append(f"  Lon: {lon:.6f}")
            
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
                
                info.append(f"  Distance: {format_distance(dist)}")
                info.append(f"  Bearing: {bearing:.0f}° ({compass})")
        else:
            info.append("Position: Not yet estimated")
            info.append(f"Samples: {len(node.estimation_samples)}/10")
        
        info.append("")
        info.append("Metrics:")
        info.append(f"  Samples: {node.metrics.get('num_samples', 0)}")
        if node.metrics.get('avg_rssi'):
            info.append(f"  Avg RSSI: {node.metrics['avg_rssi']:.1f}dBm")
        if node.metrics.get('std_rssi'):
            info.append(f"  RSSI Std: {node.metrics['std_rssi']:.1f}dBm")
        
        return '\n'.join(info)
        
    def cleanup(self):
        """Cleanup on exit"""
        self.running = False
        if self.mesh_interface:
            self.mesh_interface.close()


def main():
    """Main entry point"""
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
    
    root = tk.Tk()
    app = MeshTrackerGUI(
        root,
        gps_port=args.gps_port,
        meshtastic_port=args.meshtastic_port,
        path_loss_exp=args.path_loss,
        tx_power=args.tx_power,
        freq_mhz=args.freq
    )
    
    def on_closing():
        app.cleanup()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == '__main__':
    main()
