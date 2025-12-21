#!/usr/bin/env python3
"""
Automated tests for Mesh Tracker
Tests GPS functionality, node tracking, and display rendering
"""

import unittest
import time
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import the module to test
import mesh_tracker


class TestGPSData(unittest.TestCase):
    """Test GPS data handling"""
    
    def test_gps_data_initialization(self):
        """Test GPS data object initialization"""
        gps = mesh_tracker.GPSData()
        self.assertIsNone(gps.latitude)
        self.assertIsNone(gps.longitude)
        self.assertIsNone(gps.altitude)
        self.assertFalse(gps.fix)
    
    def test_gps_data_update(self):
        """Test GPS data updates from NMEA"""
        gps = mesh_tracker.GPSData()
        
        nmea_data = {
            'latitude': '35.968400',
            'longitude': '-115.081402',
            'altitude': '828.8',
            'satellites': '12'
        }
        
        gps.update_from_nmea(nmea_data)
        
        self.assertEqual(gps.latitude, 35.968400)
        self.assertEqual(gps.longitude, -115.081402)
        self.assertAlmostEqual(gps.altitude, 828.8 * 3.28084, places=1)  # Converted to feet
        self.assertEqual(gps.satellites, 12)
        self.assertTrue(gps.fix)
    
    def test_gps_data_invalid_values(self):
        """Test GPS data with invalid values"""
        gps = mesh_tracker.GPSData()
        
        nmea_data = {
            'latitude': 'n/a',
            'longitude': 'n/a',
            'altitude': 'n/a'
        }
        
        gps.update_from_nmea(nmea_data)
        
        self.assertIsNone(gps.latitude)
        self.assertIsNone(gps.longitude)
        self.assertFalse(gps.fix)


class TestMeshNode(unittest.TestCase):
    """Test Mesh Node handling"""
    
    def test_node_initialization(self):
        """Test node initialization"""
        node = mesh_tracker.MeshNode("!9e7656a8")
        
        self.assertEqual(node.node_id, "!9e7656a8")
        self.assertEqual(node.short_name, "Unknown")
        self.assertEqual(node.long_name, "Unknown")
        self.assertIsNone(node.rssi)
        self.assertEqual(node.packet_count, 0)
        self.assertEqual(len(node.signal_history), 0)
    
    def test_node_update(self):
        """Test node updates from packet"""
        node = mesh_tracker.MeshNode("!9e7656a8")
        node.rssi = -50  # Set RSSI before update
        initial_time = node.last_seen
        
        time.sleep(0.1)
        
        gps_data = mesh_tracker.GPSData()
        gps_data.latitude = 35.968400
        gps_data.longitude = -115.081402
        gps_data.fix = True
        
        packet = {'fromId': '!9e7656a8'}
        node.update(packet, gps_data)
        
        self.assertGreater(node.last_seen, initial_time)
        self.assertEqual(node.packet_count, 1)
        # Should have recorded signal history
        self.assertEqual(len(node.signal_history), 1)
        self.assertEqual(node.signal_history[0]['rssi'], -50)


class TestSignalTracking(unittest.TestCase):
    """Test signal tracking and hotter/colder functionality"""
    
    def test_signal_trend_insufficient_data(self):
        """Test signal trend with insufficient data"""
        node = mesh_tracker.MeshNode("!test")
        trend = node.get_signal_trend(10)
        self.assertIsNone(trend)
    
    def test_signal_trend_hotter(self):
        """Test signal getting stronger (hotter)"""
        node = mesh_tracker.MeshNode("!test")
        current_time = time.time()
        
        # Simulate signal getting stronger over time
        for i in range(10):
            node.signal_history.append({
                'timestamp': current_time + i,
                'rssi': -80 + (i * 2),  # Signal improving from -80 to -62
                'snr': 5.0,
                'latitude': 35.0,
                'longitude': -115.0
            })
        
        trend = node.get_signal_trend(10)
        self.assertEqual(trend, 'hotter')
    
    def test_signal_trend_colder(self):
        """Test signal getting weaker (colder)"""
        node = mesh_tracker.MeshNode("!test")
        current_time = time.time()
        
        # Simulate signal getting weaker over time
        for i in range(10):
            node.signal_history.append({
                'timestamp': current_time + i,
                'rssi': -60 - (i * 2),  # Signal degrading from -60 to -78
                'snr': 5.0,
                'latitude': 35.0,
                'longitude': -115.0
            })
        
        trend = node.get_signal_trend(10)
        self.assertEqual(trend, 'colder')
    
    def test_signal_trend_stable(self):
        """Test stable signal"""
        node = mesh_tracker.MeshNode("!test")
        current_time = time.time()
        
        # Simulate stable signal
        for i in range(10):
            node.signal_history.append({
                'timestamp': current_time + i,
                'rssi': -70,  # Constant signal
                'snr': 5.0,
                'latitude': 35.0,
                'longitude': -115.0
            })
        
        trend = node.get_signal_trend(10)
        self.assertEqual(trend, 'stable')
    
    def test_signal_strength_change(self):
        """Test signal strength change calculation"""
        node = mesh_tracker.MeshNode("!test")
        current_time = time.time()
        
        # Add signal samples
        for i in range(10):
            node.signal_history.append({
                'timestamp': current_time + i,
                'rssi': -80 + (i * 2),
                'snr': 5.0,
                'latitude': 35.0,
                'longitude': -115.0
            })
        
        change = node.get_signal_strength_change(10)
        self.assertIsNotNone(change)
        self.assertGreater(change, 0)  # Signal improved


class TestDistanceCalculations(unittest.TestCase):
    """Test distance and bearing calculations"""
    
    def test_distance_calculation(self):
        """Test Haversine distance calculation"""
        # Las Vegas to Los Angeles (approximately 370 km)
        lat1, lon1 = 36.1699, -115.1398  # Las Vegas
        lat2, lon2 = 34.0522, -118.2437  # Los Angeles
        
        distance = mesh_tracker.calculate_distance(lat1, lon1, lat2, lon2)
        
        # Should be approximately 370,000 meters (370 km)
        self.assertGreater(distance, 350000)
        self.assertLess(distance, 390000)
    
    def test_distance_same_location(self):
        """Test distance calculation for same location"""
        distance = mesh_tracker.calculate_distance(36.0, -115.0, 36.0, -115.0)
        self.assertAlmostEqual(distance, 0.0, places=1)
    
    def test_bearing_calculation(self):
        """Test bearing calculation"""
        # From Las Vegas to Los Angeles (roughly west)
        lat1, lon1 = 36.1699, -115.1398
        lat2, lon2 = 34.0522, -118.2437
        
        bearing = mesh_tracker.calculate_bearing(lat1, lon1, lat2, lon2)
        
        # Bearing should be roughly southwest (200-250 degrees)
        self.assertGreater(bearing, 200)
        self.assertLess(bearing, 250)
    
    def test_bearing_north(self):
        """Test bearing calculation for north direction"""
        bearing = mesh_tracker.calculate_bearing(36.0, -115.0, 37.0, -115.0)
        
        # Should be very close to 0 (north)
        self.assertLess(bearing, 5)
    
    def test_bearing_to_compass(self):
        """Test compass direction conversion"""
        self.assertEqual(mesh_tracker.bearing_to_compass(0), 'N')
        self.assertEqual(mesh_tracker.bearing_to_compass(90), 'E')
        self.assertEqual(mesh_tracker.bearing_to_compass(180), 'S')
        self.assertEqual(mesh_tracker.bearing_to_compass(270), 'W')
        self.assertEqual(mesh_tracker.bearing_to_compass(45), 'NE')
        self.assertEqual(mesh_tracker.bearing_to_compass(135), 'SE')
        self.assertEqual(mesh_tracker.bearing_to_compass(225), 'SW')
        self.assertEqual(mesh_tracker.bearing_to_compass(315), 'NW')


class TestDistanceFormatting(unittest.TestCase):
    """Test distance formatting"""
    
    def test_format_feet(self):
        """Test formatting distances in feet"""
        # 50 meters = 164.0 feet
        result = mesh_tracker.format_distance(50)
        self.assertTrue(result.endswith("ft"))
        self.assertIn("164", result)
    
    def test_format_miles(self):
        """Test formatting distances in miles"""
        # 2000 meters = 6561.7 feet = 1.24 miles
        result = mesh_tracker.format_distance(2000)
        self.assertTrue(result.endswith("mi"))
        # Should be around 1.2mi
        self.assertIn("1.", result)


class TestNMEAParsing(unittest.TestCase):
    """Test NMEA sentence parsing"""
    
    def setUp(self):
        """Set up test tracker"""
        self.tracker = mesh_tracker.MeshTracker(gps_port=2947)
    
    def test_parse_gpgga(self):
        """Test parsing GPGGA sentence"""
        sentence = "$GPGGA,123519,3558.104,N,11504.884,W,1,08,0.9,545.4,M,46.9,M,,*47"
        
        result = self.tracker.parse_nmea(sentence)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], '$GPGGA')
        self.assertIn('latitude', result)
        self.assertIn('longitude', result)
        self.assertEqual(result['satellites'], '08')
    
    def test_parse_gprmc(self):
        """Test parsing GPRMC sentence"""
        sentence = "$GPRMC,123519,A,3558.104,N,11504.884,W,022.4,084.4,230394,003.1,W*6A"
        
        result = self.tracker.parse_nmea(sentence)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], '$GPRMC')
        self.assertIn('latitude', result)
        self.assertIn('longitude', result)
        self.assertEqual(result['status'], 'A')
    
    def test_parse_invalid(self):
        """Test parsing invalid sentence"""
        sentence = "INVALID DATA"
        
        result = self.tracker.parse_nmea(sentence)
        
        self.assertIsNone(result)
    
    def test_coordinate_conversion(self):
        """Test NMEA coordinate to decimal conversion"""
        # NMEA: 3558.104,N = 35 degrees 58.104 minutes = 35.968400 degrees
        result = self.tracker.parse_coordinate('3558.104', 'N')
        self.assertAlmostEqual(float(result), 35.968, places=2)
        
        # NMEA: 11504.884,W = 115 degrees 4.884 minutes = -115.0814 degrees
        result = self.tracker.parse_coordinate('11504.884', 'W')
        self.assertAlmostEqual(float(result), -115.081, places=2)


class TestDataLogging(unittest.TestCase):
    """Test data logging functionality"""
    
    def setUp(self):
        """Set up test tracker"""
        self.tracker = mesh_tracker.MeshTracker(gps_port=2947)
        self.tracker.gps_data.latitude = 35.968400
        self.tracker.gps_data.longitude = -115.081402
        self.tracker.gps_data.fix = True
    
    def tearDown(self):
        """Clean up test log files"""
        import os
        if hasattr(self.tracker, 'log_file') and os.path.exists(self.tracker.log_file):
            os.remove(self.tracker.log_file)
    
    def test_log_gps_data(self):
        """Test logging GPS data"""
        test_data = {
            'type': '$GPGGA',
            'latitude': '35.968400',
            'longitude': '-115.081402'
        }
        
        self.tracker.log_data('gps', test_data)
        
        # Read back the log file
        with open(self.tracker.log_file, 'r') as f:
            log_entry = json.loads(f.readline())
        
        self.assertEqual(log_entry['type'], 'gps')
        self.assertEqual(log_entry['data'], test_data)
        self.assertIsNotNone(log_entry['gps_position'])
        self.assertEqual(log_entry['gps_position']['latitude'], 35.968400)
    
    def test_log_mesh_data(self):
        """Test logging mesh data"""
        test_packet = {
            'fromId': '!9e7656a8',
            'rssi': -94
        }
        
        self.tracker.log_data('mesh', test_packet)
        
        # Read back the log file
        with open(self.tracker.log_file, 'r') as f:
            log_entry = json.loads(f.readline())
        
        self.assertEqual(log_entry['type'], 'mesh')
        self.assertEqual(log_entry['data']['fromId'], '!9e7656a8')


class TestScreenRendering(unittest.TestCase):
    """Test screen rendering (visual inspection)"""
    
    def setUp(self):
        """Set up test tracker with mock data"""
        self.tracker = mesh_tracker.MeshTracker(gps_port=2947)
        
        # Set up GPS fix
        self.tracker.gps_data.latitude = 35.968400
        self.tracker.gps_data.longitude = -115.081402
        self.tracker.gps_data.altitude = 2718.8
        self.tracker.gps_data.satellites = 12
        self.tracker.gps_data.fix = True
        
        # Add some test nodes
        for i in range(5):
            node_id = f"!test{i:04d}"
            node = mesh_tracker.MeshNode(node_id)
            node.short_name = f"Node{i}"
            node.long_name = f"Test Node {i}"
            node.rssi = -90 - i
            node.snr = 5.0 + i
            node.packet_count = (i + 1) * 10
            node.latitude = 35.968400 + (i * 0.001)
            node.longitude = -115.081402 + (i * 0.001)
            self.tracker.nodes[node_id] = node
    
    def test_generate_node_list_view(self):
        """Test node list view generation"""
        layout = self.tracker.generate_node_list_view()
        
        # Should return a Layout object
        from rich.layout import Layout
        self.assertIsInstance(layout, Layout)
        
        # Print for visual inspection
        print("\n" + "="*80)
        print("NODE LIST VIEW TEST")
        print("="*80)
        from rich.console import Console
        console = Console()
        console.print(layout)
    
    def test_generate_tracking_view(self):
        """Test tracking view generation"""
        # Select first node for tracking
        self.tracker.selected_node = list(self.tracker.nodes.keys())[0]
        
        layout = self.tracker.generate_tracking_view()
        
        # Should return a Layout object
        from rich.layout import Layout
        self.assertIsInstance(layout, Layout)
        
        # Print for visual inspection
        print("\n" + "="*80)
        print("TRACKING VIEW TEST")
        print("="*80)
        from rich.console import Console
        console = Console()
        console.print(layout)
    
    def test_compass_visual(self):
        """Test compass visual generation"""
        # Test different bearings
        bearings = [0, 45, 90, 135, 180, 225, 270, 315]
        
        print("\n" + "="*80)
        print("COMPASS VISUAL TEST")
        print("="*80)
        
        for bearing in bearings:
            visual = self.tracker.create_compass_visual(bearing)
            direction = mesh_tracker.bearing_to_compass(bearing)
            print(f"{bearing:3d}° ({direction:3s}): {visual}")


class TestMeshPacketHandling(unittest.TestCase):
    """Test Meshtastic packet handling"""
    
    def setUp(self):
        """Set up test tracker"""
        self.tracker = mesh_tracker.MeshTracker(gps_port=2947)
    
    def test_handle_basic_packet(self):
        """Test handling basic mesh packet"""
        packet = {
            'fromId': '!9e7656a8',
            'rxRssi': -94,
            'rxSnr': 5.5
        }
        
        self.tracker.handle_mesh_packet(packet)
        
        self.assertIn('!9e7656a8', self.tracker.nodes)
        node = self.tracker.nodes['!9e7656a8']
        self.assertEqual(node.rssi, -94)
        self.assertEqual(node.snr, 5.5)
        self.assertEqual(node.packet_count, 1)
    
    def test_handle_packet_with_user_info(self):
        """Test handling packet with user information"""
        packet = {
            'fromId': '!9e7656a8',
            'user': {
                'shortName': 'Test',
                'longName': 'Test Node'
            }
        }
        
        self.tracker.handle_mesh_packet(packet)
        
        node = self.tracker.nodes['!9e7656a8']
        self.assertEqual(node.short_name, 'Test')
        self.assertEqual(node.long_name, 'Test Node')
    
    def test_handle_packet_with_position(self):
        """Test handling packet with position data"""
        packet = {
            'fromId': '!9e7656a8',
            'decoded': {
                'position': {
                    'latitude': 35.968400,
                    'longitude': -115.081402,
                    'altitude': 828
                }
            }
        }
        
        self.tracker.handle_mesh_packet(packet)
        
        node = self.tracker.nodes['!9e7656a8']
        self.assertEqual(node.latitude, 35.968400)
        self.assertEqual(node.longitude, -115.081402)
        self.assertEqual(node.altitude, 828)


class TestMovementDetection(unittest.TestCase):
    """Test Pi5 stationary detection and target node movement detection"""
    
    def setUp(self):
        """Set up test tracker"""
        self.tracker = mesh_tracker.MeshTracker(gps_port=2947)
        self.tracker.gps_data.fix = True
    
    def test_pi_stationary_insufficient_data(self):
        """Test stationary detection with insufficient data"""
        result = self.tracker.is_pi_stationary()
        self.assertFalse(result)
    
    def test_pi_stationary_true(self):
        """Test Pi5 is detected as stationary"""
        current_time = time.time()
        
        # Add GPS positions that are very close together (within 5 meters)
        # Using smaller increments to stay within 10 meters
        for i in range(10):
            self.tracker.gps_history.append({
                'timestamp': current_time + i,
                'latitude': 35.968400 + (i * 0.000001),  # ~0.1 meter apart
                'longitude': -115.081402
            })
        
        result = self.tracker.is_pi_stationary(time_window=60, max_movement_meters=10.0)
        self.assertTrue(result)
    
    def test_pi_moving(self):
        """Test Pi5 is detected as moving"""
        current_time = time.time()
        
        # Add GPS positions that are far apart (> 10 meters)
        for i in range(10):
            self.tracker.gps_history.append({
                'timestamp': current_time + i,
                'latitude': 35.968400 + (i * 0.0001),  # ~10+ meters apart
                'longitude': -115.081402
            })
        
        result = self.tracker.is_pi_stationary(time_window=60, max_movement_meters=10.0)
        self.assertFalse(result)
    
    def test_target_node_moving(self):
        """Test target node detected as moving when Pi is stationary"""
        current_time = time.time()
        node = mesh_tracker.MeshNode("!test")
        
        # Set up Pi as stationary
        for i in range(10):
            self.tracker.gps_history.append({
                'timestamp': current_time + i,
                'latitude': 35.968400,
                'longitude': -115.081402
            })
        
        # Add node signal history with changing signal (node moving)
        for i in range(10):
            node.signal_history.append({
                'timestamp': current_time + i,
                'rssi': -80 + (i * 2),  # Signal changing significantly
                'snr': 5.0,
                'latitude': 35.968400,
                'longitude': -115.081402
            })
        
        result = self.tracker.is_target_node_moving(node, 60)
        self.assertEqual(result, 'moving')
    
    def test_target_node_stationary(self):
        """Test target node detected as stationary when Pi is stationary"""
        current_time = time.time()
        node = mesh_tracker.MeshNode("!test")
        
        # Set up Pi as stationary
        for i in range(10):
            self.tracker.gps_history.append({
                'timestamp': current_time + i,
                'latitude': 35.968400,
                'longitude': -115.081402
            })
        
        # Add node signal history with stable signal (node stationary)
        for i in range(10):
            node.signal_history.append({
                'timestamp': current_time + i,
                'rssi': -70,  # Stable signal
                'snr': 5.0,
                'latitude': 35.968400,
                'longitude': -115.081402
            })
        
        result = self.tracker.is_target_node_moving(node, 60)
        self.assertEqual(result, 'stationary')
    
    def test_target_node_unknown_both_moving(self):
        """Test can't determine target node status when both are moving"""
        current_time = time.time()
        node = mesh_tracker.MeshNode("!test")
        
        # Set up Pi as moving
        for i in range(10):
            self.tracker.gps_history.append({
                'timestamp': current_time + i,
                'latitude': 35.968400 + (i * 0.0001),  # Moving
                'longitude': -115.081402
            })
        
        # Add node signal history
        for i in range(10):
            node.signal_history.append({
                'timestamp': current_time + i,
                'rssi': -70 + i,
                'snr': 5.0,
                'latitude': 35.968400,
                'longitude': -115.081402
            })
        
        result = self.tracker.is_target_node_moving(node, 60)
        self.assertIsNone(result)  # Can't determine


def run_tests():
    """Run all tests"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestGPSData))
    suite.addTests(loader.loadTestsFromTestCase(TestMeshNode))
    suite.addTests(loader.loadTestsFromTestCase(TestSignalTracking))
    suite.addTests(loader.loadTestsFromTestCase(TestDistanceCalculations))
    suite.addTests(loader.loadTestsFromTestCase(TestDistanceFormatting))
    suite.addTests(loader.loadTestsFromTestCase(TestNMEAParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestDataLogging))
    suite.addTests(loader.loadTestsFromTestCase(TestScreenRendering))
    suite.addTests(loader.loadTestsFromTestCase(TestMeshPacketHandling))
    suite.addTests(loader.loadTestsFromTestCase(TestMovementDetection))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    print("="*80)
    print("MESH TRACKER AUTOMATED TESTS")
    print("="*80)
    result = run_tests()
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✓ ALL TESTS PASSED!")
        exit(0)
    else:
        print("\n✗ SOME TESTS FAILED")
        exit(1)
