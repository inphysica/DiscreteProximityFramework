"""

POICombinedReach

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

from .Analytics.IO import read_ODM, read_GTFS, get_sqlite_info, quick_estimate_from_filesize
from .Analytics.Access import PTODM_ByOrigin, POIREach_wDecay


def _qvariant_to_python(value):
    """Convert QVariant or other QGIS types to native Python types for JSON serialization."""
    if value is None:
        return None
    
    # Handle QVariant objects
    try:
        from qgis.PyQt.QtCore import QVariant
        if isinstance(value, QVariant):
            value = value.toPyObject() if hasattr(value, 'toPyObject') else value.value()
    except Exception:
        pass
    
    # Handle NULLs and check types
    if value is None:
        return None
    
    # Native Python types are already JSON serializable
    if isinstance(value, (str, int, float, bool)):
        return value
    
    # Handle lists and tuples
    if isinstance(value, (list, tuple)):
        return [_qvariant_to_python(v) for v in value]
    
    # Handle dicts
    if isinstance(value, dict):
        return {k: _qvariant_to_python(v) for k, v in value.items()}
    
    # For anything else, convert to string
    return str(value)


UI_PATH = os.path.join(os.path.dirname(__file__), 'poi_combined_reach_dialog_base.ui')
FORM_CLASS, _ = uic.loadUiType(UI_PATH)

# settings key prefix
SETTINGS_KEY = 'DiscreteProximityFramework/POICombinedReach'


class POICombinedReach(QDialog, FORM_CLASS):
    """Dialog for combined model routing combining ActiveODM + GTFS + walking."""

    def __init__(self, parent=None, iface=None):
        super().__init__(parent)
        self.iface = iface
        self.layer_field_map = {}  # layer_id -> {'id_field': str, 'name_field': str}
        self.grid_layer = None
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

        # connect POI layer widget signals
        poi_layer_widget = getattr(self, 'poiLayer', None)
        if poi_layer_widget is not None:
            for sig in ('currentLayerChanged', 'layerChanged', 'sourceLayerChanged', 'currentIndexChanged'):
                if hasattr(poi_layer_widget, sig):
                    try:
                        if sig == 'currentIndexChanged':
                            poi_layer_widget.currentIndexChanged.connect(lambda _idx: self.updatePOILayer(None))
                        else:
                            getattr(poi_layer_widget, sig).connect(self.updatePOILayer)
                    except Exception:
                        continue
                    break
        
        QTimer.singleShot(100, lambda: self.updatePOILayer(None))
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
                # Add Reset button after Cancel button
                try:
                    from qgis.PyQt.QtWidgets import QPushButton
                    reset_button = QPushButton("Reset")
                    reset_button.clicked.connect(self._on_reset)
                    self.buttonBox.addButton(reset_button, self.buttonBox.ActionRole)
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
        settings.setValue(f'{SETTINGS_KEY}/DecayPlatoo', self.decayPlatoo.value())
        settings.setValue(f'{SETTINGS_KEY}/HalfDecayDuration', self.halfDecayDuration.value())
        settings.setValue(f'{SETTINGS_KEY}/IncludeTransit', self.checkBox_IncludeTransit.isChecked())
        settings.setValue(f'{SETTINGS_KEY}/UseDecay', self.checkBox_UseDecay.isChecked())

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

    def _on_reset(self):
        """Reset all numeric values and suffix text box to defaults."""
        try:
            self._log('Reset pressed')
        except Exception:
            pass
        
        try:
            # Reset numeric fields to defaults
            self.maxWalkDest.setValue(30.0)
            self.maxWalkStation.setValue(15.0)
            self.maxTotalTime.setValue(60.0)
            self.walkingSpeed.setValue(4.5)
            self.decayPlatoo.setValue(10.0)
            self.halfDecayDuration.setValue(5.0)
            
            # Reset checkboxes to defaults
            if hasattr(self, 'checkBox_UseDecay'):
                self.checkBox_UseDecay.setChecked(False)
            
            # Reset suffix text box to default
            if hasattr(self, 'exportSuffixInput'):
                self.exportSuffixInput.setText('W15')
            
            self._log('All numeric values, checkboxes, and suffix reset to defaults')
        except Exception as e:
            self._log(f'Error during reset: {str(e)}', level='debug')

    def save_settings(self):
        """Save all settings to QSettings."""
        settings = QSettings()
        try:
            # Save file paths
            settings.setValue(f'{SETTINGS_KEY}/ActiveODM_Path', self.activeODM_fileSelector.filePath())
            settings.setValue(f'{SETTINGS_KEY}/GTFS_Path', self.GTFS_fileSelector.filePath())
            settings.setValue(f'{SETTINGS_KEY}/WalkStation_Path', self.walkStation_fileSelector.filePath())
            
            # Save numeric values
            settings.setValue(f'{SETTINGS_KEY}/MaxWalkDest', self.maxWalkDest.value())
            settings.setValue(f'{SETTINGS_KEY}/MaxWalkStation', self.maxWalkStation.value())
            settings.setValue(f'{SETTINGS_KEY}/MaxTotalTime', self.maxTotalTime.value())
            settings.setValue(f'{SETTINGS_KEY}/WalkingSpeed', self.walkingSpeed.value())
            settings.setValue(f'{SETTINGS_KEY}/DecayPlatoo', self.decayPlatoo.value())
            settings.setValue(f'{SETTINGS_KEY}/HalfDecayDuration', self.halfDecayDuration.value())
            
            # Save checkboxes
            settings.setValue(f'{SETTINGS_KEY}/CheckBox_OnlySelectedFeatures', 
                            self.onlySelectedFeatures.isChecked())
            settings.setValue(f'{SETTINGS_KEY}/CheckBox_IncludeTransit',
                            self.checkBox_IncludeTransit.isChecked())
            settings.setValue(f'{SETTINGS_KEY}/CheckBox_UseDecay',
                            self.checkBox_UseDecay.isChecked())
            settings.setValue(f'{SETTINGS_KEY}/CheckBox_UseGroups',
                            self.checkBox_UseGroups.isChecked())
            settings.setValue(f'{SETTINGS_KEY}/CheckBox_UseWeights',
                            self.checkBox_UseWeights.isChecked())
            
            # Save export suffix
            export_suffix_input = getattr(self, 'exportSuffixInput', None)
            if export_suffix_input is not None:
                settings.setValue(f'{SETTINGS_KEY}/ExportSuffix', export_suffix_input.text())
            
            # Save field selectors
            id_sel = self._get_id_selector()
            id_field = self._get_current_field(id_sel)
            if id_field:
                settings.setValue(f'{SETTINGS_KEY}/IdField', id_field)
            
            # Save POI layer and selectors
            poi_layer = getattr(self, 'poiLayer', None)
            if poi_layer is not None and hasattr(poi_layer, 'currentLayer'):
                try:
                    poi = poi_layer.currentLayer()
                    if poi:
                        settings.setValue(f'{SETTINGS_KEY}/POILayerId', poi.id())
                except Exception:
                    pass
            
            poi_grid_id_sel = getattr(self, 'poiGridIdNameSelector', None)
            poi_group_attr_sel = getattr(self, 'poiGroupAttrSelector', None)
            weight_sel = self._get_weight_selector()
            if poi_grid_id_sel is not None:
                poi_grid_id_field = self._get_current_field(poi_grid_id_sel)
                if poi_grid_id_field:
                    settings.setValue(f'{SETTINGS_KEY}/POIGridIdNameField', poi_grid_id_field)
            if poi_group_attr_sel is not None:
                poi_group_attr_field = self._get_current_field(poi_group_attr_sel)
                if poi_group_attr_field:
                    settings.setValue(f'{SETTINGS_KEY}/POIGroupAttrField', poi_group_attr_field)
            if weight_sel is not None:
                weight_field = self._get_current_field(weight_sel)
                if weight_field:
                    settings.setValue(f'{SETTINGS_KEY}/POIWeightField', weight_field)
            
            self._log("Saved combined model settings")
        except Exception as e:
            self._log(f"Error saving settings: {str(e)}", level='debug')

    def load_settings(self):
        """Load settings from QSettings and apply them."""
        settings = QSettings()
        try:
            # Load checkboxes
            only_selected = settings.value(f'{SETTINGS_KEY}/CheckBox_OnlySelectedFeatures', False, type=bool)
            include_transit = settings.value(f'{SETTINGS_KEY}/CheckBox_IncludeTransit', True, type=bool)
            use_decay = settings.value(f'{SETTINGS_KEY}/CheckBox_UseDecay', False, type=bool)
            use_groups = settings.value(f'{SETTINGS_KEY}/CheckBox_UseGroups', False, type=bool)
            use_weights = settings.value(f'{SETTINGS_KEY}/CheckBox_UseWeights', False, type=bool)
            
            if hasattr(self, 'onlySelectedFeatures'):
                self.onlySelectedFeatures.setChecked(only_selected)
            if hasattr(self, 'checkBox_IncludeTransit'):
                self.checkBox_IncludeTransit.setChecked(include_transit)
            if hasattr(self, 'checkBox_UseDecay'):
                self.checkBox_UseDecay.setChecked(use_decay)
            if hasattr(self, 'checkBox_UseGroups'):
                self.checkBox_UseGroups.setChecked(use_groups)
            if hasattr(self, 'checkBox_UseWeights'):
                self.checkBox_UseWeights.setChecked(use_weights)
            
            # Load export suffix
            export_suffix = settings.value(f'{SETTINGS_KEY}/ExportSuffix', 'W15', type=str)
            if hasattr(self, 'exportSuffixInput'):
                self.exportSuffixInput.setText(export_suffix)
            
            # Load field selectors
            id_field = settings.value(f'{SETTINGS_KEY}/IdField', '', type=str)
            
            id_sel = self._get_id_selector()
            
            if id_field and id_sel is not None:
                self._try_set_selector_by_name(id_sel, id_field)
            
            # Load POI layer
            poi_layer_id = settings.value(f'{SETTINGS_KEY}/POILayerId', '', type=str)
            poi_layer_widget = getattr(self, 'poiLayer', None)
            if poi_layer_id and poi_layer_widget is not None and QgsProject is not None:
                try:
                    poi_layer = QgsProject.instance().mapLayer(poi_layer_id)
                    if poi_layer and hasattr(poi_layer_widget, 'setLayer'):
                        poi_layer_widget.setLayer(poi_layer)
                except Exception:
                    pass
            
            # Load POI attribute selectors
            poi_grid_id_field = settings.value(f'{SETTINGS_KEY}/POIGridIdNameField', '', type=str)
            poi_group_attr_field = settings.value(f'{SETTINGS_KEY}/POIGroupAttrField', '', type=str)
            weight_field = settings.value(f'{SETTINGS_KEY}/POIWeightField', '', type=str)
            
            poi_grid_id_sel = getattr(self, 'poiGridIdNameSelector', None)
            poi_group_attr_sel = getattr(self, 'poiGroupAttrSelector', None)
            weight_sel = self._get_weight_selector()
            
            if poi_grid_id_field and poi_grid_id_sel is not None:
                self._try_set_selector_by_name(poi_grid_id_sel, poi_grid_id_field)
            if poi_group_attr_field and poi_group_attr_sel is not None:
                self._try_set_selector_by_name(poi_group_attr_sel, poi_group_attr_field)
            if weight_field and weight_sel is not None:
                self._try_set_selector_by_name(weight_sel, weight_field)
            
            self._log("Loaded combined model settings")
        except Exception as e:
            self._log(f"Error loading settings: {str(e)}", level='debug')

    def _save_current_selection(self, layer_id=None):
        if layer_id is None:
            layer_id = self.grid_layer
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

    def _get_weight_selector(self):
        """Return weight attribute selector for POI layer."""
        return getattr(self, 'weightAttributeSelector', None)

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
        decay_platoo = settings.value(f'{SETTINGS_KEY}/DecayPlatoo', 10.0, type=float)  # minutes
        half_decay_duration = settings.value(f'{SETTINGS_KEY}/HalfDecayDuration', 5.0, type=float)  # minutes

        self.maxWalkDest.setValue(max_walk_dest)
        self.maxWalkStation.setValue(max_walk_station)
        self.maxTotalTime.setValue(max_total_time)
        self.walkingSpeed.setValue(walking_speed)
        self.decayPlatoo.setValue(decay_platoo)
        self.halfDecayDuration.setValue(half_decay_duration)
        
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
            self.grid_layer = layer.id() if layer is not None and hasattr(layer, 'id') else None
        except Exception:
            self.grid_layer = None

        self._log(f"updateLayer: new={self.grid_layer}")

        restored = False
        if self.grid_layer is not None:
            try:
                restored = self._restore_selection_for_layer(self.grid_layer)
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
                lid = self.grid_layer
                def _id_handler(_idx, lid=lid):
                    self._save_current_selection(lid)
                self._id_selector_conn = _id_handler
                id_sel.currentIndexChanged.connect(self._id_selector_conn)
        except Exception:
            pass
        try:
            if name_sel is not None and hasattr(name_sel, 'currentIndexChanged'):
                lid = self.grid_layer
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
            
            # Use saved field if it exists in this layer, otherwise use first field
            if saved_id_field and saved_id_field in field_names:
                id_field_name = saved_id_field
            elif fields:
                id_field_name = fields[0].name()

        id_sel = self._get_id_selector()
        
        if id_sel is not None and id_field_name:
            try:
                if hasattr(id_sel, 'setCurrentField'):
                    id_sel.setCurrentField(id_field_name)
                else:
                    self._try_set_selector_by_name(id_sel, id_field_name)
            except Exception:
                pass

        try:
            self.grid_layer = layer.id() if layer is not None and hasattr(layer, 'id') else None
        except Exception:
            self.grid_layer = None

        restored = False
        try:
            if self.grid_layer is not None:
                restored = self._restore_selection_for_layer(self.grid_layer)
        except Exception:
            restored = False

        if not restored:
            try:
                self._save_current_selection(self.grid_layer)
            except Exception:
                pass

        # connect handlers
        try:
            if id_sel is not None and hasattr(id_sel, 'currentIndexChanged'):
                lid = self.grid_layer
                def _id_handler(_idx, lid=lid):
                    try:
                        self._save_current_selection(lid)
                    except Exception:
                        pass
                self._id_selector_conn = _id_handler
                id_sel.currentIndexChanged.connect(self._id_selector_conn)
        except Exception:
            pass

    def updatePOILayer(self, layer):
        """Update POI attribute selectors when POI layer changes."""
        if layer is None:
            poi_layer_widget = getattr(self, 'poiLayer', None)
            if poi_layer_widget is not None and hasattr(poi_layer_widget, 'currentLayer'):
                try:
                    layer = poi_layer_widget.currentLayer()
                except Exception:
                    layer = None

        poi_grid_id_sel = getattr(self, 'poiGridIdNameSelector', None)
        poi_group_attr_sel = getattr(self, 'poiGroupAttrSelector', None)
        weight_sel = self._get_weight_selector()

        # Set layer for selectors
        if poi_grid_id_sel is not None and hasattr(poi_grid_id_sel, 'setLayer'):
            try:
                poi_grid_id_sel.setLayer(layer)
            except Exception:
                pass
        if poi_group_attr_sel is not None and hasattr(poi_group_attr_sel, 'setLayer'):
            try:
                poi_group_attr_sel.setLayer(layer)
            except Exception:
                pass
        if weight_sel is not None and hasattr(weight_sel, 'setLayer'):
            try:
                weight_sel.setLayer(layer)
            except Exception:
                pass
        
        self._log(f"updatePOILayer: set to {layer.name() if layer else 'None'}")

        # Try to restore previously saved selections for this layer
        if layer is not None:
            settings = QSettings()
            try:
                poi_grid_id_field = settings.value(f'{SETTINGS_KEY}/POIGridIdNameField', '', type=str)
                poi_group_attr_field = settings.value(f'{SETTINGS_KEY}/POIGroupAttrField', '', type=str)
                weight_field = settings.value(f'{SETTINGS_KEY}/POIWeightField', '', type=str)
                
                if poi_grid_id_field and poi_grid_id_sel is not None:
                    self._try_set_selector_by_name(poi_grid_id_sel, poi_grid_id_field)
                if poi_group_attr_field and poi_group_attr_sel is not None:
                    self._try_set_selector_by_name(poi_group_attr_sel, poi_group_attr_field)
                if weight_field and weight_sel is not None:
                    self._try_set_selector_by_name(weight_sel, weight_field)
                
                self._log(f"Restored POI attributes: grid_id={poi_grid_id_field}, group_attr={poi_group_attr_field}, weight={weight_field}")
            except Exception as e:
                self._log(f"Error restoring POI attributes: {str(e)}", level='debug')

    def Evaluate(self, max_features=100):

        self.labelCurrentStatus.setText("Evaluating dataset...")
        self.repaint()

        src_layer = QgsProject.instance().mapLayer(self.grid_layer)

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
        self._log("\n")
        self._log("="*50)
        self._log("Combined Model Build STARTED")
        self._log("="*50)

        prep_start = time.time()

        self.labelCurrentStatus.setText("Collect origins and destinations..")
        self.repaint()

        origins, destinations, origins_selection = sub_collectODs(self, id_field=self.idSelector.currentText(), bar=self.progressBar)

        print(f"Collected {len(origins)} origins and {len(origins_selection)} are in selection, {len(destinations)} destinations")

        self.labelCurrentStatus.setText("Preparing POI dataset...")
        self.repaint()

        # Collect POIs 

        POIs = sub_Collect_POIs(self, 
                                id_field=self.poiGridIdNameSelector.currentText(),
                                group_attr_field=self.poiGroupAttrSelector.currentText() if self.checkBox_UseGroups.isChecked() else None,
                                weight_field=self._get_current_field(self._get_weight_selector()) if self.checkBox_UseWeights.isChecked() else None,
                                use_groups =self.checkBox_UseGroups.isChecked(),
                                use_weights = self.checkBox_UseWeights.isChecked(),
                                bar=self.progressBar)


        # Load and combine ODMs

        prep_duration = time.time() - prep_start
        self._log(f"Data preparation completed in {prep_duration:.3f}s")

        step_start = time.time()
        load_start = time.time()

        self.progressBar.setMaximum(1)
        self.progressBar.setValue(0)
        self.progressBar.repaint()

        max_walk_dest_meters = self.maxWalkDest.value() * self.walkingSpeed.value() * 1000 / 60

        # Show estimate for Active ODM
        estimate_active = quick_estimate_from_filesize(self.activeODM_fileSelector.filePath())
        self.labelCurrentStatus.setText(f"Reading Active ODM... (est. {estimate_active['estimated_string']})")
        self.repaint()
        step_start = time.time()
        # Convert max walking time (minutes) to distance (meters) using walking speed
        max_walk_dest_meters = self.maxWalkDest.value() * self.walkingSpeed.value() * 1000 / 60
        activeODM = read_ODM(filepath= self.activeODM_fileSelector.filePath(), 
                            remove_prefix = False,
                            origin_prefix_whitelist = [],
                            destination_prefix_whitelist = [],
                            bar=self.progressBar, 
                            selection=origins_selection if self.onlySelectedFeatures.isChecked() else None, 
                            limit=max_walk_dest_meters,
                            only_duration=not self.checkBox_IncludeTransit.isChecked() )
        step_duration = time.time() - step_start
        self._log(f"Read Active ODM in {step_duration:.3f}s")



        # Load Active ODM

        ODM = activeODM

        if self.checkBox_IncludeTransit.isChecked() == True:

            estimate_walkstation = quick_estimate_from_filesize(self.walkStation_fileSelector.filePath())
            self.labelCurrentStatus.setText(f"Reading Walk-to-Station ODM... (est. {estimate_walkstation['estimated_string']})")
            self.repaint()
            step_start = time.time()
            # Convert max walking time (minutes) to distance (meters) using walking speed
            max_walk_station_meters = self.maxWalkStation.value() * self.walkingSpeed.value() * 1000 / 60
            walkStationODM = read_ODM(filepath= self.walkStation_fileSelector.filePath(), 
                                    remove_prefix = False,
                                    origin_prefix_whitelist = [], 
                                    destination_prefix_whitelist = ["PT"],
                                    bar=self.progressBar, 
                                    selection=None, 
                                    limit=max_walk_station_meters)
            step_duration = time.time() - step_start
            self._log(f"Read Walk-to-Station ODM in {step_duration:.3f}s")

            # Show estimate for GTFS Transit
            estimate_gtfs = quick_estimate_from_filesize(self.GTFS_fileSelector.filePath())
            self.labelCurrentStatus.setText(f"Reading GTFS Transit... (est. {estimate_gtfs['estimated_string']})")
            self.repaint()
            step_start = time.time()
            TravelODM = read_GTFS(filepath= self.GTFS_fileSelector.filePath(), 
                            max_duration=int(self.maxTotalTime.value()))
            step_duration = time.time() - step_start
            self._log(f"Read GTFS Transit in {step_duration:.3f}s")
            self._log(f"GTFS Transit ODM contains {len(TravelODM)} entries")


            # PTODM_ByOrigin

            self.labelCurrentStatus.setText("Build combined distance map...")
            self.repaint()

            ODM = PTODM_ByOrigin(
                PTAccess = walkStationODM, 
                PTTravel = TravelODM, 
                WalkingODM = activeODM, 
                OriginSelection = origins_selection, 
                DestinationSelection=destinations, 
                max_total_duration=self.maxTotalTime.value(), 
                max_walking_duration=self.maxWalkStation.value(),
                max_direct_walking_duration=self.maxWalkDest.value(),
                bar=self.progressBar)


        load_duration = time.time() - load_start
        self._log(f"Data loading and preparation completed in {load_duration:.3f}s")


        calculate_start = time.time()

        max_duration = max(self.maxTotalTime.value(),self.maxWalkDest.value() )

        self.labelCurrentStatus.setText("Calculating reachability with decay...")
        self.repaint()

        self._log(f"Max duration for reachability: {max_duration} minutes")
        if self.checkBox_UseDecay.isChecked():
            self._log(f"Decay platoo: {self.decayPlatoo.value()} minutes, Half decay duration: {self.halfDecayDuration.value()} minutes")


        # by default origins_selection should be all origins.

        Reach, groups = POIREach_wDecay(ODM=ODM,
                            POIs=POIs, 
                            origin_selection = origins_selection,
                            Max_Duration = max_duration,
                            Plato=self.decayPlatoo.value(),
                            Half=self.halfDecayDuration.value(),
                            Use_Decay=self.checkBox_UseDecay.isChecked(),
                            Use_Groups = self.checkBox_UseGroups.isChecked(),
                            Suffix = self.exportSuffixInput.text() if hasattr(self, 'exportSuffixInput') else "W15",
                            bar=self.progressBar)

        self.labelCurrentStatus.setText("Exporting results...")
        self.repaint()

        calculate_duration = time.time() - calculate_start
        self._log(f"Calculated reachability in {calculate_duration:.3f}s")

        export_start = time.time()

        sub_Export_GeoJSON(self, Reach, origins_selection, groups)

        export_duration = time.time() - export_start

        self.labelCurrentStatus.setText("Done")
        self.repaint()


        
        build_duration = time.time() - build_start
        self._log(f"Combined Model Build COMPLETED in {build_duration:.3f}s total")
        self._log(f"Data preparation completed in {prep_duration:.3f}s")
        self._log(f"Data loading and preparation completed in {load_duration:.3f}s")
        self._log(f"Calculated reachability in {calculate_duration:.3f}s")
        self._log(f"Exported results in {export_duration:.3f}s")

        self._log("="*50 + "\n")

        return True


def sub_collectODs(self, id_field, bar=None):


    """

    DESCRIPTION:
        Collect origin and destination IDs from input layer.

    ARGUMENTS:
        id_field (str): Name of the field to use as ID for origins and destinations.
        bar (QProgressBar, optional): Progress bar to update during collection.

    RETURNS:
        origins (list): List of origin IDs (strings).
        destinations (list): List of destination IDs (strings).
        origin_selection (list): List of selected origin IDs if "Only Selected Features" is checked, otherwise empty list.


    """


    src_layer = QgsProject.instance().mapLayer(self.grid_layer) 

    all_features = [feat for feat in src_layer.getFeatures()]


    origins = []
    destinations = []
    origin_selection = []

    self.labelCurrentStatus.setText("Collecting destinations and origins ...")
    self.repaint()
    if bar is not None:
        bar.setMaximum(len(all_features))
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()
    for i, feat in enumerate(all_features):
        if bar is not None:
            bar.setValue(i)
            bar.repaint()
            QCoreApplication.processEvents()
        
        id_ = str(feat[id_field])
        destinations.append( id_ )
        origins.append(id_)


    if (self.onlySelectedFeatures.isChecked() == True):

        features = src_layer.selectedFeatures()

        self.labelCurrentStatus.setText("Collecting origin selection...")
        self.repaint()
        if bar is not None:
            bar.setMaximum(len(features))
            bar.setValue(0)
            bar.repaint()
            QCoreApplication.processEvents()

        for i, feat in enumerate(features):

            if bar is not None:
                bar.setValue(i)
                bar.repaint()
                QCoreApplication.processEvents()
            
            id_ = str(feat[id_field])

            origin_selection.append(id_)
    else:
        origin_selection = origins


    return origins, destinations, origin_selection

def sub_Collect_POIs(self, id_field, group_attr_field, weight_field, use_groups, use_weights, bar=None):
    """

    DESCRIPTION:
        Collect POI information from the POI layer.
        Groups POIs by attribute value if use_groups is True, otherwise groups all under "_".
        Each group contains a dictionary of destination IDs mapped to weights.
    
    ARGUMENTS:
        id_field (str): Name of the field to use as ID for POIs.
        group_attr_field (str): Name of the field to use for grouping POIs (optional).
        weight_field (str): Name of the field to use for weighting POIs (optional).
        use_groups (bool): Whether to use grouping for POIs.
        use_weights (bool): Whether to use weighting for POIs.
        bar (QProgressBar, optional): Progress bar to update during collection.

    RETURNS:
        pois (dict): Structure: {group_name: {destination_id: weight, ...}, ...}
                     If use_groups is False, all POIs grouped under "_".
                     If use_weights is False, all weights default to 1.0.

    """
    
    POI_DEFAULT_KEY = "__"


    # Get POI layer
    poi_layer_widget = getattr(self, 'poiLayer', None)
    if poi_layer_widget is None or not hasattr(poi_layer_widget, 'currentLayer'):
        self._log("ERROR: POI layer widget not found", level='debug')
        return {}
    
    try:
        poi_layer = poi_layer_widget.currentLayer()
    except Exception as e:
        self._log(f"ERROR: Failed to get POI layer: {str(e)}", level='debug')
        return {}
    
    if poi_layer is None:
        self._log("ERROR: No POI layer selected", level='debug')
        return {}
    
    # Get all POI features
    poi_features = [feat for feat in poi_layer.getFeatures()]
    
    if len(poi_features) == 0:
        self._log("WARNING: No features found in POI layer")
        return {"_": {}}
    
    self._log(f"Collecting {len(poi_features)} POIs from layer '{poi_layer.name()}'")
    self._log(f"  ID field: {id_field}, Use groups: {use_groups}, Use weights: {use_weights}")
    if use_groups:
        self._log(f"  Group attribute: {group_attr_field}")
    if use_weights:
        self._log(f"  Weight attribute: {weight_field}")
    
    # Initialize progress bar
    if bar is not None:
        bar.setMaximum(len(poi_features))
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()
    
    # Initialize POI dictionary: {group: {destination_id: weight, ...}, ...}
    pois = {}
    
    # Iterate through all POI features
    for i, feat in enumerate(poi_features):
        if bar is not None:
            bar.setValue(i)
            bar.repaint()
            QCoreApplication.processEvents()
        
        try:
            # Get destination ID from id_field
            destination_id = str(feat[id_field])
            
            # Get group attribute
            if use_groups and group_attr_field:
                try:
                    group = str(feat[group_attr_field])
                except Exception:
                    group = POI_DEFAULT_KEY
                    self._log(f"WARNING: Could not read group attribute for feature {i}, using default", level='debug')
            else:
                group = POI_DEFAULT_KEY
            
            # Get weight
            if use_weights and weight_field:
                try:
                    weight = float(feat[weight_field])
                except Exception:
                    weight = 1.0
                    self._log(f"WARNING: Could not read weight for feature {i}, using 1.0", level='debug')
            else:
                weight = 1.0
            
            # Initialize group dictionary if needed
            if group not in pois:
                pois[group] = {}
            
            # Add POI to group with destination ID as key and weight as value
            pois[group][destination_id] = weight
            
        except Exception as e:
            self._log(f"ERROR processing POI feature {i}: {str(e)}", level='debug')
            continue
    
    if bar is not None:
        bar.setValue(len(poi_features))
        bar.repaint()
        QCoreApplication.processEvents()
    
    # Log summary
    total_pois = sum(len(group_pois) for group_pois in pois.values())
    self._log(f"Collected {total_pois} POIs across {len(pois)} group(s)")
    for group in sorted(pois.keys()):
        group_pois = pois[group]
        self._log(f"  Group '{group}': {len(group_pois)} POIs")
    
    return pois

def sub_Export_GeoJSON(self, Reach, origins, groups):
    """
    GeoJSON export using Python's json library - writes directly to GeoJSON file.
    Much faster than QGIS layer updates. No QGIS API overhead.
    Output file is saved next to input file with datetime suffix.
    """
    total_start = time.time()
    self._log("=== GeoJSON EXPORT (JSON Library) ===")
    self._log(f"Starting GeoJSON export with {len(origins)} origins")
    
    src_layer = QgsProject.instance().mapLayer(self.grid_layer)
    crs_authid = src_layer.crs().authid()

    # Step 1: Load features
    self.labelCurrentStatus.setText("Loading features...")
    self.repaint()

    step_start = time.time()
    feats = [feat for feat in src_layer.getFeatures()]
    step_duration = time.time() - step_start
    self._log(f"[1/5] Load features: {step_duration:.3f}s ({len(feats)} features)")

    # Step 2: Build data map
    self.labelCurrentStatus.setText("Building data map...")
    self.repaint()

    bar = self.progressBar
    if bar is not None:
        bar.setMaximum(len(feats))
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()

    step_start = time.time()
    feature_data = {}  # Maps feature_id -> {attr: value}
    id_field_name = self.idSelector.currentText()
    self._log(f"Using ID field: {id_field_name}")
    
    data_lookups = 0
    distance_values_set = 0

    for i, feat in enumerate(feats):
        # if (i + 1) % max(1, len(feats) // 2) == 0:
        bar.setValue(i)
        QCoreApplication.processEvents()

        origin = feat[id_field_name]
        feat_attrs = {}
        
        # Copy all original attributes
        for field in feat.fields():
            feat_attrs[field.name()] = feat[field.name()]

        for group in groups:
            val = -1
            if origin in Reach:
                val = Reach[origin][group]
            feat_attrs[group] = val  # Default to None for all groups

        feature_data[feat.id()] = (feat, feat_attrs)

    step_duration = time.time() - step_start
    self._log(f"[2/5] Build data map: {step_duration:.3f}s ({len(feature_data)} features, {data_lookups} lookups)")

    # Step 3: Generate output path
    step_start = time.time()
    src_file = src_layer.dataProvider().dataSourceUri()
    
    if src_file:
        if '|' in src_file:
            src_file = src_file.split('|')[0]
        base_dir = os.path.dirname(src_file)
        base_name = os.path.splitext(os.path.basename(src_file))[0]
    else:
        base_dir = os.path.expanduser('~')
        base_name = "results"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_filename = f"{base_name}_results_{timestamp}.geojson"
    output_path = os.path.join(base_dir, output_filename)
    
    self._log(f"Output file: {output_path}")
    step_duration = time.time() - step_start
    self._log(f"[3/5] Generate path: {step_duration:.3f}s")

    # Step 4: Write GeoJSON directly using json library
    self.labelCurrentStatus.setText("Writing GeoJSON file...")
    self.repaint()

    step_start = time.time()
    
    try:
        geojson_features = []
        
        if bar is not None:
            bar.setMaximum(len(feature_data))
            bar.setValue(0)
            bar.repaint()
            QCoreApplication.processEvents()

        for i, (feat_id, (orig_feat, feat_attrs)) in enumerate(feature_data.items()):
            if (i + 1) % max(1, len(feature_data) // 10) == 0:
                bar.setValue(i)
                QCoreApplication.processEvents()

            # Get geometry as GeoJSON
            geom = orig_feat.geometry()
            if geom is None or geom.isEmpty():
                geometry = None
            else:
                geometry = json.loads(geom.asJson())

            # Create GeoJSON feature
            geojson_feat = {
                "type": "Feature",
                "geometry": geometry,
                "properties": feat_attrs
            }
            geojson_features.append(geojson_feat)

        # Create FeatureCollection
        geojson_data = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {
                    "name": crs_authid
                }
            },
            "features": geojson_features
        }

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(geojson_data, f, indent=2, default=str)

        step_duration = time.time() - step_start
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        self._log(f"[4/5] Write file: {step_duration:.3f}s ({file_size:.2f} MB, {len(geojson_features)} features)")
        
    except Exception as e:
        self._log(f"ERROR writing GeoJSON: {str(e)}")
        return False

    # Step 5: Load into QGIS
    self.labelCurrentStatus.setText("Loading results layer...")
    self.repaint()

    step_start = time.time()
    
    try:
        result_layer = QgsVectorLayer(output_path, os.path.basename(output_path), "ogr")
        if not result_layer.isValid():
            self._log("ERROR: Failed to load output GeoJSON layer")
            return False
        
        QgsProject.instance().addMapLayer(result_layer)
        step_duration = time.time() - step_start
        self._log(f"[5/5] Load layer: {step_duration:.3f}s")
        
    except Exception as e:
        self._log(f"ERROR loading layer: {str(e)}")
        return False

    total_duration = time.time() - total_start
    self._log(f"=== TOTAL TIME: {total_duration:.3f}s ===")
    self._log(f"Summary: {len(feats)} features × {len(origins)} origins")
    self._log(f"Output: {output_path}")
    self._log("=== END GeoJSON EXPORT ===")
    
    return True
