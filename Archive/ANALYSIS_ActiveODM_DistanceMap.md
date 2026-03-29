# ActiveODM DistanceMap Dialog - Comprehensive Analysis

## Document Purpose
This analysis covers the existing `activeodm_distancemap_dialog.py` (1011 lines) and `.ui` file to guide the creation of a **multimodal CombinedODM_DistanceMap** dialog that incorporates transit routing.

---

## Part 1: Python File Structure & Key Methods

### 1.1 Class Definition & Initialization
**File**: `activeodm_distancemap_dialog.py`
**Lines**: 42-100

```python
class ActiveODMDistanceMapDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None, iface=None):
        # Inherits: QDialog (PyQt5) + FORM_CLASS (generated from .ui)
        # Key attributes initialized:
        # - self.iface: QGIS interface for messaging/logging
        # - self.layer_field_map: dict storing per-layer field selections
        # - self.current_layer_id: tracks active layer
        # - self._id_selector_conn, self._name_selector_conn: signal handlers
```

**Memory Storage**:
- Layer field selections stored in-memory during plugin runtime (not persisted to disk)
- QSettings used for persistent storage across QGIS sessions (Speed, MaxDuration, MaxDistance, checkbox states)

---

### 1.2 Main Workflow: The Build() Method
**Location**: Lines 760-805

```
Build() → Orchestrates entire distance map computation
├─ sub_collectPairs() → Extract origins from input layer
├─ read_ODM() → Load SQLite ODM file (filtered by selection & distance limit)
├─ sub_BuildDistanceMap() → Calculate walk times and distance map
└─ sub_Export_GeoJSON() → Create result layer with distance/duration fields
```

#### Flow Diagram:
```
User clicks OK → Evaluate() → Build() → Export → Dialog closes
                   ↓
            - Validates layer
            - Validates features (>100?)
            - Validates output options
            - Validates ODM file exists
                   ↓
            If valid → labelCurrentStatus updates
                     progressBar updated
                     QCoreApplication.processEvents()
```

---

### 1.3 Sub-Function Details

#### A. `sub_collectPairs()` (Lines 835-874)
**Purpose**: Extract origin features from the input layer

```python
def sub_collectPairs(self, name_field, id_field, use_name=True):
    # Inputs:
    #   name_field: field name for display names
    #   id_field: field name matching ODM origin IDs
    #   use_name: if True, display as "Name (ID)", else just "ID"
    
    # Returns:
    origins = [(id, display_name), (id, display_name), ...]
    selection = [id, id, id, ...]  # Just the IDs for filtering ODM
    
    # Process:
    # 1. Get all features from layer
    # 2. If onlySelectedFeatures checked: use selectedFeatures()
    #    Else: use all features
    # 3. Extract id_field and name_field values
    # 4. Update progress bar
```

**Key Decision Point**: `onlySelectedFeatures` checkbox
- Line 699-705 in Evaluate(): Checks if user selected this option
- Affects both validation logic and data collection

---

#### B. `read_ODM()` (Analytics/IO.py, Lines 196-300+)
**Purpose**: Load SQLite file into nested dict structure

```python
def read_ODM(filepath, remove_prefix=True, origin_prefix_whitelist=[],
             destination_prefix_whitelist=[], max_duration=0,
             bar=None, selection=None, limit=0):
    
    # Returns:
    # D[origin][destination] = (distance_meters, duration_seconds)
    
    # SQL Query Built Dynamically:
    # SELECT * FROM OD
    # WHERE origin IN (?, ?, ...) [if selection provided]
    # AND distance < ? [if limit > 0]
    
    # Returned ODM Structure:
    # {
    #   "origin_id_1": {
    #     "dest_1": (1500.0, 60.0),  # 1.5km, 60 seconds
    #     "dest_2": (2000.0, 80.0),
    #   },
    #   ...
    # }
```

**Filtering Logic** (Line 809):
```python
min_limit = min(
    speed_kmh * (max_duration_minutes / 60) * 1000,  # Time-based distance
    max_distance_km * 1000                            # Direct distance
)
# Both filters are applied via the 'limit' parameter
```

**SQLite Table Schema** (Expected):
```
OD Table columns:
- origin (TEXT): ID matching grid layer's id_field
- destination (TEXT): ID of destination
- distance (REAL): Distance in meters
- duration (REAL): Duration in seconds
```

---

#### C. `sub_BuildDistanceMap()` (Lines 876-908)
**Purpose**: Create working distance map with walk times

```python
def sub_BuildDistanceMap(self, ODM, origins, src_layer, speed=4.5, bar=None):
    # Inputs:
    #   ODM: nested dict from read_ODM()
    #   origins: list of (id, name) tuples from sub_collectPairs()
    #   src_layer: input vector layer
    #   speed: walking speed in km/h (from speedDial)
    
    # Process:
    DistanceMap = {}
    for (id_, name) in origins:
        if id_ in ODM:
            DistanceMap[id_] = {}
            for dest_id, (distance, duration) in ODM[id_].items():
                walk_time = distance / (speed * 1000 / 60)
                # where: speed in km/h → m/min
                DistanceMap[id_][dest_id] = (distance, duration, walk_time)
    
    # Returns:
    # DistanceMap[origin][destination] = (distance_m, duration_s, walk_time_min)
```

**Critical Calculation**:
- `walk_time_min = distance_m / (speed_kmh * 1000 / 60)`
- Converts: distance (meters), speed (km/h) → walk_time (minutes)
- Speed from `self.speedDial.value()` (QgsDoubleSpinBox, 0-100 km/h range)

---

#### D. `sub_Export_GeoJSON()` (Lines 912+)
**Purpose**: Create result layer with distance/duration attributes

**High-level Process**:
1. Create memory layer based on input layer geometry
2. Add fields: `from_{origin_name}_Distance` and `from_{origin_name}_Duration` for each origin
3. For each destination feature in input layer:
   - Look up distances from all origins in DistanceMap
   - Populate corresponding fields
4. Export to GeoJSON file

**Field Naming**: 
- Origin name comes from `sub_collectPairs()` output (includes ID if use_name=True)
- Results: one pair of fields per origin
- Special case: if destination ID = origin ID → set distance=0, duration=0

---

### 1.4 Supporting Methods

#### Settings Persistence
- **`save_settings()`** (Lines 185-203): Save to QSettings
  - Checkboxes: ResultDistance, ResultDuration, IncludeName, OnlySelectedFeatures
  - Field selections: IdField, NameField
  
- **`load_settings()`** (Lines 205-232): Restore from QSettings with defaults
  - Defaults: ResultDistance=True, ResultDuration=True, IncludeName=True, OnlySelectedFeatures=False

#### Layer Field Management
- **`_save_current_selection(layer_id)`** (Line 234): Store field selections per layer
- **`_restore_selection_for_layer(layer_id)`** (Line 247): Restore field selections when switching layers
- **`updateLayer(layer)`** (Line 425): Triggered when input layer changes
  - Disconnects old signal handlers
  - Sets layer for field selectors
  - Restores previous field selections for this layer

#### Validation & Logging
- **`Evaluate(max_features=100)`** (Lines 640-760): Pre-Build validation
  - Checks: layer exists, features exist, at least one output option
  - Prompts user if >100 features
- **`_log(message, level='info')`** (Line 419): QGIS log output via QgsMessageLog

---

## Part 2: UI File Structure & Widgets

### 2.1 UI File Overview
**File**: `activeodm_distancemap_dialog_base.ui`
**Type**: Qt Designer XML format
**Window Size**: 713x580 pixels
**Layout**: QVBoxLayout (vertical stacking)

### 2.2 Widget Hierarchy

```
ActiveODMDistanceMapDialog (QDialog, 713x580)
└─ verticalLayout
   ├─ label: "Input Grid Layer"
   ├─ inputLayer: QgsMapLayerComboBox [name="inputLayer"]
   ├─ onlySelectedFeatures: QCheckBox [checked=true]
   ├─ label_3: "ID (same as ODM ID)"
   ├─ idSelector: QgsFieldComboBox [name="idSelector"]
   ├─ line_2: QLine (divider)
   ├─ label_2: "Origin Destination Matrix (ODM) in SQLite format"
   ├─ fileSelector: QgsFileWidget [name="fileSelector"]
   ├─ line: QLine (divider)
   ├─ mGroupBox_2: QgsCollapsibleGroupBox [title="Options"] (110px min height)
   │  ├─ label_5: "Max time (minutes)"
   │  ├─ MaxDurationDial: QgsDoubleSpinBox [0-1440, decimals=1]
   │  ├─ label_7: "Max distance (km)"
   │  ├─ MaxDistanceDial: QgsDoubleSpinBox [0-1000, decimals=1]
   │  ├─ label_6: "Speed (km/h)"
   │  └─ speedDial: QgsDoubleSpinBox [0-100, step=0.1]
   ├─ mGroupBox: QgsCollapsibleGroupBox [title="Results"] (130px min height)
   │  ├─ checkBox_ResultDistance: QCheckBox [checked=true]
   │  ├─ checkBox_ResultDuration: QCheckBox [checked=false]
   │  ├─ checkBox_IncludeName: QCheckBox [checked=false]
   │  ├─ label_4: "Name attribute"
   │  └─ nameSelector: QgsFieldComboBox [name="nameSelector"]
   ├─ buttonBox: QDialogButtonBox [OK, Cancel]
   ├─ line_4: QLine (divider)
   ├─ labelCurrentStatus: QLabel [text="-"]
   └─ progressBar: QProgressBar [value=0]
```

### 2.3 Custom QGIS Widgets
All widgets maintain references to QGIS objects:

| Widget | Base Class | Purpose | Key Method |
|--------|-----------|---------|-----------|
| inputLayer | QComboBox | Select vector layer | currentLayer() |
| idSelector | QComboBox | Select ID field from layer | currentField() |
| nameSelector | QComboBox | Select name field from layer | currentField() |
| fileSelector | QWidget | Browse and select file | filePath() |
| MaxDurationDial | QDoubleSpinBox | Set max travel time |value() |
| MaxDistanceDial | QDoubleSpinBox | Set max walking distance | value() |
| speedDial | QDoubleSpinBox | Set walking speed | value() |

---

## Part 3: Imports & Dependencies

### 3.1 Core Imports
```python
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QPushButton, QLineEdit, QFileDialog, 
                                 QMessageBox, QProgressBar
from qgis.PyQt.QtCore import QTimer, QSettings, QCoreApplication, QVariant
from qgis.core import (QgsVectorLayerExporter, QgsVectorFileWriter, 
                       QgsCoordinateTransformContext, QgsWkbTypes, 
                       QgsVectorLayer, QgsField, QgsMessageLog, Qgis, QgsProject)

import os, time, json
from datetime import datetime
```

### 3.2 Local Module Imports
```python
from .Analytics.IO import (
    read_ODM,
    estimate_sqlite_load_time,
    get_sqlite_info,
    quick_estimate_from_filesize
)
```

---

## Part 4: Evaluation & Error Handling

### 4.1 Pre-Build Checks in `Evaluate()`
**Location**: Lines 640-760

```python
def Evaluate(self, max_features=100) -> bool:
    """
    Validates user input before Build() execution
    Returns: True if OK to proceed, False to cancel
    """
    
    Checks performed:
    1. ✓ At least ONE output option selected (distance OR duration)
    2. ✓ Layer exists and has features
    3. ✓ If onlySelectedFeatures: at least one feature must be selected
    4. ⚠ Warn if >100 features (asks user to confirm)
    5. ✓ ODM file exists and is readable (via read_ODM() return check)
```

### 4.2 Error Handling in Build()
**Failure Points**:

1. **ODM file not found** (Line 803):
   - `read_ODM()` returns None if file can't be opened or has 0 rows
   - Shows dialog: "Error matching origins" → Check ID field and ODM file
   
2. **No matching origins** (Line 803):
   - If `ODM is None` → id_field values don't match ODM origin IDs
   
3. **Bad layer reference** (various):
   - `QgsProject.instance().mapLayer()` can return None if layer deleted

### 4.3 Progress Feedback
Three feedback mechanisms:
1. `self.labelCurrentStatus.setText(msg)` - Status text
2. `self.progressBar.setValue(0-100)` - Progress percentage
3. `QCoreApplication.processEvents()` - Allows UI refresh during long operations

---

## Part 5: Settings & Persistence

### 5.1 QSettings Keys (DiscreteProximityFramework/ prefix)
```
├─ last_odm_path (str)                        [Last selected file path]
├─ Speed (float)                              [Default: 4.5 km/h]
├─ MaxDuration (float)                        [Default: 20 minutes]
├─ MaxDistance (float)                        [Default: 1.5 km]
├─ CheckBox_ResultDistance (bool)             [Default: true]
├─ CheckBox_ResultDuration (bool)             [Default: false]
├─ CheckBox_IncludeName (bool)                [Default: false]
├─ CheckBox_OnlySelectedFeatures (bool)       [Default: false]
├─ IdField (str)                              [Last selected ID field]
└─ NameField (str)                            [Last selected Name field]
```

### 5.2 In-Memory Storage
- **`self.layer_field_map`** dict:
  ```python
  {
    layer_id_string: {'id_field': 'PosID', 'name_field': 'PosName'},
    layer_id_string: {'id_field': 'GridID', 'name_field': None},
  }
  ```
  - Restored when layer changes → user sees their last field selection for that layer
  - Lost when plugin reloads

---

## Part 6: Key Sections for Multimodal Adaptation

### 6.1 Critical Adaptations for CombinedODM_DistanceMap

#### A. FILE SELECTOR CHANGES
**Current**: Single SQLite file selector
```xml
<fileSelector>: QgsFileWidget [single file]
```

**New (CombinedODM)**: Three file selectors needed
```xml
activeODM_fileSelector:           QgsFileWidget  [Last-mile walking]
station2stationGTFS_fileSelector: QgsFileWidget  [Transit routing]
walkingToStation_fileSelector:    QgsFileWidget  [Access/egress]
```

#### B. NUMERIC INPUT CHANGES
**Current (3 inputs)**:
- MaxDurationDial (0-1440 min): *Total max travel time*
- MaxDistanceDial (0-1000 km): *Max walking distance*
- speedDial (0-100 km/h): *Walking speed*

**New (CombinedODM - 3 inputs, different meanings)**:
- maxWalkingToDestination (0-5 km): *Last-mile walking after transit*
- maxWalkingToStation (0-3 km): *Access walking to first station*
- maxTotalTravelTime (0-180 min): *Total multimodal journey time*

#### C. BUILD() WORKFLOW CHANGES

**Current Flow**:
```
collectPairs() 
  → read_ODM(single_file)
  → BuildDistanceMap()
  → Export_GeoJSON()
```

**New Flow (CombinedODM)**:
```
collectPairs() 
  → read_ODM(activeODM_file)           [Destination → nearest/multiple access points]
  → read_GTFS_Matrix(gtfs_file)        [Station A → Station B transit times]
  → read_ODM(walk2station_file)        [Origin → nearby stations]
  → sub_BuildCombinedDistanceMap()     [Combine 3 matrices via routing logic]
    ├─ For each (origin, destination):
    │  ├─ Check: origin_location → nearby_station_A (walk2station)
    │  ├─ Check: station_A → station_B via GTFS (transit_time)
    │  ├─ Check: station_B → destination (activeODM walking)
    │  └─ If all exists & total_time < max_total: include route
    └─ Return: combined_routes with segments
  → Export_CombinedGeoJSON()           [Multimodal result fields]
```

#### D. DATA STRUCTURE EXPANSION

**Current DistanceMap**:
```python
DistanceMap[origin][destination] = (distance_m, duration_s, walk_time_min)
```

**New CombinedDistanceMap** (proposed):
```python
CombinedDistanceMap[origin][destination] = {
    'total_distance': total_m,
    'total_time': total_min,
    'access_distance': walk_m,
    'transit_time': transit_min,
    'egress_distance': walk_m,
    'station_pair': (station_a_id, station_b_id),
    'route_viable': True/False
}
```

#### E. IO FUNCTIONS NEEDED

**Current** (from Analytics/IO.py):
- `read_ODM(filepath, remove_prefix=True, ..., selection=None, limit=0)`

**Needed for CombinedODM**:
- `read_ODM()` → Use as-is for access & egress walking
- `read_GTFS_Matrix()` → NEW function to read station-to-station transit matrix
  - Parameters: filepath, max_transit_time
  - Returns: `GTFS[station_a][station_b] = (distance, transit_time_min)`
- `combine_odm_matrices()` → NEW function to compute multimodal routing
  - Inputs: walk2station_ODM, GTFS, activeODM, numeric constraints
  - Returns: combined_distance_map

#### F. EXPORT CHANGES

**Current sub_Export_GeoJSON()**:
- Creates fields: `from_{origin_name}_Distance`, `from_{origin_name}_Duration`

**New sub_Export_CombinedGeoJSON()**:
- Creates fields per origin:
  - `from_{origin_name}_AccessWalk_m`
  - `from_{origin_name}_TransitTime_min`
  - `from_{origin_name}_EgressWalk_m`
  - `from_{origin_name}_TotalTime_min`
  - `from_{origin_name}_StationPair` (optional: "STA→STB")

#### G. VALIDATION & CONSTRAINTS

**New Evaluate() checks**:
- ✓ Three ODM files must exist and be readable
- ✓ First ODM should contain all destination IDs
- ✓ Second ODM (walk2station) should have origins matching input layer
- ✓ GTFS matrix should have consistent station IDs
- ⚠ Warn if few routes produced (e.g., <30% of origin-destination pairs viable)

---

## Part 7: Implementation Recommendations

### 7.1 Code Reuse Strategy
| Component | Reuse? | Notes |
|-----------|--------|-------|
| Dialog class structure | ✓ Much | Keep BaseODMDialog, inherit CombinedODMDialog |
| `sub_collectPairs()` | ✓ Yes | Same logic for extracting origins |
| `read_ODM()` | ✓ Yes | Works for both access/egress walking ODM files |
| `Evaluate()` | ~ Partial | Extend with 3-file validation |
| `Build()` | ~ Partial | Replace logic, keep structure/messaging |
| `updateLayer()`  | ✓ Yes | Same layer change handling |
| Settings persistence | ✓ Yes | Extend with 3 file paths + 3 numeric inputs |
| Progress bar/logging | ✓ Yes | Same feedback mechanisms |

### 7.2 New Files to Create
```
plugins/DPF/
├─ combined_odm_distancemap_dialog_base.ui  [NEW: Extended UI]
├─ combined_odm_distancemap_dialog.py       [NEW: Dialog class]
├─ Analytics/
│  └─ IO_Multimodal.py                      [NEW: GTFS reader & combiner]
└─ discrete_proximity_framework.py           [MODIFY: Register new dialog]
```

### 7.3 Suggested Method Skeleton for CombinedODMDistanceMapDialog

```python
class CombinedODMDistanceMapDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None, iface=None):
        # Initialize 3 file paths, 3 numeric inputs
        
    def Build(self):
        # Step 1: Collect origins (reuse sub_collectPairs)
        # Step 2: Load 3 ODM files
        #   - activeODM_data = read_ODM(...)
        #   - gtfs_data = read_GTFS_Matrix(...) [NEW]
        #   - walk2station_data = read_ODM(...) 
        # Step 3: Combine routing
        #   - combined_map = sub_CombinedDistanceMap(...)
        # Step 4: Export
        #   - sub_Export_CombinedGeoJSON(...)
        
    def sub_CombinedDistanceMap(self, walk2station, gtfs, activeODM, origins):
        # Nested loops:
        # for each origin in walk2station:
        #   for each destination in activeODM:
        #     for each station pair in GTFS:
        #       if walk2station[origin][station_A] AND 
        #          GTFS[station_A][station_B] AND
        #          activeODM[station_B][destination]:
        #         Calculate total time/distance
        #         Store in CombinedMap
        return CombinedMap
```

---

## Summary Table: Workflow Crosswalk

| Process Step | Current Method | Current Inputs | Current Outputs | For CombinedODM |
|---|---|---|---|---|
| **Prepare** | `prep_Defaults()` | Settings | UI initialized | Extend: 3 files, 3 dials |
| **Collect** | `sub_collectPairs()` | Layer + fields | origins, selection | Reuse: same logic |
| **Validate** | `Evaluate()` | User inputs | pass/fail | Extend: 3-file checks |
| **Load Data** | `read_ODM()` | 1 SQLite file | ODM dict | Use 3x for multi-modal |
| **Compute** | `sub_BuildDistanceMap()` | ODM + origins | DistanceMap | Replace: routing logic |
| **Export** | `sub_Export_GeoJSON()` | DistanceMap | GeoJSON layer | Extend: more fields |
| **Log** | `_log()` | Message | QGIS log | Reuse: same |

---

## Conclusion

The existing ActiveODMDistanceMapDialog provides a **solid architectural template** for the CombinedODM_DistanceMap. The main adaptations needed are:

1. **UI**: Add 2 more file selectors and adjust numeric inputs
2. **Build workflow**: Replace `sub_BuildDistanceMap()` with multimodal routing combining 3 ODM matrices
3. **IO functions**: Add GTFS reader and route combiner in `Analytics/IO_Multimodal.py`
4. **Export**: Extend field generation to show multimodal journey segments
5. **Settings**: Persist 3 file paths instead of 1

The **structural patterns** (signal handling, field mapping, progress updates, settings persistence) are highly reusable.
