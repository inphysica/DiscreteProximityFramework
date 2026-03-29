"""

CombinedReachAnalysisDialog

Combined Reach Analysis using POI with attribute decay functions.
Analyzes accessibility from grid origins to POI features with customizable attribute weighting.

Dialog stores per-layer field selections in memory and logs diagnostic messages to QGIS log.

"""

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (QDialog, QTableWidgetItem, QCheckBox, QMessageBox, 
                                  QHeaderView, QAbstractItemView)
from qgis.PyQt.QtCore import QTimer, QSettings, Qt
from qgis.core import QgsProject, QgsField
from qgis.PyQt.QtCore import QCoreApplication

import os
import time
import json
from datetime import datetime

try:
    from qgis.core import QgsMessageLog, Qgis
except Exception:
    QgsMessageLog = None
    Qgis = None

UI_PATH = os.path.join(os.path.dirname(__file__), 'combinedreach_analysis_dialog_base.ui')

try:
    FORM_CLASS, _ = uic.loadUiType(UI_PATH)
except Exception as e:
    class FORM_CLASS:
        def setupUi(self, MainWindow):
            pass
    print(f"Warning: Could not load UI file {UI_PATH}: {e}")

# settings key prefix
SETTINGS_KEY = 'DiscreteProximityFramework/CombinedReachAnalysis'


class CombinedReachAnalysisDialog(QDialog, FORM_CLASS):
    """Dialog for combined reach analysis with POI layer and attribute selection."""

    def __init__(self, parent=None, iface=None):
        super().__init__(parent)
        self.iface = iface
        self.current_grid_layer_id = None
        self.current_poi_layer_id = None
        self.poi_attributes_selection = {}  # poi_layer_id -> list of selected attribute names

        self.layer_field_map = {}  # layer_id -> {'id_field': str, 'name_field': str}


        
        try:
            self.setupUi(self)
        except Exception as e:
            self._log(f"Warning: Could not setup UI from file: {e}", level='debug')
            self._create_ui_manually()

        self._log(f"QSettings organization: {QSettings().organizationName()}, app: {QSettings().applicationName()}", level='debug')

        # seed known layers (non-persistent)
        if QgsProject is not None:
            try:
                for lay in QgsProject.instance().mapLayers().values():
                    try:
                        self.poi_attributes_selection.setdefault(lay.id(), [])
                    except Exception:
                        continue
            except Exception:
                pass

        self.prep_Defaults()

        # Connect grid layer selector
        if hasattr(self, 'inputLayer'):
            for sig in ('currentLayerChanged', 'layerChanged', 'sourceLayerChanged'):
                if hasattr(self.inputLayer, sig):
                    try:
                        getattr(self.inputLayer, sig).connect(self.on_grid_layer_changed)
                    except Exception:
                        continue
                    break



        # Connect POI layer selector
        if hasattr(self, 'poiLayer'):
            for sig in ('currentLayerChanged', 'layerChanged', 'sourceLayerChanged'):
                if hasattr(self.poiLayer, sig):
                    try:
                        getattr(self.poiLayer, sig).connect(self._on_poi_layer_changed_handler)
                    except Exception:
                        continue
                    break

        # Connect dialog buttons
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

        # Connect Select All / Deselect All buttons
        try:
            if hasattr(self, 'selectAllButton'):
                self.selectAllButton.clicked.connect(self.select_all_attributes)
            if hasattr(self, 'deselectAllButton'):
                self.deselectAllButton.clicked.connect(self.deselect_all_attributes)
        except Exception:
            pass

        QTimer.singleShot(0, lambda: self.on_grid_layer_changed(None))
        QTimer.singleShot(0, lambda: self.on_poi_layer_changed(None))

    def on_grid_layer_changed(self, layer):
        """Handle grid layer selection change."""
        if layer is None and hasattr(self, 'inputLayer'):
            try:
                layer = self.inputLayer.currentLayer()
            except Exception:
                layer = None

        try:
            self.current_grid_layer_id = layer.id() if layer is not None and hasattr(layer, 'id') else None
        except Exception:
            self.current_grid_layer_id = None

        # Update field selector to show fields from the selected layer
        if hasattr(self, 'idSelector'):
            try:
                self.idSelector.setLayer(layer)
            except Exception:
                pass

        self._log(f"Grid layer changed: {self.current_grid_layer_id}")

    def _on_poi_layer_changed_handler(self, layer):
        """Handle POI layer selection change - saves previous layer's attributes first."""
        # Save previous POI layer's attribute selections BEFORE switching
        if self.current_poi_layer_id is not None:
            self._save_poi_attributes()
        # Now switch layers
        self.on_poi_layer_changed(layer)

    def on_poi_layer_changed(self, layer):
        """Handle POI layer selection change."""
        if layer is None and hasattr(self, 'poiLayer'):
            try:
                layer = self.poiLayer.currentLayer()
            except Exception:
                layer = None

        # Save previous POI layer's attribute selections
        if self.current_poi_layer_id is not None:
            self._save_poi_attributes()

        try:
            self.current_poi_layer_id = layer.id() if layer is not None and hasattr(layer, 'id') else None
        except Exception:
            self.current_poi_layer_id = None

        # Update POI Grid ID field selector to show fields from the selected layer
        if hasattr(self, 'poiGridIdSelector'):
            try:
                self.poiGridIdSelector.setLayer(layer)
            except Exception:
                pass

        self._log(f"POI layer changed: {self.current_poi_layer_id}")

        # Populate attribute table for new POI layer
        self._populate_attributes_table(layer)

    def _populate_attributes_table(self, layer):
        """Populate the attribute table with checkboxes, names, and types."""
        if not hasattr(self, 'attributeTable'):
            return

        # Block signals while populating to avoid triggering saves during setup
        self.attributeTable.blockSignals(True)
        self.attributeTable.setRowCount(0)

        if layer is None:
            self.attributeTable.blockSignals(False)
            return

        try:
            fields = list(layer.fields())
        except Exception:
            fields = []
            self.attributeTable.blockSignals(False)
            return

        if not fields:
            self.attributeTable.blockSignals(False)
            return

        # Get previously selected attributes for this layer
        previously_selected = self.poi_attributes_selection.get(self.current_poi_layer_id, [])
        self._log(f"Restoring {len(previously_selected)} saved attributes for POI layer {self.current_poi_layer_id}: {previously_selected}", level='debug')

        for i, field in enumerate(fields):
            field_name = field.name()
            field_type = field.typeName()

            self.attributeTable.insertRow(i)

            # Checkbox column
            checkbox = QCheckBox()
            if field_name in previously_selected:
                checkbox.setChecked(True)
                self._log(f"Checked attribute: {field_name}", level='debug')
            self.attributeTable.setCellWidget(i, 0, checkbox)

            # Attribute name column
            name_item = QTableWidgetItem(field_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.attributeTable.setItem(i, 1, name_item)

            # Type column
            type_item = QTableWidgetItem(field_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.attributeTable.setItem(i, 2, type_item)

        # Resize columns
        self.attributeTable.resizeColumnsToContents()
        self.attributeTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.attributeTable.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.attributeTable.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        # Unblock signals after table is fully set up
        self.attributeTable.blockSignals(False)
        
        # Connect checkbox signals to auto-save future changes
        self._connect_attribute_table_signals()

        self._log(f"Populated {len(fields)} attributes for POI layer {self.current_poi_layer_id}")

    def _connect_attribute_table_signals(self):
        """Connect attribute table checkboxes to auto-save on change."""
        if not hasattr(self, 'attributeTable'):
            return
        
        # Capture current layer ID to ensure saves go to correct layer
        current_layer_id = self.current_poi_layer_id
        if not current_layer_id:
            return
        
        # Connect each checkbox to save selection on change
        for row in range(self.attributeTable.rowCount()):
            checkbox = self.attributeTable.cellWidget(row, 0)
            if checkbox and isinstance(checkbox, QCheckBox):
                try:
                    # Create closure to capture layer ID and dialog reference
                    def make_handler(layer_id, dialog):
                        def _on_checkbox_changed(state):
                            # Only save if we're still on the same layer
                            if layer_id == dialog.current_poi_layer_id:
                                dialog._save_poi_attributes()
                        return _on_checkbox_changed
                    
                    handler = make_handler(current_layer_id, self)
                    checkbox.stateChanged.connect(handler)
                    self._log(f"Connected checkbox signal for row {row}", level='debug')
                except Exception as e:
                    self._log(f"Warning: Could not connect checkbox signal for row {row}: {e}", level='debug')

    def _save_poi_attributes(self):
        """Save currently selected POI attributes to memory dictionary."""
        if not hasattr(self, 'attributeTable') or self.current_poi_layer_id is None:
            return

        selected_attributes = []
        for row in range(self.attributeTable.rowCount()):
            checkbox = self.attributeTable.cellWidget(row, 0)
            if checkbox and isinstance(checkbox, QCheckBox) and checkbox.isChecked():
                attr_name = self.attributeTable.item(row, 1).text()
                selected_attributes.append(attr_name)

        self.poi_attributes_selection[self.current_poi_layer_id] = selected_attributes
        self._log(f"Saved {len(selected_attributes)} attributes for POI layer {self.current_poi_layer_id}: {selected_attributes}", level='debug')

    def select_all_attributes(self):
        """Select all attributes in the table."""
        if not hasattr(self, 'attributeTable'):
            return
        for row in range(self.attributeTable.rowCount()):
            checkbox = self.attributeTable.cellWidget(row, 0)
            if checkbox and isinstance(checkbox, QCheckBox):
                checkbox.setChecked(True)
        self._log("Selected all attributes")

    def deselect_all_attributes(self):
        """Deselect all attributes in the table."""
        if not hasattr(self, 'attributeTable'):
            return
        for row in range(self.attributeTable.rowCount()):
            checkbox = self.attributeTable.cellWidget(row, 0)
            if checkbox and isinstance(checkbox, QCheckBox):
                checkbox.setChecked(False)
        self._log("Deselected all attributes")

    def get_selected_poi_attributes(self):
        """
        Get list of currently selected POI attributes.

        Returns:
            list: Attribute names that are checked
        """
        if not hasattr(self, 'attributeTable'):
            return []

        selected = []
        for row in range(self.attributeTable.rowCount()):
            checkbox = self.attributeTable.cellWidget(row, 0)
            if checkbox and isinstance(checkbox, QCheckBox) and checkbox.isChecked():
                attr_name = self.attributeTable.item(row, 1).text()
                selected.append(attr_name)

        return selected

    def get_grid_layer(self):
        """Get currently selected grid layer."""
        if hasattr(self, 'inputLayer'):
            try:
                return self.inputLayer.currentLayer()
            except Exception:
                return None
        return None

    def get_poi_layer(self):
        """Get currently selected POI layer."""
        if hasattr(self, 'poiLayer'):
            try:
                return self.poiLayer.currentLayer()
            except Exception:
                return None
        return None

    def get_id_field(self):
        """Get currently selected ID field."""
        if hasattr(self, 'idSelector'):
            try:
                return self.idSelector.currentField()
            except Exception:
                return None
        return None

    def get_poi_grid_id_field(self):
        """Get currently selected POI Grid ID field."""
        if hasattr(self, 'poiGridIdSelector'):
            try:
                return self.poiGridIdSelector.currentField()
            except Exception:
                return None
        return None

    def get_decay_plato(self):
        """Get decay plato value (minutes)."""
        if hasattr(self, 'decayPlato'):
            try:
                return self.decayPlato.value()
            except Exception:
                return 15.0
        return 15.0

    def get_decay_half_distance(self):
        """Get decay half distance value (minutes)."""
        if hasattr(self, 'decayHalfDistance'):
            try:
                return self.decayHalfDistance.value()
            except Exception:
                return 30.0
        return 30.0

    def get_use_transit(self):
        """Get use transit checkbox state."""
        if hasattr(self, 'useTransit'):
            try:
                return self.useTransit.isChecked()
            except Exception:
                return True
        return True

    def get_max_walk_dest(self):
        """Get max walking to destination value (minutes)."""
        if hasattr(self, 'maxWalkDest'):
            try:
                return self.maxWalkDest.value()
            except Exception:
                return 30.0
        return 30.0

    def get_max_walk_station(self):
        """Get max walk to station value (minutes)."""
        if hasattr(self, 'maxWalkStation'):
            try:
                return self.maxWalkStation.value()
            except Exception:
                return 15.0
        return 15.0

    def get_walking_speed(self):
        """Get walking speed value (km/h)."""
        if hasattr(self, 'walkingSpeed'):
            try:
                return self.walkingSpeed.value()
            except Exception:
                return 4.5
        return 4.5

    def get_max_duration(self):
        """Get max duration value (minutes)."""
        if hasattr(self, 'maxDuration'):
            try:
                return self.maxDuration.value()
            except Exception:
                return 60.0
        return 60.0

    def get_active_odm_file(self):
        """Get selected Active ODM file path."""
        if hasattr(self, 'activeODMFileSelector'):
            try:
                return self.activeODMFileSelector.filePath()
            except Exception:
                return ""
        return ""

    def get_gtfs_odm_file(self):
        """Get selected GTFS ODM file path."""
        if hasattr(self, 'gtfsODMFileSelector'):
            try:
                return self.gtfsODMFileSelector.filePath()
            except Exception:
                return ""
        return ""

    def get_station_odm_file(self):
        """Get selected Station ODM file path."""
        if hasattr(self, 'stationODMFileSelector'):
            try:
                return self.stationODMFileSelector.filePath()
            except Exception:
                return ""
        return ""

    def prep_Defaults(self):
        """Prepare default settings."""
        settings = QSettings()

        self._log(f"Loading settings from key: {SETTINGS_KEY}", level='debug')

        # Restore layer selections
        grid_layer_id = settings.value(f'{SETTINGS_KEY}/GridLayerId', '', type=str)
        poi_layer_id = settings.value(f'{SETTINGS_KEY}/POILayerId', '', type=str)

        self._log(f"Loaded layer IDs: GridLayerId='{grid_layer_id}', POILayerId='{poi_layer_id}'", level='debug')

        if hasattr(self, 'inputLayer') and grid_layer_id:
            try:
                grid_layer = QgsProject.instance().mapLayer(grid_layer_id)
                if grid_layer:
                    self.inputLayer.setLayer(grid_layer)
                    self.current_grid_layer_id = grid_layer.id()
                    self._log(f"Restored grid layer: {grid_layer.name()}", level='debug')
            except Exception as e:
                self._log(f"Warning: Could not restore grid layer: {e}", level='debug')

        if hasattr(self, 'poiLayer') and poi_layer_id:
            try:
                poi_layer = QgsProject.instance().mapLayer(poi_layer_id)
                if poi_layer:
                    self.poiLayer.setLayer(poi_layer)
                    self.current_poi_layer_id = poi_layer.id()
                    self._log(f"Restored POI layer: {poi_layer.name()}", level='debug')
                    # Populate table immediately since signal connections may not be ready yet
                    self._populate_attributes_table(poi_layer)
            except Exception as e:
                self._log(f"Warning: Could not restore POI layer: {e}", level='debug')

        # Restore file paths
        active_odm_path = settings.value(f'{SETTINGS_KEY}/ActiveODMPath', '', type=str)
        gtfs_odm_path = settings.value(f'{SETTINGS_KEY}/GTFSODMPath', '', type=str)
        station_odm_path = settings.value(f'{SETTINGS_KEY}/StationODMPath', '', type=str)

        self._log(f"Loaded file paths: ActiveODM='{active_odm_path}', GTFSODM='{gtfs_odm_path}', StationODM='{station_odm_path}'", level='debug')

        if hasattr(self, 'activeODMFileSelector'):
            self.activeODMFileSelector.setFilePath(active_odm_path)
        else:
            self._log("Warning: activeODMFileSelector widget not found", level='debug')
        if hasattr(self, 'gtfsODMFileSelector'):
            self.gtfsODMFileSelector.setFilePath(gtfs_odm_path)
        else:
            self._log("Warning: gtfsODMFileSelector widget not found", level='debug')
        if hasattr(self, 'stationODMFileSelector'):
            self.stationODMFileSelector.setFilePath(station_odm_path)
        else:
            self._log("Warning: stationODMFileSelector widget not found", level='debug')

        # Restore numeric values
        decay_plato = settings.value(f'{SETTINGS_KEY}/DecayPlato', 15.0, type=float)
        decay_half_distance = settings.value(f'{SETTINGS_KEY}/DecayHalfDistance', 30.0, type=float)
        use_transit = settings.value(f'{SETTINGS_KEY}/UseTransit', True, type=bool)
        max_walk_dest = settings.value(f'{SETTINGS_KEY}/MaxWalkDest', 30.0, type=float)
        max_walk_station = settings.value(f'{SETTINGS_KEY}/MaxWalkStation', 15.0, type=float)
        walking_speed = settings.value(f'{SETTINGS_KEY}/WalkingSpeed', 4.5, type=float)
        max_duration = settings.value(f'{SETTINGS_KEY}/MaxDuration', 60.0, type=float)

        self._log(f"Loaded numeric values: DecayPlato={decay_plato}, DecayHalfDist={decay_half_distance}, UseTransit={use_transit}, MaxWalkDest={max_walk_dest}, MaxWalkStation={max_walk_station}, WalkingSpeed={walking_speed}, MaxDuration={max_duration}", level='debug')

        if hasattr(self, 'decayPlato'):
            self.decayPlato.setValue(decay_plato)
        if hasattr(self, 'decayHalfDistance'):
            self.decayHalfDistance.setValue(decay_half_distance)
        if hasattr(self, 'useTransit'):
            self.useTransit.setChecked(use_transit)
        if hasattr(self, 'maxWalkDest'):
            self.maxWalkDest.setValue(max_walk_dest)
        if hasattr(self, 'maxWalkStation'):
            self.maxWalkStation.setValue(max_walk_station)
        if hasattr(self, 'walkingSpeed'):
            self.walkingSpeed.setValue(walking_speed)
        if hasattr(self, 'maxDuration'):
            self.maxDuration.setValue(max_duration)

        # Restore POI attribute selections
        poi_attributes_json = settings.value(f'{SETTINGS_KEY}/POIAttributeSelections', '{}', type=str)
        try:
            self.poi_attributes_selection = json.loads(poi_attributes_json) if poi_attributes_json and poi_attributes_json != '{}' else {}
            self._log(f"Loaded POI attribute selections: {self.poi_attributes_selection}", level='debug')
        except Exception as e:
            self._log(f"Warning: Could not load POI attribute selections: {e}", level='debug')
            self.poi_attributes_selection = {}

        # Log all current settings for debugging
        all_settings = self._get_all_settings()
        self._log(f"All stored settings: {all_settings}", level='debug')
        self._log("Loaded default settings")

    def _log(self, message, level='info'):
        """Log message to QGIS log."""
        if QgsMessageLog is None:
            return
        try:
            lvl = Qgis.Info if level == 'info' else Qgis.Debug
            QgsMessageLog.logMessage(message, 'DiscreteProximityFramework', lvl)
        except Exception:
            pass

    def _get_all_settings(self):
        """Debug helper: Get all settings stored under our prefix."""
        settings = QSettings()
        settings.beginGroup(SETTINGS_KEY)
        keys = settings.allKeys()
        settings.endGroup()
        
        result = {}
        for key in keys:
            value = settings.value(f'{SETTINGS_KEY}/{key}')
            result[key] = value
        
        return result

    def _create_ui_manually(self):
        """Create UI elements manually if UI file fails to load."""
        try:
            from qgis.PyQt.QtWidgets import (QVBoxLayout, QGroupBox, QLabel, QTableWidget,
                                            QTableWidgetItem, QCheckBox, QDoubleSpinBox, 
                                            QProgressBar, QDialogButtonBox, QGridLayout, 
                                            QHBoxLayout, QPushButton)
            from qgis.gui import QgsMapLayerComboBox, QgsDoubleSpinBox, QgsFieldComboBox, QgsFileWidget

            self.setWindowTitle("Combined Reach Analysis")
            self.setGeometry(0, 0, 800, 1100)

            main_layout = QVBoxLayout(self)

            # Grid layer
            main_layout.addWidget(QLabel("Grid Input Layer"))
            self.inputLayer = QgsMapLayerComboBox()
            main_layout.addWidget(self.inputLayer)

            # Selected features only
            self.onlySelectedFeatures = QCheckBox("Selected features only")
            self.onlySelectedFeatures.setChecked(True)
            main_layout.addWidget(self.onlySelectedFeatures)

            # ID Field selector (on same line)
            id_field_layout = QHBoxLayout()
            id_field_layout.addWidget(QLabel("ID Field"))
            self.idSelector = QgsFieldComboBox()
            id_field_layout.addWidget(self.idSelector)
            main_layout.addLayout(id_field_layout)

            # POI layer
            main_layout.addWidget(QLabel("Point of Interest Layer"))
            self.poiLayer = QgsMapLayerComboBox()
            main_layout.addWidget(self.poiLayer)

            # POI Grid ID Field selector (on same line)
            poi_grid_id_layout = QHBoxLayout()
            poi_grid_id_layout.addWidget(QLabel("Grid ID Field"))
            self.poiGridIdSelector = QgsFieldComboBox()
            poi_grid_id_layout.addWidget(self.poiGridIdSelector)
            main_layout.addLayout(poi_grid_id_layout)

            # ODM Datasets section
            main_layout.addWidget(QLabel("ODM Datasets"))
            
            # Active ODM (on same line)
            active_odm_layout = QHBoxLayout()
            active_odm_layout.addWidget(QLabel("Active ODM (Origin-to-Destination)"))
            self.activeODMFileSelector = QgsFileWidget()
            self.activeODMFileSelector.setFilter("SQLite files (*.sqlite *.db *.gpkg);;All files (*)")
            active_odm_layout.addWidget(self.activeODMFileSelector)
            main_layout.addLayout(active_odm_layout)
            
            # GTFS ODM (on same line)
            gtfs_odm_layout = QHBoxLayout()
            gtfs_odm_layout.addWidget(QLabel("GTFS ODM (Station-to-Station)"))
            self.gtfsODMFileSelector = QgsFileWidget()
            self.gtfsODMFileSelector.setFilter("SQLite files (*.sqlite *.db *.gpkg);;All files (*)")
            gtfs_odm_layout.addWidget(self.gtfsODMFileSelector)
            main_layout.addLayout(gtfs_odm_layout)
            
            # Station ODM (on same line)
            station_odm_layout = QHBoxLayout()
            station_odm_layout.addWidget(QLabel("Station ODM (Origin|Destination-to-Station)"))
            self.stationODMFileSelector = QgsFileWidget()
            self.stationODMFileSelector.setFilter("SQLite files (*.sqlite *.db *.gpkg);;All files (*)")
            station_odm_layout.addWidget(self.stationODMFileSelector)
            main_layout.addLayout(station_odm_layout)

            # Attributes
            main_layout.addWidget(QLabel("Select Attributes for Calculation"))
            
            # Select All / Deselect All buttons
            button_layout = QHBoxLayout()
            select_all_btn = QPushButton("Select All")
            deselect_all_btn = QPushButton("Deselect All")
            select_all_btn.clicked.connect(self.select_all_attributes)
            deselect_all_btn.clicked.connect(self.deselect_all_attributes)
            button_layout.addWidget(select_all_btn)
            button_layout.addWidget(deselect_all_btn)
            button_layout.addStretch()
            main_layout.addLayout(button_layout)
            
            self.attributeTable = QTableWidget()
            self.attributeTable.setColumnCount(3)
            self.attributeTable.setHorizontalHeaderLabels(["Select", "Attribute Name", "Type"])
            main_layout.addWidget(self.attributeTable)

            # Constraints group
            constraints_group = QGroupBox("Constraints")
            constraints_layout = QGridLayout()

            constraints_layout.addWidget(QLabel("Max walking to destination (min)"), 0, 0)
            self.maxWalkDest = QgsDoubleSpinBox()
            self.maxWalkDest.setValue(30.0)
            constraints_layout.addWidget(self.maxWalkDest, 0, 1)

            constraints_layout.addWidget(QLabel("Max walk to station (min)"), 1, 0)
            self.maxWalkStation = QgsDoubleSpinBox()
            self.maxWalkStation.setValue(15.0)
            constraints_layout.addWidget(self.maxWalkStation, 1, 1)

            constraints_layout.addWidget(QLabel("Walking speed (km/h)"), 2, 0)
            self.walkingSpeed = QgsDoubleSpinBox()
            self.walkingSpeed.setValue(4.5)
            constraints_layout.addWidget(self.walkingSpeed, 2, 1)

            constraints_layout.addWidget(QLabel("Max duration (min)"), 3, 0)
            self.maxDuration = QgsDoubleSpinBox()
            self.maxDuration.setValue(60.0)
            constraints_layout.addWidget(self.maxDuration, 3, 1)

            constraints_layout.addWidget(QLabel("Decay Plato (minutes)"), 4, 0)
            self.decayPlato = QgsDoubleSpinBox()
            self.decayPlato.setValue(15.0)
            constraints_layout.addWidget(self.decayPlato, 4, 1)

            constraints_layout.addWidget(QLabel("Decay Half Distance (minutes)"), 5, 0)
            self.decayHalfDistance = QgsDoubleSpinBox()
            self.decayHalfDistance.setValue(30.0)
            constraints_layout.addWidget(self.decayHalfDistance, 5, 1)

            self.useTransit = QCheckBox("Use Transit")
            self.useTransit.setChecked(True)
            constraints_layout.addWidget(self.useTransit, 6, 0)

            constraints_group.setLayout(constraints_layout)
            main_layout.addWidget(constraints_group)

            # Status and progress
            self.labelCurrentStatus = QLabel("Ready")
            main_layout.addWidget(self.labelCurrentStatus)

            self.progressBar = QProgressBar()
            main_layout.addWidget(self.progressBar)

            # Button box
            self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            main_layout.addWidget(self.buttonBox)

            self.setLayout(main_layout)
            self._log("UI created manually")
        except Exception as e:
            self._log(f"Error creating manual UI: {e}", level='debug')

    def _on_ok(self):
        """Internal OK handler."""
        self._save_poi_attributes()

        settings = QSettings()
        
        # Save POI attribute selections as JSON
        try:
            poi_attributes_json = json.dumps(self.poi_attributes_selection)
            settings.setValue(f'{SETTINGS_KEY}/POIAttributeSelections', poi_attributes_json)
            self._log(f"Saving POI attribute selections: {poi_attributes_json}", level='debug')
        except Exception as e:
            self._log(f"Warning: Could not save POI attribute selections: {e}", level='debug')
        
        # Save layer selections
        grid_layer_id = ''
        poi_layer_id = ''
        
        if hasattr(self, 'inputLayer'):
            try:
                grid_layer = self.inputLayer.currentLayer()
                if grid_layer:
                    grid_layer_id = grid_layer.id()
                    self._log(f"Saving grid layer: {grid_layer.name()} (ID: {grid_layer_id})", level='debug')
            except Exception as e:
                self._log(f"Warning: Could not get grid layer: {e}", level='debug')
        
        if hasattr(self, 'poiLayer'):
            try:
                poi_layer = self.poiLayer.currentLayer()
                if poi_layer:
                    poi_layer_id = poi_layer.id()
                    self._log(f"Saving POI layer: {poi_layer.name()} (ID: {poi_layer_id})", level='debug')
            except Exception as e:
                self._log(f"Warning: Could not get POI layer: {e}", level='debug')
        
        settings.setValue(f'{SETTINGS_KEY}/GridLayerId', grid_layer_id)
        settings.setValue(f'{SETTINGS_KEY}/POILayerId', poi_layer_id)
        
        # Save file paths
        active_odm = self.activeODMFileSelector.filePath() if hasattr(self, 'activeODMFileSelector') else ''
        gtfs_odm = self.gtfsODMFileSelector.filePath() if hasattr(self, 'gtfsODMFileSelector') else ''
        station_odm = self.stationODMFileSelector.filePath() if hasattr(self, 'stationODMFileSelector') else ''
        
        settings.setValue(f'{SETTINGS_KEY}/ActiveODMPath', active_odm)
        settings.setValue(f'{SETTINGS_KEY}/GTFSODMPath', gtfs_odm)
        settings.setValue(f'{SETTINGS_KEY}/StationODMPath', station_odm)
        
        self._log(f"Saving file paths: ActiveODM='{active_odm}', GTFSODM='{gtfs_odm}', StationODM='{station_odm}'", level='debug')
        
        # Save numeric values
        decay_plato = self.decayPlato.value() if hasattr(self, 'decayPlato') else 15.0
        decay_half_distance = self.decayHalfDistance.value() if hasattr(self, 'decayHalfDistance') else 30.0
        use_transit = self.useTransit.isChecked() if hasattr(self, 'useTransit') else True
        max_walk_dest = self.maxWalkDest.value() if hasattr(self, 'maxWalkDest') else 30.0
        max_walk_station = self.maxWalkStation.value() if hasattr(self, 'maxWalkStation') else 15.0
        walking_speed = self.walkingSpeed.value() if hasattr(self, 'walkingSpeed') else 4.5
        max_duration = self.maxDuration.value() if hasattr(self, 'maxDuration') else 60.0
        
        settings.setValue(f'{SETTINGS_KEY}/DecayPlato', decay_plato)
        settings.setValue(f'{SETTINGS_KEY}/DecayHalfDistance', decay_half_distance)
        settings.setValue(f'{SETTINGS_KEY}/UseTransit', use_transit)
        settings.setValue(f'{SETTINGS_KEY}/MaxWalkDest', max_walk_dest)
        settings.setValue(f'{SETTINGS_KEY}/MaxWalkStation', max_walk_station)
        settings.setValue(f'{SETTINGS_KEY}/WalkingSpeed', walking_speed)
        settings.setValue(f'{SETTINGS_KEY}/MaxDuration', max_duration)

        self._log(f"Saving numeric values: DecayPlato={decay_plato}, DecayHalfDist={decay_half_distance}, UseTransit={use_transit}, MaxWalkDest={max_walk_dest}, MaxWalkStation={max_walk_station}, WalkingSpeed={walking_speed}, MaxDuration={max_duration}", level='debug')
        
        # Ensure settings are written to disk
        settings.sync()
        self._log("OK pressed - settings saved and synced to disk")

        try:
            res = self.on_ok()
            if res is False:
                return
        except Exception:
            pass

        try:
            self.accept()
        except Exception:
            try:
                self.done(1)
            except Exception:
                pass

    def _on_cancel(self):
        """Internal Cancel handler."""
        self._log("Cancel pressed")

        try:
            res = self.on_cancel()
            if res is False:
                return
        except Exception:
            pass

        try:
            self.reject()
        except Exception:
            try:
                self.done(0)
            except Exception:
                pass

    def on_ok(self):
        """
        Override this method for custom OK behavior.
        Return False to prevent dialog from closing.
        """



        print("OK clicked - override on_ok() for custom behavior")



        return True

    def on_cancel(self):
        """
        Override this method for custom Cancel behavior.
        Return False to prevent dialog from closing.
        """
        return True
