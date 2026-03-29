# DiscreteProximityFramework QGIS Plugin

A QGIS plugin providing multiple reachability and distance analysis tools based on Origin-Destination Matrices (ODM). Supports Active Mobility, Public Transport, Combined Multimodal models, and POI-based analysis.

## Installation:
- Copy the `DiscreteProximityFramework` folder into your QGIS plugins directory.
- Restart QGIS or use Plugin Manager -> Refresh.
- Enable the plugin in Plugin Manager.

## Usage:
The plugin provides four analysis tools accessible from the Plugins menu and toolbar:

1. **Active Model Distance Map** - Calculate distance/duration maps using Active Mobility ODM
2. **Combined Model Distance Map** - Multimodal analysis combining Active ODM + GTFS + Walking
3. **ODM Reach** - Generic ODM reachability analysis
4. **POI Combined Reach** - Combined reachability analysis from Points of Interest

## Files:

### Core Plugin Files
- `discrete_proximity_framework.py` - Main plugin class, menu/toolbar registration, and action handlers
- `__init__.py` - QGIS plugin factory
- `metadata.txt` - Plugin metadata

### Analysis Dialogs
- `activeodm_distancemap_dialog.py` - Active Mobility distance map analysis
- `activeodm_distancemap_dialog_base.ui` - UI definition for Active Mobility dialog
- `combinedodm_distancemap_dialog.py` - Combined multimodal distance map analysis
- `combinedodm_distancemap_dialog_base.ui` - UI definition for Combined model dialog
- `odm_reach_dialog.py` - Generic ODM reachability analysis
- `odm_reach_dialog_base.ui` - UI definition for ODM Reach dialog
- `poi_combined_reach_dialog.py` - POI combined reachability analysis
- `combinedreach_analysis_dialog.py` - Combined reach analysis utility

### Analytics Module
- `Analytics/IO.py` - ODM file reading and processing utilities
- `Analytics/Access.py` - Accessibility analysis functions

### Resources
- `icons/` - Toolbar and menu icons for analysis tools


Datasets (ODMs)

- [Acrive Mobility ODM](https://www.dropbox.com/scl/fi/9oa0fuhag1f7adzd8bl28/ODM-v6B-_ActiveMobility-16km.SQLite?rlkey=1sumzcohot0vbaeuudu33ccei&dl=0) covers 16km distance from between all cells
- [Public transportaion PT-to-PT ODM](https://www.dropbox.com/scl/fi/9oqi28zq21xbnahrorbc5/Eesti_PT2PT-240min-_Transfer-15min-_WS1_0700.SQLite?rlkey=u0bm8m2ki41t3gvf2t4gy6kga&dl=0) covers all movements betweeen all station in 3h range. 
- [Walking to stations](https://www.dropbox.com/scl/fi/69icutj32sdv0hdeioeha/ODM-v6B-_PTAccess-W20min.SQLite?rlkey=zb331iqob5lr44iq531u79jnw&dl=0) covers all walks from origins or destination to station in max 20min.
- [Distance to park](https://www.dropbox.com/scl/fi/ufz1itqw8qt63oyqhe4x8/ODM-v6B-_2.6km_EE2NATUTRE.SQLite?rlkey=idnipuq6gunbusei23v4i6lvd&dl=0) covers all distance from origin or destination to road sample points. 

Datasets

- [Grid](https://www.dropbox.com/scl/fi/42bztb0ux26ggz6hkkq52/AGRD_EE_v6B-Grid.geojson?rlkey=vmzaabvshvebd59uab3iidj4n&dl=0)
- [Points of interest](https://www.dropbox.com/scl/fi/2ralmcq9a725ufwzhx7gu/POI_v12-20250410A-beta.geojson?rlkey=zqfjwy6e49ypbhl96s1zga7ka&dl=0)


