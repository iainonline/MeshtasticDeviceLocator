# Mesh Tracker GUI Test Session

**Date**: Mon 22 Dec 11:25:24 PST 2025
**Session ID**: 20251222_112333

## Test Environment
- OS: Linux 6.12.47+rpt-rpi-2712
- Screenshot Tool: scrot
- GUI Process: 13752

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
[DEBUG] Updating display, 94 nodes
[DEBUG] Displaying 94 nodes in list
[DEBUG] Actually displayed 94 nodes in listbox
[DEBUG] Restored selection to line 10 for node !9e7656a8
[DEBUG] Packet received: !f7d5753d
[DEBUG] Processing packet from !f7d5753d
[DEBUG] Node !f7d5753d RSSI: -63 (min:-63, max:-63) Est.dist: 2.1km
[DEBUG] Node !f7d5753d SNR: 5.5
[DEBUG] Node !f7d5753d hops: 2
[ERROR] Logging failed: Object of type mappingproxy is not JSON serializable
[DEBUG] Node !f7d5753d position from packet: 36.254515, -115.264717
[POSITION] Node !f7d5753d has GPS: lat=36.254515, lon=-115.264717
[POSITION] Source: Node's own GPS (not estimated)
[POSITION] Current estimation_samples count: 0
[POSITION] Distance from tracker: 35.82km
[DEBUG] Updating display, 94 nodes
[DEBUG] Displaying 94 nodes in list
[DEBUG] Actually displayed 94 nodes in listbox
[DEBUG] Restored selection to line 11 for node !9e7656a8
[DEBUG] Updating display, 94 nodes
[DEBUG] Displaying 94 nodes in list
[DEBUG] Actually displayed 94 nodes in listbox
[DEBUG] Restored selection to line 11 for node !9e7656a8
Traceback (most recent call last):
  File "/home/iain/MeshLocator/MeshtasticDeviceLocator/mesh_tracker_gui.py", line 1826, in handle_mesh_packet
    self.log_file.write(json.dumps(log_entry) + '\n')
                        ^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/__init__.py", line 231, in dumps
    return _default_encoder.encode(obj)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/encoder.py", line 200, in encode
    chunks = self.iterencode(o, _one_shot=True)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/encoder.py", line 258, in iterencode
    return _iterencode(o, 0)
           ^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/encoder.py", line 180, in default
    raise TypeError(f'Object of type {o.__class__.__name__} '
TypeError: Object of type mappingproxy is not JSON serializable
2025-12-22 11:25:14,044 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:15,062 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:16,063 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:17,066 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:18,071 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:19,046 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:20,051 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:21,061 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:22,061 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:23,065 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
2025-12-22 11:25:24,065 - __main__ - DEBUG - GPS Fix: 35.968404, -115.081402, Sats: 12
```

## Test Completion

Test session completed at: Mon 22 Dec 11:25:24 PST 2025

