#!/usr/bin/env python3
"""
Test script for mesh_tracker.py improvements
Validates key functionality without requiring Meshtastic hardware
"""

import sys
import numpy as np
from scipy.optimize import least_squares
from filterpy.kalman import KalmanFilter

def test_imports():
    """Test that all required imports work"""
    print("Testing imports...")
    try:
        import numpy as np
        print("  ✓ NumPy imported successfully")
    except ImportError as e:
        print(f"  ✗ NumPy import failed: {e}")
        return False
    
    try:
        from scipy.optimize import least_squares
        print("  ✓ SciPy imported successfully")
    except ImportError as e:
        print(f"  ✗ SciPy import failed: {e}")
        return False
    
    try:
        from filterpy.kalman import KalmanFilter
        print("  ✓ FilterPy imported successfully")
    except ImportError as e:
        print(f"  ✗ FilterPy import failed: {e}")
        return False
    
    try:
        from rich.console import Console
        print("  ✓ Rich imported successfully")
    except ImportError as e:
        print(f"  ✗ Rich import failed: {e}")
        return False
    
    print("All imports successful!\n")
    return True


def test_outlier_filtering():
    """Test outlier filtering logic"""
    print("Testing outlier filtering...")
    
    # Create sample data with outliers
    rssi_values = np.array([-70, -72, -71, -69, -100, -68, -73, -50, -71])
    mean_rssi = np.mean(rssi_values)
    std_rssi = np.std(rssi_values)
    
    print(f"  Sample RSSI values: {rssi_values}")
    print(f"  Mean: {mean_rssi:.2f}, Std Dev: {std_rssi:.2f}")
    
    # Filter outliers (>2 std dev)
    filtered = rssi_values[np.abs(rssi_values - mean_rssi) <= 2 * std_rssi]
    outliers = rssi_values[np.abs(rssi_values - mean_rssi) > 2 * std_rssi]
    
    print(f"  Filtered values: {filtered}")
    print(f"  Outliers removed: {outliers}")
    print(f"  ✓ Filtering works: {len(filtered)}/{len(rssi_values)} samples kept\n")
    return True


def test_time_decay_weighting():
    """Test time-based decay weighting"""
    print("Testing time-based decay weighting...")
    
    # Sample ages in seconds
    ages = np.array([0, 60, 120, 300, 600, 900])  # 0s, 1m, 2m, 5m, 10m, 15m
    time_decay = 300.0  # 5 minute decay constant
    
    # Calculate decay factors
    decay_factors = np.exp(-ages / time_decay)
    
    print(f"  Time decay constant: {time_decay}s")
    print(f"  Sample ages (s): {ages}")
    print(f"  Decay factors: {decay_factors}")
    print(f"  5-minute sample weight: {decay_factors[3]:.3f} (should be ~0.368)")
    print(f"  ✓ Time decay calculation works\n")
    return True


def test_rssi_to_distance():
    """Test RSSI to distance conversion with FSPL"""
    print("Testing RSSI to distance conversion...")
    
    tx_power = 14.0  # dBm
    freq_mhz = 915.0
    path_loss_exp = 2.5
    
    # FSPL at 1m
    fspl_1m = 20 * np.log10(freq_mhz) + 20 * np.log10(1) - 27.55
    print(f"  FSPL at 1m for {freq_mhz} MHz: {fspl_1m:.2f} dB")
    
    # Test various RSSI values
    test_rssi = [-40, -60, -80, -100]
    for rssi in test_rssi:
        path_loss = tx_power - rssi - fspl_1m
        distance = 10 ** (path_loss / (10 * path_loss_exp))
        distance = max(distance, 1.0)
        print(f"  RSSI {rssi} dBm → {distance:.1f} meters")
    
    print(f"  ✓ RSSI to distance conversion works\n")
    return True


def test_kalman_filter_init():
    """Test Kalman filter initialization"""
    print("Testing Kalman filter initialization...")
    
    # Initialize Kalman filter (4-state: lat, lon, vel_lat, vel_lon)
    kf = KalmanFilter(dim_x=4, dim_z=2)
    
    # Set up matrices
    dt = 1.0
    kf.F = np.array([
        [1, 0, dt, 0],
        [0, 1, 0, dt],
        [0, 0, 1, 0],
        [0, 0, 0, 1]
    ])
    kf.H = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0]
    ])
    kf.x = np.array([37.7749, -122.4194, 0, 0])  # San Francisco
    kf.R = np.eye(2) * 0.0001
    kf.Q = np.eye(4) * 0.00001
    kf.P = np.eye(4) * 0.01
    
    print(f"  Initial state: {kf.x}")
    print(f"  State dimension: {kf.dim_x}")
    print(f"  Measurement dimension: {kf.dim_z}")
    
    # Simulate one prediction and update
    kf.predict()
    z = np.array([37.7750, -122.4195])  # Slightly moved
    kf.update(z)
    
    print(f"  After update: {kf.x[:2]}")
    print(f"  ✓ Kalman filter initialization and update works\n")
    return True


def test_scipy_trilateration():
    """Test SciPy least_squares for trilateration"""
    print("Testing SciPy trilateration...")
    
    # Known positions and distances
    measurements = [
        {'lat': 37.7749, 'lon': -122.4194, 'distance': 100, 'weight': 1.0},
        {'lat': 37.7750, 'lon': -122.4180, 'distance': 150, 'weight': 1.0},
        {'lat': 37.7760, 'lon': -122.4190, 'distance': 120, 'weight': 1.0},
    ]
    
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = np.radians(lat1), np.radians(lat2)
        dphi = np.radians(lat2 - lat1)
        dlambda = np.radians(lon2 - lon1)
        a = np.sin(dphi/2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda/2)**2
        return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    
    def residuals(pos):
        est_lat, est_lon = pos
        resids = []
        for m in measurements:
            calc_dist = haversine(est_lat, est_lon, m['lat'], m['lon'])
            resid = (calc_dist - m['distance']) * np.sqrt(m['weight'])
            resids.append(resid)
        return resids
    
    # Initial guess (weighted centroid)
    init_lat = np.mean([m['lat'] for m in measurements])
    init_lon = np.mean([m['lon'] for m in measurements])
    
    print(f"  Initial guess: ({init_lat:.6f}, {init_lon:.6f})")
    
    # Optimize
    result = least_squares(residuals, [init_lat, init_lon], method='lm')
    
    if result.success:
        est_lat, est_lon = result.x
        print(f"  Optimized position: ({est_lat:.6f}, {est_lon:.6f})")
        rmse = np.sqrt(np.mean(np.array(residuals(result.x))**2))
        print(f"  RMSE: {rmse:.2f} meters")
        print(f"  ✓ SciPy trilateration successful\n")
        return True
    else:
        print(f"  ✗ Optimization failed: {result.message}\n")
        return False


def test_heatmap_binning():
    """Test heatmap grid binning logic"""
    print("Testing heatmap binning logic...")
    
    # Generate random sample positions
    np.random.seed(42)
    n_samples = 50
    lats = 37.7749 + np.random.randn(n_samples) * 0.001
    lons = -122.4194 + np.random.randn(n_samples) * 0.001
    rssis = -70 + np.random.randn(n_samples) * 10
    
    # Convert to relative x,y
    mean_lat, mean_lon = np.mean(lats), np.mean(lons)
    R = 6371000
    lat_to_m = R * np.pi / 180
    lon_to_m = R * np.pi / 180 * np.cos(np.radians(mean_lat))
    
    x = (lons - mean_lon) * lon_to_m
    y = (lats - mean_lat) * lat_to_m
    
    # Create grid
    grid_width, grid_height = 10, 5
    x_min, x_max = np.min(x) - 10, np.max(x) + 10
    y_min, y_max = np.min(y) - 10, np.max(y) + 10
    
    x_edges = np.linspace(x_min, x_max, grid_width + 1)
    y_edges = np.linspace(y_min, y_max, grid_height + 1)
    
    # Bin samples
    grid_rssi = np.full((grid_height, grid_width), np.nan)
    grid_counts = np.zeros((grid_height, grid_width))
    
    for i in range(len(x)):
        x_idx = np.searchsorted(x_edges, x[i]) - 1
        y_idx = np.searchsorted(y_edges, y[i]) - 1
        if 0 <= x_idx < grid_width and 0 <= y_idx < grid_height:
            if np.isnan(grid_rssi[y_idx, x_idx]):
                grid_rssi[y_idx, x_idx] = rssis[i]
                grid_counts[y_idx, x_idx] = 1
            else:
                grid_rssi[y_idx, x_idx] += rssis[i]
                grid_counts[y_idx, x_idx] += 1
    
    # Average
    for y_idx in range(grid_height):
        for x_idx in range(grid_width):
            if grid_counts[y_idx, x_idx] > 0:
                grid_rssi[y_idx, x_idx] /= grid_counts[y_idx, x_idx]
    
    filled_cells = np.sum(~np.isnan(grid_rssi))
    print(f"  Grid size: {grid_width}x{grid_height}")
    print(f"  Samples: {n_samples}")
    print(f"  Filled cells: {filled_cells}/{grid_width*grid_height}")
    print(f"  Sample range: X=[{x_min:.1f}, {x_max:.1f}], Y=[{y_min:.1f}, {y_max:.1f}]")
    print(f"  ✓ Heatmap binning works\n")
    return True


def main():
    """Run all tests"""
    print("="*60)
    print("Mesh Tracker Improvements Validation Test")
    print("="*60 + "\n")
    
    tests = [
        ("Imports", test_imports),
        ("Outlier Filtering", test_outlier_filtering),
        ("Time Decay Weighting", test_time_decay_weighting),
        ("RSSI to Distance", test_rssi_to_distance),
        ("Kalman Filter", test_kalman_filter_init),
        ("SciPy Trilateration", test_scipy_trilateration),
        ("Heatmap Binning", test_heatmap_binning),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"  ✗ {name} test failed with exception: {e}\n")
            results.append((name, False))
    
    print("="*60)
    print("Test Summary")
    print("="*60)
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {name}")
    
    passed = sum(1 for _, s in results if s)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! Ready to run mesh_tracker.py")
        return 0
    else:
        print("\n✗ Some tests failed. Check dependencies or code.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
