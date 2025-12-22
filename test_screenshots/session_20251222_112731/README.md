# Mesh Tracker GUI Test Session

**Date**: Mon 22 Dec 11:29:23 PST 2025
**Session ID**: 20251222_112731

## Test Environment
- OS: Linux 6.12.47+rpt-rpi-2712
- Screenshot Tool: scrot
- GUI Process: 14336

## Functional Test Results

### Error Detection
- Errors: 5
- Tracebacks: 9

### Node Discovery
- Nodes discovered: 95

### GPS Functionality
- GPS readings: 110

### Signal Data
- RSSI readings: 9
- SNR readings: 9

### Hop Count
- Hop count readings: 5
- Direct connections: 2

### Logging
- JSON log entries: 0

### Resource Usage
- Memory usage: 3.125 MB

## Screenshots

### 01_initial_state
**Description**: GUI initial state after startup

![01_initial_state](01_initial_state.png)

### 02_gps_lock
**Description**: GUI after waiting for GPS lock

![02_gps_lock](02_gps_lock.png)

### 03_nodes_discovered
**Description**: GUI after node discovery period

![03_nodes_discovered](03_nodes_discovered.png)

### 05_data_collection
**Description**: GUI after 30 seconds of data collection

![05_data_collection](05_data_collection.png)

### 06_signal_plot
**Description**: GUI showing signal history plot

![06_signal_plot](06_signal_plot.png)


## GUI Output Log (last 50 lines)

```
Traceback (most recent call last):
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 1820, in handle_mesh_packet
    'decoded': make_json_serializable(decoded),
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 57, in make_json_serializable
    return make_json_serializable(dict(obj)) if hasattr(obj, 'items') else list(obj)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 57, in make_json_serializable
    return make_json_serializable(dict(obj)) if hasattr(obj, 'items') else list(obj)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 57, in make_json_serializable
    return make_json_serializable(dict(obj)) if hasattr(obj, 'items') else list(obj)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  [Previous line repeated 984 more times]
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 56, in make_json_serializable
    elif isinstance(obj, type({}.keys()).__base__):  # mappingproxy, dict_keys, dict_values
                              ^^^^^^^^^
RecursionError: maximum recursion depth exceeded while calling a Python object
2025-12-22 11:29:10,122 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081392, Sats: 12
2025-12-22 11:29:11,066 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081392, Sats: 12
2025-12-22 11:29:12,043 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081392, Sats: 12
2025-12-22 11:29:13,062 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081392, Sats: 12
Traceback (most recent call last):
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 1820, in handle_mesh_packet
    'decoded': make_json_serializable(decoded),
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 57, in make_json_serializable
    return make_json_serializable(dict(obj)) if hasattr(obj, 'items') else list(obj)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 57, in make_json_serializable
    return make_json_serializable(dict(obj)) if hasattr(obj, 'items') else list(obj)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 57, in make_json_serializable
    return make_json_serializable(dict(obj)) if hasattr(obj, 'items') else list(obj)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  [Previous line repeated 984 more times]
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 56, in make_json_serializable
    elif isinstance(obj, type({}.keys()).__base__):  # mappingproxy, dict_keys, dict_values
                              ^^^^^^^^^
RecursionError: maximum recursion depth exceeded while calling a Python object
2025-12-22 11:29:14,057 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081392, Sats: 12
2025-12-22 11:29:15,062 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081392, Sats: 12
2025-12-22 11:29:16,069 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081392, Sats: 12
2025-12-22 11:29:17,037 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081392, Sats: 12
2025-12-22 11:29:18,055 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081392, Sats: 12
2025-12-22 11:29:19,054 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081391, Sats: 12
2025-12-22 11:29:20,067 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081391, Sats: 12
2025-12-22 11:29:21,059 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081391, Sats: 12
2025-12-22 11:29:22,051 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081391, Sats: 12
2025-12-22 11:29:23,047 - __main__ - DEBUG - GPS Fix: 35.968383, -115.081391, Sats: 12
```

## Test Completion

Test session completed at: Mon 22 Dec 11:29:23 PST 2025

