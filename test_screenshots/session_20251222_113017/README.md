# Mesh Tracker GUI Test Session

**Date**: Mon 22 Dec 11:32:09 PST 2025
**Session ID**: 20251222_113017

## Test Environment
- OS: Linux 6.12.47+rpt-rpi-2712
- Screenshot Tool: scrot
- GUI Process: 14829

## Functional Test Results

### Error Detection
- Errors: 4
- Tracebacks: 4

### Node Discovery
- Nodes discovered: 97

### GPS Functionality
- GPS readings: 91

### Signal Data
- RSSI readings: 4
- SNR readings: 4

### Hop Count
- Hop count readings: 3
- Direct connections: 0

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
[DEBUG] Updating display, 97 nodes
[DEBUG] Displaying 97 nodes in list
[DEBUG] Actually displayed 97 nodes in listbox
[DEBUG] Node selected: !9e761374, short_name=Unknown, long_name=Unknown
[DEBUG] Node !9e761374 has no estimated position
[DEBUG] Packet received: None
[DEBUG] Packet has no valid fromId: dict_keys(['from', 'to', 'channel', 'encrypted', 'id', 'rxTime', 'rxSnr', 'hopLimit', 'rxRssi', 'hopStart', 'relayNode', 'transportMechanism', 'raw', 'fromId', 'toId'])
[DEBUG] Updating display, 97 nodes
[DEBUG] Displaying 97 nodes in list
[DEBUG] Actually displayed 97 nodes in listbox
[DEBUG] Restored selection to line 5 for node !9e761374
[DEBUG] Updating display, 97 nodes
2025-12-22 11:31:32,035 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:33,047 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:34,034 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:35,043 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:36,039 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:37,046 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:38,037 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:39,046 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:40,037 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:41,047 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:42,034 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:43,039 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:44,040 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:45,051 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:46,037 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:47,038 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:48,039 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:49,049 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:50,070 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:51,065 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:52,039 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:53,064 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:54,064 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:55,049 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:56,058 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:57,068 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:58,065 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:31:59,044 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:00,061 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:01,061 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:02,060 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:03,041 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:04,033 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:05,045 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:06,069 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:07,063 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:08,067 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
2025-12-22 11:32:09,052 - __main__ - DEBUG - GPS Fix: 35.968392, -115.081393, Sats: 12
```

## Test Completion

Test session completed at: Mon 22 Dec 11:32:09 PST 2025

