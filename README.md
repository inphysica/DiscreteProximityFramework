# DiscreteProximityFramework QGIS Plugin

This is a minimal QGIS plugin scaffold named "DiscreteProximityFramework". It provides one action: "ActiveODM_DistanceMap".

Installation:
- Copy the `DiscreteProximityFramework` folder into your QGIS plugins directory.
- Restart QGIS or use Plugin Manager -> Refresh.
- Enable the plugin in Plugin Manager.

Usage:
- Open QGIS; in the Plugins menu you'll find "DiscreteProximityFramework".
- Click the "Active ODM DistanceMap" 

Files:
- `discrete_proximity_framework.py` - main plugin class and action handler.
- `metadata.txt` - plugin metadata.
- `__init__.py` - factory for QGIS to load the plugin.

Notes:
- Replace the placeholder message box in `run_activeodm_distancemap` with real processing code.
- Add an `icon.png` file if you want a toolbar icon.


Datasets (ODMs)

- [Acrive Mobility ODM](https://www.dropbox.com/scl/fi/9oa0fuhag1f7adzd8bl28/ODM-v6B-_ActiveMobility-16km.SQLite?rlkey=1sumzcohot0vbaeuudu33ccei&dl=0) covers 16km distance from between all cells
- [Public transportaion PT-to-PT ODM](https://www.dropbox.com/scl/fi/9oqi28zq21xbnahrorbc5/Eesti_PT2PT-240min-_Transfer-15min-_WS1_0700.SQLite?rlkey=u0bm8m2ki41t3gvf2t4gy6kga&dl=0) covers all movements betweeen all station in 3h range. 

Dataset

- [Grid](https://www.dropbox.com/scl/fi/42bztb0ux26ggz6hkkq52/AGRD_EE_v6B-Grid.geojson?rlkey=vmzaabvshvebd59uab3iidj4n&dl=0)

