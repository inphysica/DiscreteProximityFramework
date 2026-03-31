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
Example:
```
C:\Users\raul\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\DiscreteProximityFramework
```

**macOS:**
```
~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins
```
Example:
```
/Users/username/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/DiscreteProximityFramework
```

**Linux:**
```
~/.local/share/QGIS/QGIS3/profiles/default/python/plugins
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

### POI Combined Reach Dialog
- **Group attribute selection** - Group POIs by custom attributes
- **Weight attribute selection** - Weight POIs by custom numeric attributes
- **Decay analysis** - Apply decay functions to POI reachability
- **File load estimation** - Real-time estimates of file loading duration
- **Settings persistence** - All parameters saved and restored across sessions
- **Informational hints** - Visual guidance for input parameters with grey-colored helper text

## Datasets:

### Origin-Destination Pairs

- [Acrive Mobility ODM](https://www.dropbox.com/scl/fi/9oa0fuhag1f7adzd8bl28/ODM-v6B-_ActiveMobility-16km.SQLite?rlkey=1sumzcohot0vbaeuudu33ccei&dl=0) covers 16km distance from between all cells
- [Public transportaion PT-to-PT ODM](https://www.dropbox.com/scl/fi/9oqi28zq21xbnahrorbc5/Eesti_PT2PT-240min-_Transfer-15min-_WS1_0700.SQLite?rlkey=u0bm8m2ki41t3gvf2t4gy6kga&dl=0) covers all movements betweeen all station in 3h range. 
- [Walking to stations](https://www.dropbox.com/scl/fi/69icutj32sdv0hdeioeha/ODM-v6B-_PTAccess-W20min.SQLite?rlkey=zb331iqob5lr44iq531u79jnw&dl=0) covers all walks from origins or destination to station in max 20min.
- [Distance to park](https://www.dropbox.com/scl/fi/ufz1itqw8qt63oyqhe4x8/ODM-v6B-_2.6km_EE2NATUTRE.SQLite?rlkey=idnipuq6gunbusei23v4i6lvd&dl=0) covers all distance from origin or destination to road sample points. 

### Grids and Points

- [Grid](https://www.dropbox.com/scl/fi/42bztb0ux26ggz6hkkq52/AGRD_EE_v6B-Grid.geojson?rlkey=vmzaabvshvebd59uab3iidj4n&dl=0)
- [Points of interest](https://www.dropbox.com/scl/fi/2ralmcq9a725ufwzhx7gu/POI_v12-20250410A-beta.geojson?rlkey=zqfjwy6e49ypbhl96s1zga7ka&dl=0)




