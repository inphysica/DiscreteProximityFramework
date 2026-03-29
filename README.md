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
- [Walking to stations](https://www.dropbox.com/scl/fi/69icutj32sdv0hdeioeha/ODM-v6B-_PTAccess-W20min.SQLite?rlkey=zb331iqob5lr44iq531u79jnw&dl=0) covers all walks from origins or destination to station in max 20min.
- [Distance to park](https://www.dropbox.com/scl/fi/ufz1itqw8qt63oyqhe4x8/ODM-v6B-_2.6km_EE2NATUTRE.SQLite?rlkey=idnipuq6gunbusei23v4i6lvd&dl=0) covers all distance from origin or destination to road sample points. 
Dataset

- [Grid](https://www.dropbox.com/scl/fi/42bztb0ux26ggz6hkkq52/AGRD_EE_v6B-Grid.geojson?rlkey=vmzaabvshvebd59uab3iidj4n&dl=0)
- [Points of interest](https://www.dropbox.com/scl/fi/2ralmcq9a725ufwzhx7gu/POI_v12-20250410A-beta.geojson?rlkey=zqfjwy6e49ypbhl96s1zga7ka&dl=0)


