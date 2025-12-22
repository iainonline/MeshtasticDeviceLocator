# Long Name Display and Crash Fix Summary

## Issues Fixed

### 1. Incorrect Long Names Display
**Problem**: Nodes were showing "Unknown" or incorrect long names initially, even though they had proper names configured in the Meshtastic network.

**Root Cause**: When packets arrive from nodes, many packet types don't include user information (short name, long name). Only NODEINFO packets contain this data. Since our tracker was only using packet data, nodes appeared as "Unknown" until a NODEINFO packet was received.

**Solution**: 
- Added lookup to the Meshtastic interface's `nodeDB` when handling packets
- If a node doesn't have user info in the packet, we now query the interface's cached node database
- Handles both `!node_id` and `node_id` format variations
- Updates occur automatically as the interface's nodeDB gets populated

### 2. Display Name Fallback Logic
**Problem**: Even with the nodeDB lookup, some nodes might not have long names set, or the long name might be the same as the short name.

**Solution**: Implemented a cascading fallback for display names:
1. Use long name if available and different from short name
2. Fall back to short name if long name is "Unknown" or same as short name
3. Fall back to formatted node ID (e.g., "Meshtastic 7a8c") if both are "Unknown"

This ensures every node always has a readable display name.

### 3. Program Crash on Non-TTY Terminals
**Problem**: When running via shell scripts or with output redirection (e.g., `./run.sh` or piping), the program crashed immediately with a termios error.

**Root Cause**: The code called `termios.tcgetattr(sys.stdin)` without checking if stdin was a proper terminal. This fails when stdin is redirected, piped, or not a TTY.

**Solution**:
- Added `sys.stdin.isatty()` check before attempting terminal control
- When running without a TTY:
  - Displays a warning message
  - Runs in non-interactive mode
  - Still collects data and logs properly
  - Can be stopped with Ctrl+C

## Code Changes

### File: `mesh_tracker.py`

#### Change 1: NodeDB Lookup in `handle_mesh_packet()`
Added code after extracting user info from packet to look up missing names from the mesh interface's nodeDB:

```python
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
                    # Update missing names from nodeDB
```

#### Change 2: Display Name Fallback in `generate_node_list_view()`
Improved the name display logic in the node list:

```python
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
```

#### Change 3: TTY Check in `run()`
Added terminal type checking before attempting terminal control:

```python
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
```

## Testing Results

### Before Fix:
- Nodes showed as "Unknown" initially
- Long names appeared incorrect or truncated oddly
- Program crashed immediately when run via `./run.sh` or with piped output
- Exit message: "Shutting down..." immediately after startup

### After Fix:
- Nodes display with proper names from nodeDB
- Fallback names are logical and readable
- Program runs successfully in all terminal contexts
- Interactive mode works in proper TTY
- Non-interactive mode works when stdin is not a TTY
- Data logging continues properly in both modes

## Benefits

1. **Better User Experience**: Node names now appear correctly from the start
2. **Robust Fallback**: Every node always has a readable name
3. **Flexibility**: Works in interactive terminals, scripts, pipes, and redirections
4. **Reliability**: No more crashes due to terminal type mismatches
5. **Data Collection**: Can now run as a background service or with output redirection for logging

## Git Branch
Changes committed to: `feature/fix-longname-and-crash`

Ready to merge to `main` branch.
