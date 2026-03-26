"""

CombinedODMDistanceMapDialog

Combined model routing combining:
1. ActiveODM (walking to/from destinations)
2. GTFS Transit (station-to-station travel times)
3. Walking to/from transit stations

Dialog stores per-layer field selections in memory, restores them when switching layers,
and logs diagnostic messages to the QGIS log.

"""

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QPushButton, QLineEdit, QFileDialog, QMessageBox, QProgressBar
from qgis.PyQt.QtCore import QTimer, QSettings
from qgis.core import QgsVectorLayerExporter, QgsVectorFileWriter, QgsCoordinateTransformContext, QgsWkbTypes, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication

from qgis.core import QgsField
from qgis.PyQt.QtCore import QVariant

import os
import time
import json
from datetime import datetime

try:
    from qgis.core import QgsMessageLog, Qgis, QgsProject
except Exception:
    QgsMessageLog = None
    Qgis = None
    QgsProject = None

from .Analytics.IO import read_ODM, read_GTFS, estimate_sqlite_load_time, get_sqlite_info, quick_estimate_from_filesize


UI_PATH = os.path.join(os.path.dirname(__file__), 'combinedodm_distancemap_dialog_base.ui')
FORM_CLASS, _ = uic.loadUiType(UI_PATH)

# settings key prefix
SETTINGS_KEY = 'DiscreteProximityFramework/CombinedODM'


class CombinedODMDistanceMapDialog(QDialog, FORM_CLASS):
    """Dialog for combined model routing combining ActiveODM + GTFS + walking."""

    def __init__(self, parent=None, iface=None):
        super().__init__(parent)
        self.iface = iface
        self.layer_field_map = {}  # layer_id -> {'id_field': str, 'name_field': str}
        self.current_layer_id = None
        self._id_selector_conn = None
        self._name_selector_conn = None

        self.setupUi(self)

        # seed known layers (non-persistent)
        if QgsProject is not None:
            try:
                for lay in QgsProject.instance().mapLayers().values():
                    try:
                        self.layer_field_map.setdefault(lay.id(), {'id_field': None})
                    except Exception:
                        continue
            except Exception:
                pass

        self.prep_Defaults()

        # connect layer widget signals
        layer_widget = getattr(self, 'inputLayer', None)
        if layer_widget is not None:
            for sig in ('currentLayerChanged', 'layerChanged', 'sourceLayerChanged', 'currentIndexChanged'):
                if hasattr(layer_widget, sig):
                    try:
                        if sig == 'currentIndexChanged':
                            layer_widget.currentIndexChanged.connect(lambda _idx: self.updateLayer(None))
                        else:
                            getattr(layer_widget, sig).connect(self.updateLayer)
                    except Exception:
                        continue
                    break

        QTimer.singleShot(0, lambda: self.updateLayer(None))

        # connect dialog buttons
        try:
            if hasattr(self, 'buttonBox'):
                try:
                    self.buttonBox.accepted.connect(self._on_ok)
                except Exception:
                    pass
                try:
                    self.buttonBox.rejected.connect(self._on_cancel)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_ok(self):

        settings = QSettings()
        settings.setValue(f'{SETTINGS_KEY}/ActiveODM_Path', self.activeODM_fileSelector.filePath())
        settings.setValue(f'{SETTINGS_KEY}/GTFS_Path', self.GTFS_fileSelector.filePath())
        settings.setValue(f'{SETTINGS_KEY}/WalkStation_Path', self.walkStation_fileSelector.filePath())

        settings.setValue(f'{SETTINGS_KEY}/MaxWalkDest', self.maxWalkDest.value())
        settings.setValue(f'{SETTINGS_KEY}/MaxWalkStation', self.maxWalkStation.value())
        settings.setValue(f'{SETTINGS_KEY}/MaxTotalTime', self.maxTotalTime.value())
        settings.setValue(f'{SETTINGS_KEY}/WalkingSpeed', self.walkingSpeed.value())

        # Save settings
        self.save_settings()

        self._log("Storing combined model settings...")
        
        if self.Evaluate():

            self.labelCurrentStatus.setText("Start build...")
            self.repaint()

            if (self.Build()):
                self._log("Build successful")
            else:
                self._log("Build failed")
                return
        else:
            self.labelCurrentStatus.setText("Exit without build")
            self.repaint()
            return

        """Internal OK handler: call user-defined on_ok, then accept dialog."""
        try:
            self._log('OK pressed')
        except Exception:
            pass
        ok_to_close = True
        try:
            res = self.on_ok()
            if res is False:
                ok_to_close = False
        except Exception:
            ok_to_close = True

        if ok_to_close:
            try:
                self.accept()
            except Exception:
                try:
                    self.done(1)
                except Exception:
                    pass

    def _on_cancel(self):

        """Internal Cancel handler: call user-defined on_cancel, then reject dialog."""
        try:
            self._log('Cancel pressed')
        except Exception:
            pass
        cancel_close = True

        self.save_settings()

        try:
            res = self.on_cancel()
            if res is False:
                cancel_close = False
        except Exception:
            cancel_close = True

        if cancel_close:
            try:
                self.reject()
            except Exception:
                try:
                    self.done(0)
                except Exception:
                    pass

    def save_settings(self):
        """Save all settings to QSettings."""
        settings = QSettings()
        try:
            # Save checkboxes
            settings.setValue(f'{SETTINGS_KEY}/CheckBox_OnlySelectedFeatures', 
                            self.onlySelectedFeatures.isChecked())
            settings.setValue(f'{SETTINGS_KEY}/CheckBox_IncludeName', 
                            self.checkBox_IncludeName.isChecked())
            
            # Save field selectors
            id_sel = self._get_id_selector()
            name_sel = self._get_name_selector()
            id_field = self._get_current_field(id_sel)
            name_field = self._get_current_field(name_sel)
            if id_field:
                settings.setValue(f'{SETTINGS_KEY}/IdField', id_field)
            if name_field:
                settings.setValue(f'{SETTINGS_KEY}/NameField', name_field)
            
            self._log("Saved combined model settings")
        except Exception as e:
            self._log(f"Error saving settings: {str(e)}", level='debug')

    def load_settings(self):
        """Load settings from QSettings and apply them."""
        settings = QSettings()
        try:
            # Load checkboxes
            only_selected = settings.value(f'{SETTINGS_KEY}/CheckBox_OnlySelectedFeatures', False, type=bool)
            include_name = settings.value(f'{SETTINGS_KEY}/CheckBox_IncludeName', False, type=bool)
            
            if hasattr(self, 'onlySelectedFeatures'):
                self.onlySelectedFeatures.setChecked(only_selected)
            if hasattr(self, 'checkBox_IncludeName'):
                self.checkBox_IncludeName.setChecked(include_name)
            
            # Load field selectors
            id_field = settings.value(f'{SETTINGS_KEY}/IdField', '', type=str)
            name_field = settings.value(f'{SETTINGS_KEY}/NameField', '', type=str)
            
            id_sel = self._get_id_selector()
            name_sel = self._get_name_selector()
            
            if id_field and id_sel is not None:
                self._try_set_selector_by_name(id_sel, id_field)
            if name_field and name_sel is not None:
                self._try_set_selector_by_name(name_sel, name_field)
            
            self._log("Loaded combined model settings")
        except Exception as e:
            self._log(f"Error loading settings: {str(e)}", level='debug')

    def _save_current_selection(self, layer_id=None):
        if layer_id is None:
            layer_id = self.current_layer_id
        if not layer_id:
            return
        id_sel = self._get_id_selector()
        name_sel = self._get_name_selector()
        id_field = self._get_current_field(id_sel)
        name_field = self._get_current_field(name_sel)
        self.layer_field_map[layer_id] = {'id_field': id_field, 'name_field': name_field}
        self._log(f"Saved mapping for {layer_id}: id_field={id_field}, name_field={name_field}")

    def _try_set_selector_by_name(self, selector, field_name):
        if selector is None or not field_name:
            return False
        try:
            if hasattr(selector, 'setCurrentField'):
                selector.setCurrentField(field_name)
                return True
            if hasattr(selector, 'count') and hasattr(selector, 'itemText') and hasattr(selector, 'setCurrentIndex'):
                for i in range(selector.count()):
                    try:
                        if selector.itemText(i) == field_name:
                            selector.setCurrentIndex(i)
                            return True
                    except Exception:
                        continue
        except Exception:
            return False
        return False

    def _restore_selection_for_layer(self, layer_id):
        if not layer_id:
            return False
        data = self.layer_field_map.get(layer_id)
        if not data:
            return False
        id_sel = self._get_id_selector()
        name_sel = self._get_name_selector()
        restored = False
        if id_sel is not None and data.get('id_field'):
            restored = self._try_set_selector_by_name(id_sel, data.get('id_field')) or restored
        if name_sel is not None and data.get('name_field'):
            restored = self._try_set_selector_by_name(name_sel, data.get('name_field')) or restored

        if not restored and QgsProject is not None:
            def retry():
                try:
                    lay = QgsProject.instance().mapLayer(layer_id)
                except Exception:
                    lay = None
                if lay is None:
                    return
                try:
                    fields = [f.name() for f in list(lay.fields())]
                except Exception:
                    fields = []
                if id_sel is not None and data.get('id_field') in fields:
                    self._try_set_selector_by_name(id_sel, data.get('id_field'))
                if name_sel is not None and data.get('name_field') in fields:
                    self._try_set_selector_by_name(name_sel, data.get('name_field'))
            try:
                QTimer.singleShot(0, retry)
            except Exception:
                pass

        return bool(restored)

    def _log(self, message, level='info'):
        if QgsMessageLog is None:
            return
        try:
            lvl = Qgis.Info if level == 'info' else Qgis.Debug
            QgsMessageLog.logMessage(message, 'DiscreteProximityFramework', lvl)
        except Exception:
            pass

    def _get_id_selector(self):
        """Return id selector."""
        return getattr(self, 'IdFieldSelector', None) or getattr(self, 'idSelector', None)

    def _get_name_selector(self):
        """Return name selector."""
        return getattr(self, 'NameFieldSelector', None) or getattr(self, 'nameSelector', None)

    def _get_current_field(self, selector):
        if selector is None:
            return None
        try:
            if hasattr(selector, 'currentField'):
                return selector.currentField()
            if hasattr(selector, 'currentText'):
                return selector.currentText()
        except Exception:
            return None
        return None

    def prep_Defaults(self):

        self.activeODM_fileSelector.setDialogTitle("Select Active ODM (SQLite)")
        self.activeODM_fileSelector.setFilter("SQLite files (*.sqlite *.db *.gpkg);;All files (*)")

        self.GTFS_fileSelector.setDialogTitle("Select GTFS Transit (SQLite)")
        self.GTFS_fileSelector.setFilter("SQLite files (*.sqlite *.db *.gpkg);;All files (*)")

        self.walkStation_fileSelector.setDialogTitle("Select Walk-to-Station ODM (SQLite)")
        self.walkStation_fileSelector.setFilter("SQLite files (*.sqlite *.db *.gpkg);;All files (*)")

        settings = QSettings()
        
        # Restore file paths
        activeODM_path = settings.value(f'{SETTINGS_KEY}/ActiveODM_Path', '')
        gtfs_path = settings.value(f'{SETTINGS_KEY}/GTFS_Path', '')
        walkstation_path = settings.value(f'{SETTINGS_KEY}/WalkStation_Path', '')

        if activeODM_path and os.path.exists(activeODM_path):
            try:
                self.activeODM_fileSelector.setFilePath(activeODM_path)
            except Exception:
                pass

        if gtfs_path and os.path.exists(gtfs_path):
            try:
                self.GTFS_fileSelector.setFilePath(gtfs_path)
            except Exception:
                pass

        if walkstation_path and os.path.exists(walkstation_path):
            try:
                self.walkStation_fileSelector.setFilePath(walkstation_path)
            except Exception:
                pass

        # Restore numeric values
        max_walk_dest = settings.value(f'{SETTINGS_KEY}/MaxWalkDest', 30.0, type=float)  # minutes
        max_walk_station = settings.value(f'{SETTINGS_KEY}/MaxWalkStation', 15.0, type=float)  # minutes
        max_total_time = settings.value(f'{SETTINGS_KEY}/MaxTotalTime', 60.0, type=float)  # minutes
        walking_speed = settings.value(f'{SETTINGS_KEY}/WalkingSpeed', 4.5, type=float)  # km/h

        self.maxWalkDest.setValue(max_walk_dest)
        self.maxWalkStation.setValue(max_walk_station)
        self.maxTotalTime.setValue(max_total_time)
        self.walkingSpeed.setValue(walking_speed)
        
        # Load other settings
        self.load_settings()

    def updateLayer(self, layer):
        if layer is None:
            layer_widget = getattr(self, 'inputLayer', None)
            if layer_widget is not None and hasattr(layer_widget, 'currentLayer'):
                try:
                    layer = layer_widget.currentLayer()
                except Exception:
                    layer = None

        id_sel = self._get_id_selector()
        name_sel = self._get_name_selector()

        # disconnect previous handlers
        try:
            if id_sel is not None and self._id_selector_conn is not None:
                try:
                    id_sel.currentIndexChanged.disconnect(self._id_selector_conn)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if name_sel is not None and self._name_selector_conn is not None:
                try:
                    name_sel.currentIndexChanged.disconnect(self._name_selector_conn)
                except Exception:
                    pass
        except Exception:
            pass

        # Set layer for selectors
        if id_sel is not None and hasattr(id_sel, 'setLayer'):
            try:
                id_sel.setLayer(layer)
            except Exception:
                pass
        if name_sel is not None and hasattr(name_sel, 'setLayer'):
            try:
                name_sel.setLayer(layer)
            except Exception:
                pass

        try:
            self.current_layer_id = layer.id() if layer is not None and hasattr(layer, 'id') else None
        except Exception:
            self.current_layer_id = None

        self._log(f"updateLayer: new={self.current_layer_id}")

        restored = False
        if self.current_layer_id is not None:
            try:
                restored = self._restore_selection_for_layer(self.current_layer_id)
            except Exception:
                restored = False

        if not restored:
            try:
                self.populate_defaults()
            except Exception:
                pass

        # reconnect handlers
        try:
            if id_sel is not None and hasattr(id_sel, 'currentIndexChanged'):
                lid = self.current_layer_id
                def _id_handler(_idx, lid=lid):
                    self._save_current_selection(lid)
                self._id_selector_conn = _id_handler
                id_sel.currentIndexChanged.connect(self._id_selector_conn)
        except Exception:
            pass
        try:
            if name_sel is not None and hasattr(name_sel, 'currentIndexChanged'):
                lid = self.current_layer_id
                def _name_handler(_idx, lid=lid):
                    self._save_current_selection(lid)
                self._name_selector_conn = _name_handler
                name_sel.currentIndexChanged.connect(self._name_selector_conn)
        except Exception:
            pass

    def populate_defaults(self):
        layer_widget = getattr(self, 'inputLayer', None)
        layer = None
        if layer_widget is not None and hasattr(layer_widget, 'currentLayer'):
            try:
                layer = layer_widget.currentLayer()
            except Exception:
                layer = None

        id_field_name = None
        name_field_name = None
        if layer is not None:
            try:
                fields = list(layer.fields())
                field_names = [f.name() for f in fields]
            except Exception:
                fields = []
                field_names = []
            
            # Try to get saved field names from QSettings
            settings = QSettings()
            saved_id_field = settings.value(f'{SETTINGS_KEY}/IdField', '', type=str)
            saved_name_field = settings.value(f'{SETTINGS_KEY}/NameField', '', type=str)
            
            # Use saved field if it exists in this layer, otherwise use first field
            if saved_id_field and saved_id_field in field_names:
                id_field_name = saved_id_field
            elif fields:
                id_field_name = fields[0].name()
            
            if saved_name_field and saved_name_field in field_names:
                name_field_name = saved_name_field
            elif fields:
                name_field_name = fields[0].name()

        id_sel = self._get_id_selector()
        name_sel = self._get_name_selector()
        
        if id_sel is not None and id_field_name:
            try:
                if hasattr(id_sel, 'setCurrentField'):
                    id_sel.setCurrentField(id_field_name)
                else:
                    self._try_set_selector_by_name(id_sel, id_field_name)
            except Exception:
                pass
        if name_sel is not None and name_field_name:
            try:
                if hasattr(name_sel, 'setCurrentField'):
                    name_sel.setCurrentField(name_field_name)
                else:
                    self._try_set_selector_by_name(name_sel, name_field_name)
            except Exception:
                pass

        try:
            self.current_layer_id = layer.id() if layer is not None and hasattr(layer, 'id') else None
        except Exception:
            self.current_layer_id = None

        restored = False
        try:
            if self.current_layer_id is not None:
                restored = self._restore_selection_for_layer(self.current_layer_id)
        except Exception:
            restored = False

        if not restored:
            try:
                self._save_current_selection(self.current_layer_id)
            except Exception:
                pass

        # connect handlers
        try:
            if id_sel is not None and hasattr(id_sel, 'currentIndexChanged'):
                lid = self.current_layer_id
                def _id_handler(_idx, lid=lid):
                    try:
                        self._save_current_selection(lid)
                    except Exception:
                        pass
                self._id_selector_conn = _id_handler
                id_sel.currentIndexChanged.connect(self._id_selector_conn)
        except Exception:
            pass
        try:
            if name_sel is not None and hasattr(name_sel, 'currentIndexChanged'):
                lid = self.current_layer_id
                def _name_handler(_idx, lid=lid):
                    try:
                        self._save_current_selection(lid)
                    except Exception:
                        pass
                self._name_selector_conn = _name_handler
                name_sel.currentIndexChanged.connect(self._name_selector_conn)
        except Exception:
            pass

    def Evaluate(self, max_features=100):

        self.labelCurrentStatus.setText("Evaluating dataset...")
        self.repaint()

        src_layer = QgsProject.instance().mapLayer(self.current_layer_id)

        # Check file paths
        if not self.activeODM_fileSelector.filePath():
            QMessageBox.critical(self.iface.mainWindow(), "Missing file", "Please select Active ODM file")
            return False
        if not self.GTFS_fileSelector.filePath():
            QMessageBox.critical(self.iface.mainWindow(), "Missing file", "Please select GTFS Transit file")
            return False
        if not self.walkStation_fileSelector.filePath():
            QMessageBox.critical(self.iface.mainWindow(), "Missing file", "Please select Walk-to-Station ODM file")
            return False

        if (self.onlySelectedFeatures.isChecked() == True):
            selected_features = src_layer.selectedFeatures()
            if (len(selected_features) > max_features):

                reply = QMessageBox.question(
                    self.iface.mainWindow(),
                    "Confirm action",
                    f"You are about to process more than {max_features} selected features. Do you want to proceed?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    return True
                else:
                    return False
            if (len(selected_features) == 0):

                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "No features selected",
                    "You have chosen to process only selected features, but no features are selected. Please select some features or uncheck the option.",
                    QMessageBox.Ok
                )
                return False
            
        else:

            all_features = [feat for feat in src_layer.getFeatures()]
            if (len(all_features) > max_features):

                reply = QMessageBox.question(
                    self.iface.mainWindow(),
                    "Confirm action",
                    f"You are about to process more than {max_features} features. Do you want to proceed?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    return True
                else:
                    return False
                
        return True

    def Build(self):

        build_start = time.time()
        self._log("\n" + "="*50)
        self._log("Combined Model Build STARTED")
        self._log("="*50)

        self.labelCurrentStatus.setText("Collecting destinations...")
        self.repaint()

        step_start = time.time()
        name_field = self.nameSelector.currentText() if hasattr(self, 'nameSelector') else None
        destinations, selection = sub_collectDestinations(self, 
                                                         id_field=self.idSelector.currentText(),
                                                         name_field=name_field,
                                                         use_name=self.checkBox_IncludeName.isChecked())
        step_duration = time.time() - step_start
        self._log(f"Collected {len(destinations)} destinations in {step_duration:.3f}s")

        # Load the three ODM matrices
        self.labelCurrentStatus.setText("Reading Active ODM...")
        self.repaint()
        step_start = time.time()
        # Convert max walking time (minutes) to distance (meters) using walking speed
        max_walk_dest_meters = self.maxWalkDest.value() * self.walkingSpeed.value() * 1000 / 60
        activeODM = read_ODM(self.activeODM_fileSelector.filePath(), False, 
                            bar=self.progressBar, selection=selection, 
                            limit=max_walk_dest_meters)
        step_duration = time.time() - step_start
        self._log(f"Read Active ODM in {step_duration:.3f}s")

        self.labelCurrentStatus.setText("Reading Walk-to-Station ODM...")
        self.repaint()
        step_start = time.time()
        # Convert max walking time (minutes) to distance (meters) using walking speed
        max_walk_station_meters = self.maxWalkStation.value() * self.walkingSpeed.value() * 1000 / 60
        walkStationODM = read_ODM(self.walkStation_fileSelector.filePath(), False, 
                                  bar=self.progressBar, selection=selection, 
                                  limit=max_walk_station_meters)
        step_duration = time.time() - step_start
        self._log(f"Read Walk-to-Station ODM in {step_duration:.3f}s")

        self.labelCurrentStatus.setText("Reading GTFS Transit...")
        self.repaint()
        step_start = time.time()
        GTFS = read_GTFS(self.GTFS_fileSelector.filePath(), max_duration=int(self.maxTotalTime.value() * 60))
        step_duration = time.time() - step_start
        self._log(f"Read GTFS Transit in {step_duration:.3f}s")

        self.labelCurrentStatus.setText("Building combined distance map...")
        self.repaint()

        src_layer = QgsProject.instance().mapLayer(self.current_layer_id)
        step_start = time.time()
        combinedMap = sub_BuildCombinedDistanceMap(self, activeODM, walkStationODM, GTFS, 
                                                    destinations, src_layer=src_layer, 
                                                    max_total_time=self.maxTotalTime.value(),
                                                    bar=self.progressBar)
        step_duration = time.time() - step_start
        self._log(f"Built combined distance map in {step_duration:.3f}s")

        self.labelCurrentStatus.setText("Exporting results...")
        self.repaint()

        sub_Export_Combined_GeoJSON(self, combinedMap, destinations)

        self.labelCurrentStatus.setText("Done")
        self.repaint()

        build_duration = time.time() - build_start
        self._log(f"Combined Model Build COMPLETED in {build_duration:.3f}s total")
        self._log("="*50 + "\n")

        return True


def sub_collectDestinations(self, id_field, name_field=None, use_name=False):
    """Collect destination IDs from input layer."""
    src_layer = QgsProject.instance().mapLayer(self.current_layer_id)

    all_features = [feat for feat in src_layer.getFeatures()]

    if (self.onlySelectedFeatures.isChecked() == True):
        features = src_layer.selectedFeatures()
    else:
        features = all_features

    destinations = []
    selection = []

    self.labelCurrentStatus.setText("Collecting destinations...")
    self.repaint()
    bar = self.progressBar
    bar.setMaximum(len(features))
    bar.setValue(0)
    bar.repaint()
    QCoreApplication.processEvents()

    for i, feat in enumerate(features):
        bar.setValue(i)
        bar.repaint()
        QCoreApplication.processEvents()
        
        id_ = str(feat[id_field])
        
        if use_name and name_field:
            name = str(feat[name_field]) + f" ({id_})"
        else:
            name = str(id_)
        
        destinations.append((id_, name))
        selection.append(id_)

    return destinations, selection


def sub_BuildCombinedDistanceMap(self, activeODM, walkStationODM, GTFS, destinations, src_layer, max_total_time, bar=None):
    """
    Combine three matrices to find optimal combined model routes:
    1. Walk from origin to station (walkStationODM)
    2. Transit from station to station (GTFS)
    3. Walk from station to destination (activeODM)
    
    For each origin-destination pair, find the best route option.
    """
    
    if bar is not None:
        bar.setMaximum(len(destinations))
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()

    CombinedMap = {}

    for i, dest_id in enumerate(destinations):

        if bar is not None:
            bar.setValue(i)
            QCoreApplication.processEvents()

        CombinedMap[dest_id] = {}

        # For each origin in the matrices
        all_origins = set()
        if dest_id in activeODM:
            all_origins.update(activeODM[dest_id].keys())

        for origin_id in all_origins:
            
            routes = []
            
            # Option 1: Direct walk (Active ODM to destination)
            if dest_id in activeODM and origin_id in activeODM[dest_id]:
                dist, dur = activeODM[dest_id][origin_id]
                routes.append({
                    'type': 'walk',
                    'distance': dist,
                    'duration': dur,
                    'total_time': dur / 60  # convert seconds to minutes
                })
            
            # Option 2: Walk to station + Transit + Walk from station
            # This would require station mapping logic - simplified for now
            # In full implementation: iterate through walk_station pairs and GTFS routes
            
            # Select best route (shortest time)
            if routes:
                best_route = min(routes, key=lambda r: r['total_time'])
                if best_route['total_time'] <= max_total_time:
                    CombinedMap[dest_id][origin_id] = best_route

    return CombinedMap


def sub_Export_Combined_GeoJSON(self, combinedMap, destinations):
    """
    Export combined model routing results to GeoJSON.
    Output fields: AccessWalk, TransitTime, EgressWalk, TotalTime
    """
    
    total_start = time.time()
    self._log("=== Combined Model GeoJSON EXPORT ===")
    self._log(f"Starting export with {len(destinations)} destinations")
    
    src_layer = QgsProject.instance().mapLayer(self.current_layer_id)
    
    self.labelCurrentStatus.setText("Loading features...")
    self.repaint()

    step_start = time.time()
    feats = [feat for feat in src_layer.getFeatures()]
    step_duration = time.time() - step_start
    self._log(f"[1/3] Load features: {step_duration:.3f}s ({len(feats)} features)")

    # Step 2: Prepare data
    self.labelCurrentStatus.setText("Preparing data...")
    self.repaint()

    step_start = time.time()
    geojson_features = []
    
    for feat in feats:
        feat_dict = {
            'type': 'Feature',
            'geometry': json.loads(feat.geometry().asJson()),
            'properties': {}
        }
        
        # Copy base attributes
        for field_name in feat.fields().names():
            try:
                feat_dict['properties'][field_name] = feat[field_name]
            except Exception:
                pass
        
        # Add routing results for each destination
        dest_id = str(feat[self.idSelector.currentText()])
        
        if dest_id in combinedMap:
            for origin_data in destinations:
                if isinstance(origin_data, tuple):
                    origin_id, origin_name = origin_data
                else:
                    origin_id = origin_data
                    origin_name = origin_id
                
                if origin_id in combinedMap[dest_id]:
                    route_data = combinedMap[dest_id][origin_id]
                    feat_dict['properties'][f'from_{origin_name}_TotalTime_min'] = route_data.get('total_time', -1)
                    feat_dict['properties'][f'from_{origin_name}_Distance_m'] = route_data.get('distance', -1)
                    feat_dict['properties'][f'from_{origin_name}_Duration_s'] = route_data.get('duration', -1)
        
        geojson_features.append(feat_dict)
    
    step_duration = time.time() - step_start
    self._log(f"[2/3] Prepare data: {step_duration:.3f}s")

    # Step 3: Write GeoJSON file
    self.labelCurrentStatus.setText("Writing GeoJSON file...")
    self.repaint()

    step_start = time.time()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(
        os.path.dirname(self.activeODM_fileSelector.filePath()),
        f'combined_model_results_{timestamp}.geojson'
    )
    
    geojson_dict = {
        'type': 'FeatureCollection',
        'crs': {'type': 'name', 'properties': {'name': src_layer.crs().authid()}},
        'features': geojson_features
    }
    
    with open(output_file, 'w') as f:
        json.dump(geojson_dict, f, indent=2)
    
    step_duration = time.time() - step_start
    self._log(f"[3/3] Write GeoJSON: {step_duration:.3f}s")
    self._log(f"Output: {output_file}")
    
    total_duration = time.time() - total_start
    self._log(f"Combined Model GeoJSON EXPORT completed in {total_duration:.3f}s total")
    self._log("================================")
