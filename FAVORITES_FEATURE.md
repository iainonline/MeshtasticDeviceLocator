# Favorites Feature - Implementation Summary

## Overview
Added the ability to favorite mesh nodes and save those favorites for future sessions. Also improved the mesh node list display sizing and formatting.

## Changes Made

### 1. Data Structures
- Added `is_favorite` boolean attribute to `MeshNode` class
- Added `favorite_nodes` set to track favorited node IDs
- Created `favorites_file` (favorite_nodes.pkl) for persistence

### 2. Persistence
- Favorites are saved to `favorite_nodes.pkl` using pickle
- Favorites are loaded on startup and restored after app restart
- Favorites are automatically saved when:
  - Toggling favorite status
  - Application cleanup/exit

### 3. User Interface Improvements

#### Node List Display
- **Fixed width**: Set listbox to 30 characters for consistent sizing
- **Favorite indicator**: ⭐ star emoji shows next to favorited nodes
- **Improved sorting**: Favorites appear first, then sorted by last seen time
- **Better formatting**: Display format is now `⭐ Name       RSSIdB Age [samples]`

#### Controls
- **New Button**: "⭐ Toggle Favorite" button in left panel
- **Keyboard Shortcut**: Ctrl+F to toggle favorite on selected node
- **Auto-marking**: New nodes are automatically marked as favorites if they were previously favorited

### 4. Functions Added

#### `load_favorites()`
- Loads favorite nodes from disk on startup
- Marks existing nodes as favorites if they're in the favorites set

#### `save_favorites()`
- Saves current favorite nodes to disk
- Called on toggle and on app cleanup

#### `toggle_favorite()`
- Toggles favorite status of the currently selected node
- Updates the favorites set and saves to disk
- Shows a message box if no node is selected
- Triggers display refresh to show the star

### 5. Auto-marking Logic
Nodes are marked as favorites when created in three locations:
1. When loading signal history (restoring from previous session)
2. When loading from Meshtastic nodeDB
3. When receiving new packets from mesh

## Usage

### Favoriting a Node
1. Select a node from the mesh nodes list
2. Click "⭐ Toggle Favorite" button OR press Ctrl+F
3. A star (⭐) will appear next to the node name
4. The node will move to the top of the list

### Unfavoriting a Node
1. Select a favorited node (one with ⭐)
2. Click "⭐ Toggle Favorite" button OR press Ctrl+F
3. The star will be removed and the node will return to normal sorting

### Persistence
- Favorites are automatically saved and will persist across application restarts
- The favorites are stored in `favorite_nodes.pkl` in the application directory

## Display Format
```
⭐ NodeName   -45 =dB  15s [5]
   OtherNode  -60 ↓dB  2m  
   FarNode    N/A     10m
```

- First column: ⭐ for favorites, empty for regular nodes
- Second column: Node name (max 10 chars)
- Third column: RSSI with trend indicator (↑ improving, ↓ degrading, = stable)
- Fourth column: Time since last seen (s=seconds, m=minutes, h=hours)
- Fifth column: [N] number of estimation samples collected (if any)

## Technical Details

### Files Modified
- `mesh_tracker_gui.py`: Main GUI implementation

### Files Created
- `favorite_nodes.pkl`: Persistent storage for favorites (created automatically)

### Node List Width
Changed from dynamic width (300px) to fixed character width (30 chars) which:
- Prevents horizontal resizing issues
- Ensures consistent display across all nodes
- Makes the list more predictable and easier to read
