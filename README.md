# DiscreteProximityFramework QGIS Plugin

A QGIS plugin providing multiple reachability and distance analysis tools based on Origin-Destination Matrices (ODM). Supports Active Mobility, Public Transport, Combined Multimodal models, and POI-based analysis.

## Installation:

### From GitHub Releases (Recommended)

1. Download the latest release from [GitHub Releases](https://github.com/inphysica/DiscreteProximityFramework/releases)
2. Extract the ZIP file
3. Copy the `DiscreteProximityFramework` folder to your QGIS plugins directory:

**Windows:**
```
C:\Users\[YOUR_USERNAME]\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins
```

**macOS:**
```
~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins
```

4. Restart QGIS
5. Enable the plugin in **Plugins → Manage and Install Plugins**
   - Search for "Discrete Proximity Framework"
   - Check the checkbox to enable

### From Git Clone

```bash
cd path/to/plugins/folder
git clone https://github.com/inphysica/DiscreteProximityFramework.git DiscreteProximityFramework
```

Then restart QGIS and enable in Plugin Manager.




## Usage:
The plugin provides four analysis tools accessible from the Plugins menu and toolbar:

1. **Active Model Distance Map** - Calculate distance/duration maps using Active Mobility ODM
2. **Combined Model Distance Map** - Multimodal analysis combining Active ODM + GTFS + Walking
4. **POI Combined Reach** - Combined reachability analysis from Points of Interest

## Key Concepts:

### Grid Layer (Input)
The **Grid Layer** is your main geometry layer and acts as the foundation for all analyses. 

**Important Requirements:**
- Must have an **ID field** that matches the origin/destination IDs in your ODM files
- Typically named `PosID` but can be any numeric or text field
- This ID links your grid cells to the ODM data - ensure they match exactly
- All results are calculated relative to this grid's geometries

**Example:**
```
Grid Layer: agrd_ee_v6b.geojson
ID Field: PosID (values: 1, 2, 3, ... matching ODM origins/destinations)
```

### Results Output
All analysis tools automatically save results as **GeoJSON** files:
- **Output Location:** Same directory as your input grid layer
- **Format:** GeoJSON (.geojson) with all original grid attributes + new analysis columns
- **Naming Convention:** `[GridName]_results_[YYYYMMDD_HHMM].geojson`
- **Columns Added:** Distance and/or duration from each origin/destination

**Both tools save results regardless of:**
- Whether you clicked OK or Cancel (settings are persisted)
- Your selection choices (results reflect your current parameters)

### Settings
- **Automatic Persistence:** All parameters (paths, numeric values, selections, checkboxes) are saved automatically
- **Cancel Button:** Even if you cancel, your settings are preserved for next session
- **Per-Tool Storage:** Each tool maintains independent settings
- **Settings Location:** QGIS application settings (encrypted in QGIS configuration)





## Files:

### Core Plugin Files
- `discrete_proximity_framework.py` - Main plugin class, menu/toolbar registration, and action handlers
- `__init__.py` - QGIS plugin factory
- `metadata.txt` - Plugin metadata

### Analysis Dialogs
- `activeodm_distancemap_dialog.py` - Active Mobility distance map analysis with file load estimation
- `activeodm_distancemap_dialog_base.ui` - UI definition for Active Mobility dialog
- `combinedodm_distancemap_dialog.py` - Combined multimodal distance map analysis with file load estimation
- `combinedodm_distancemap_dialog_base.ui` - UI definition for Combined model dialog with hint labels
- `poi_combined_reach_dialog.py` - POI combined reachability analysis with grouping, weighting, and decay options
- `poi_combined_reach_dialog_base.ui` - UI definition for POI Combined Reach dialog with hint labels and suffix field

### Analytics Module
- `Analytics/IO.py` - ODM file reading and processing utilities; file load time estimation
- `Analytics/Access.py` - Accessibility analysis functions; PTODM_ByOrigin with performance timing measurements

### Resources
- `icons/` - Toolbar and menu icons for analysis tools

## Features:

### General Features (All Tools)
- **File Load Estimation** - Real-time estimates of file loading duration before processing
- **Settings Persistence** - All parameters automatically saved and restored across QGIS sessions
- **User-Friendly Hints** - Grey informational labels explaining parameter meanings
- **Automatic Results Export** - Results saved as GeoJSON copies of input grid with analysis columns
- **Performance Monitoring** - Console logging of processing times for diagnostics

### Active Model Distance Map & Combined Model Distance Map
- **Walking Speed Guidance** - Built-in hints for typical walking/cycling speeds
- **Max Walk Time Parameters** - Configurable limits for destination accessibility without transit
- **Direct Output** - Results immediately appear in QGIS as new layers

### POI Combined Reach Dialog
- **Group attribute selection** - Group POIs by custom attributes (e.g., category, type, region)
- **Weight attribute selection** - Weight POIs by custom numeric attributes (e.g., importance, capacity)
- **Decay analysis** - Apply exponential decay functions to POI reachability over time
- **Flexible POI Configuration** - Use groups only, weights only, or both combined
- **Multimodal Support** - Analyze reachability combining walking + public transport
- **Intelligent Defaults** - Remembers your POI layer and field selections

### Performance & Optimization
- **Loop Timing Analysis** - Detailed performance measurements for debugging and optimization
- **Progress Bars** - Visual feedback during long operations
- **Decay Plateau Options** - No decay during initial period, gradual decline afterwards

## Data Requirements

### Input Data
1. **Grid Layer** (REQUIRED)
   - Polygon or point geometry layer
   - Must have an ID field matching ODM origins/destinations
   - Typical field name: `PosID` (but flexible - can be any name)
   - Supported formats: Shapefile, GeoJSON, GeoPackage, etc.

2. **ODM Files** (REQUIRED)
   - SQLite format (.sqlite, .db, .gpkg)
   - Contains origin-destination matrices with IDs matching grid layer
   - Typical fields: origin, destination, distance, duration

3. **POI Layer** (OPTIONAL - for POI Combined Reach only)
   - Point or polygon geometry layer
   - Should have ID field matching grid layer IDs
   - Optional: group attribute field (e.g., category, type, region)
   - Optional: numeric weight field (e.g., capacity, popularity, importance)

### ID Field Matching
**Critical:** Ensure ID values in grid layer exactly match IDs in ODM files:
- Both must be same data type (text or numeric)
- Both must have identical values (no prefixes, suffixes, or transformations)
- Example: Grid layer `PosID=001` must match ODM origin/destination `001` (not `1`)

## Troubleshooting

### Common Issues

**"Missing file" error**
- Ensure all ODM files are selected before clicking OK
- Verify file paths are correct and files exist

**"No results generated" or "No matching IDs"**
- Check that grid layer ID field values match ODM IDs exactly (character for character)
- Verify ID field data types match (both text or both numeric)
- Try opening ODM files with SQLite browser to inspect ID values

**"Files loading very slowly"**
- Large ODM files take time to load
- Plugin shows estimated load time - be patient and wait for completion
- Consider using smaller geographic areas or shorter time windows in your data

**"Settings not saved between sessions"**
- Settings are automatically saved whenever you:
  - Click OK button (saves + runs analysis)
  - Click Cancel button (saves settings without running)
  - Click Reset button (saves reset values)
- Verify QGIS has file write permissions
- Check QGIS console for any permission-related errors

**"Results layer not appearing in QGIS"**
- Check QGIS Messages Log (View → Panels → Messages)
- GeoJSON files are always saved to the same directory as input grid layer
- Verify folder has write permissions
- Try manually opening the .geojson file (File → Open)

## Sample Datasets:

### Origin-Destination Matrices

- [Active Mobility ODM](https://www.dropbox.com/scl/fi/9oa0fuhag1f7adzd8bl28/ODM-v6B-_ActiveMobility-16km.SQLite?rlkey=1sumzcohot0vbaeuudu33ccei&dl=0) covers 16km distance from between all cells
- [Public transportation PT-to-PT ODM](https://www.dropbox.com/scl/fi/9oqi28zq21xbnahrorbc5/Eesti_PT2PT-240min-_Transfer-15min-_WS1_0700.SQLite?rlkey=u0bm8m2ki41t3gvf2t4gy6kga&dl=0) covers all movements between all stations in 3h range. 
- [Walking to stations](https://www.dropbox.com/scl/fi/69icutj32sdv0hdeioeha/ODM-v6B-_PTAccess-W20min.SQLite?rlkey=zb331iqob5lr44iq531u79jnw&dl=0) covers all walks from origins or destination to station in max 20min.
- [Distance to park](https://www.dropbox.com/scl/fi/ufz1itqw8qt63oyqhe4x8/ODM-v6B-_2.6km_EE2NATUTRE.SQLite?rlkey=idnipuq6gunbusei23v4i6lvd&dl=0) covers all distances from origin or destination to road sample points. 

### Grids and Points

- [Grid](https://www.dropbox.com/scl/fi/42bztb0ux26ggz6hkkq52/AGRD_EE_v6B-Grid.geojson?rlkey=vmzaabvshvebd59uab3iidj4n&dl=0)
- [Points of interest](https://www.dropbox.com/scl/fi/2ralmcq9a725ufwzhx7gu/POI_v12-20250410A-beta.geojson?rlkey=zqfjwy6e49ypbhl96s1zga7ka&dl=0)

## License

MIT License - See [LICENSE](LICENSE) file for details

## Support & Contributions

- **Issues:** Report bugs at [GitHub Issues](https://github.com/inphysica/DiscreteProximityFramework/issues)
- **Contributions:** Pull requests welcome on [GitHub](https://github.com/inphysica/DiscreteProximityFramework)
- **Contact:** dev@inphysica.com
