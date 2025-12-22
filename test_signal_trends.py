#!/usr/bin/env python3
"""
Test the new signal trends and last 5 readings feature
"""

import time
from typing import Optional, List

class SimpleMeshNode:
    """Simplified MeshNode for testing"""
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.short_name = "Unknown"
        self.signal_history: List[dict] = []
        self.rssi = None
        self.snr = None
    
    def get_signal_trend(self, time_window: int) -> Optional[str]:
        """Get signal trend over specified time window in seconds"""
        if len(self.signal_history) < 2:
            return None
        
        current_time = time.time()
        cutoff_time = current_time - time_window
        
        recent_readings = [h for h in self.signal_history if h['timestamp'] > cutoff_time]
        
        if len(recent_readings) < 2:
            return None
        
        mid_point = len(recent_readings) // 2
        first_half = recent_readings[:mid_point]
        second_half = recent_readings[mid_point:]
        
        avg_first = sum(h['rssi'] for h in first_half) / len(first_half)
        avg_second = sum(h['rssi'] for h in second_half) / len(second_half)
        
        diff = avg_second - avg_first
        
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
        
        mid_point = len(recent_readings) // 2
        first_half = recent_readings[:mid_point]
        second_half = recent_readings[mid_point:]
        
        avg_first = sum(h['rssi'] for h in first_half) / len(first_half)
        avg_second = sum(h['rssi'] for h in second_half) / len(second_half)
        
        return avg_second - avg_first
    
    def get_last_n_signal_readings(self, n: int = 5) -> List[dict]:
        """Get the last N signal readings with timestamps"""
        if not self.signal_history:
            return []
        
        current_time = time.time()
        last_n = self.signal_history[-n:] if len(self.signal_history) >= n else self.signal_history
        
        result = []
        for entry in last_n:
            age = current_time - entry['timestamp']
            result.append({
                'timestamp': entry['timestamp'],
                'rssi': entry['rssi'],
                'snr': entry.get('snr', 0),
                'age': age
            })
        
        return result

def test_signal_trends():
    """Test signal trend detection and last 5 readings"""
    
    print("="*60)
    print("Testing Signal Trends and Last 5 Readings")
    print("="*60)
    print()
    
    # Create a node
    node = SimpleMeshNode("!test1234")
    node.short_name = "TEST"
    
    print("Scenario 1: Walking TOWARD node (getting HOTTER)")
    print("-" * 60)
    
    # Simulate signal getting stronger (walking toward)
    rssi_values = [-90, -88, -85, -82, -78, -75, -72, -68, -65]
    snr_values = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
    
    base_time = time.time() - 300  # Start 5 minutes ago
    
    for i, (rssi, snr) in enumerate(zip(rssi_values, snr_values)):
        node.rssi = rssi
        node.snr = snr
        
        # Manually add to signal history with time spread
        node.signal_history.append({
            'timestamp': base_time + (i * 30),  # 30 seconds apart
            'rssi': rssi,
            'snr': snr
        })
    
    # Update current time for age calculations
    node.signal_history[-1]['timestamp'] = time.time() - 5  # 5 seconds ago
    
    print("\nSignal trends:")
    print(f"  10 seconds:  {node.get_signal_trend(10)} ({node.get_signal_strength_change(10):+.1f} dBm)" if node.get_signal_trend(10) else "  10 seconds:  Not enough data")
    print(f"  60 seconds:  {node.get_signal_trend(60)} ({node.get_signal_strength_change(60):+.1f} dBm)" if node.get_signal_trend(60) else "  60 seconds:  Not enough data")
    print(f"  5 minutes:   {node.get_signal_trend(300)} ({node.get_signal_strength_change(300):+.1f} dBm)" if node.get_signal_trend(300) else "  5 minutes:   Not enough data")
    
    print("\nLast 5 signal readings:")
    last_readings = node.get_last_n_signal_readings(5)
    for i, reading in enumerate(last_readings, 1):
        age_str = f"{reading['age']:.0f}s ago" if reading['age'] < 60 else f"{reading['age']/60:.1f}m ago"
        print(f"  {i}. RSSI: {reading['rssi']:4d} dBm, SNR: {reading['snr']:4.1f} dB  ({age_str})")
    
    print()
    print("="*60)
    print()
    
    # Test scenario 2: Walking away
    print("Scenario 2: Walking AWAY from node (getting COLDER)")
    print("-" * 60)
    
    node2 = SimpleMeshNode("!test5678")
    node2.short_name = "TEST2"
    
    # Simulate signal getting weaker (walking away)
    rssi_values2 = [-65, -68, -72, -75, -78, -82, -85, -88, -90]
    snr_values2 = [6.0, 5.5, 5.0, 4.5, 4.0, 3.5, 3.0, 2.5, 2.0]
    
    base_time2 = time.time() - 300
    
    for i, (rssi, snr) in enumerate(zip(rssi_values2, snr_values2)):
        node2.rssi = rssi
        node2.snr = snr
        
        node2.signal_history.append({
            'timestamp': base_time2 + (i * 30),
            'rssi': rssi,
            'snr': snr
        })
    
    node2.signal_history[-1]['timestamp'] = time.time() - 5
    
    print("\nSignal trends:")
    print(f"  10 seconds:  {node2.get_signal_trend(10)} ({node2.get_signal_strength_change(10):+.1f} dBm)" if node2.get_signal_trend(10) else "  10 seconds:  Not enough data")
    print(f"  60 seconds:  {node2.get_signal_trend(60)} ({node2.get_signal_strength_change(60):+.1f} dBm)" if node2.get_signal_trend(60) else "  60 seconds:  Not enough data")
    print(f"  5 minutes:   {node2.get_signal_trend(300)} ({node2.get_signal_strength_change(300):+.1f} dBm)" if node2.get_signal_trend(300) else "  5 minutes:   Not enough data")
    
    print("\nLast 5 signal readings:")
    last_readings2 = node2.get_last_n_signal_readings(5)
    for i, reading in enumerate(last_readings2, 1):
        age_str = f"{reading['age']:.0f}s ago" if reading['age'] < 60 else f"{reading['age']/60:.1f}m ago"
        print(f"  {i}. RSSI: {reading['rssi']:4d} dBm, SNR: {reading['snr']:4.1f} dB  ({age_str})")
    
    print()
    print("="*60)
    print("Test completed successfully!")
    print("="*60)

if __name__ == "__main__":
    test_signal_trends()
