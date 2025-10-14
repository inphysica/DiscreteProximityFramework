"""

ActiveODMDistanceMapDialog

Well-formed implementation that remembers per-layer id/name field
selections in memory only, restores them when switching layers, and
logs diagnostic messages to the QGIS log.

"""

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QPushButton, QLineEdit, QFileDialog, QMessageBox, QProgressBar
from qgis.PyQt.QtCore import QTimer, QSettings
from qgis.core import QgsVectorLayerExporter, QgsVectorFileWriter, QgsCoordinateTransformContext, QgsWkbTypes, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication

from qgis.core import QgsField
from qgis.PyQt.QtCore import QVariant

import os

try:
    from qgis.core import QgsMessageLog, Qgis, QgsProject
except Exception:
    QgsMessageLog = None
    Qgis = None
    QgsProject = None



from .Analytics.IO import read_ODM


UI_PATH = os.path.join(os.path.dirname(__file__), 'activeodm_distancemap_dialog_base.ui')
FORM_CLASS, _ = uic.loadUiType(UI_PATH)

# In-memory (plugin runtime) storage of last chosen ODM file path. Not persisted to disk.
_LAST_ODM_PATH = None
# settings key to persist last selected ODM file across QGIS sessions
SETTINGS_KEY = 'DiscreteProximityFramework/last_odm_path'


class ActiveODMDistanceMapDialog(QDialog, FORM_CLASS):
    """Dialog which stores per-layer field selections in memory."""

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
                        self.layer_field_map.setdefault(lay.id(), {'id_field': None, 'name_field': None})
                    except Exception:
                        continue
            except Exception:
                pass


        self.prep_Defaults()


        # connect layer widget signals (support various QGIS versions)
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

        # defer initial update to let widgets populate
        QTimer.singleShot(0, lambda: self.updateLayer(None))

        # connect dialog buttons (OK / Cancel)
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
        settings.setValue('DiscreteProximityFramework/last_odm_path', self.fileSelector.filePath())
        last_odm_path = settings.value('DiscreteProximityFramework/last_odm_path','')

        speed_raw = settings.setValue('DiscreteProximityFramework/Speed',self.speedDial.value())
        max_duration_raw = settings.setValue('DiscreteProximityFramework/MaxDuration',self.MaxDurationDial.value())
        max_distance_raw = settings.setValue('DiscreteProximityFramework/MaxDistance',self.MaxDistanceDial.value())

        self._log(f"Storing last ODM path: {last_odm_path}")
        self._log(f"Storing speed: {speed_raw}")
        self._log(f"Storing max duration: {max_duration_raw}")
        self._log(f"Storing max distance: {max_distance_raw}")

        self._log(f"Current layer id: {self.current_layer_id}")
        
        if self.Evaluate():

            self.labelCurrentStatus.setText("Start build...")
            self.repaint()

            if (self.Build()):
                self._log("Build successful")
                
            else:
                self._log("Build failed")
                return
            
        else:

            self.labelCurrentStatus.setText(" Exit without build")
            self.repaint()
            return


        """Internal OK handler: call user-defined on_ok, then accept dialog."""
        try:
            self._log('OK pressed')
        except Exception:
            pass
        ok_to_close = True
        try:
            # user hook: if it returns False, do not close
            res = self.on_ok()
            if res is False:
                ok_to_close = False
        except Exception:
            # on exception, do not block closing
            ok_to_close = True

        if ok_to_close:
            try:
                self.accept()
            except Exception:
                try:
                    # fallback for older dialogs
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

    def _save_current_selection(self, layer_id=None):
        if layer_id is None:
            layer_id = self.current_layer_id
        if not layer_id:
            return
        id_sel, name_sel = self._get_selector()
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
        id_sel, name_sel = self._get_selector()
        restored = False
        if id_sel is not None and data.get('id_field'):
            restored = self._try_set_selector_by_name(id_sel, data.get('id_field')) or restored
        if name_sel is not None and data.get('name_field'):
            restored = self._try_set_selector_by_name(name_sel, data.get('name_field')) or restored

        if not restored and QgsProject is not None:
            # schedule a retry after UI finishes populating
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

    def _log_settings(self):
        """Read plugin-related settings and log them for diagnostics."""
        try:
            settings = QSettings()
            # Try to list at least the last_odm_path key and any keys under our plugin root
            try:
                val = settings.value(SETTINGS_KEY, None)
                self._log(f"QSettings[{SETTINGS_KEY}] = {val}", level='debug')
            except Exception:
                pass

            # Scan for other keys under our prefix
            try:
                # QSettings doesn't provide a direct 'keys under prefix' cross-platform API,
                # but we can attempt to read the whole group if supported.
                settings.beginGroup('DiscreteProximityFramework')
                for key in settings.allKeys():
                    try:
                        v = settings.value(key)
                        self._log(f"QSettings[DiscreteProximityFramework/{key}] = {v}", level='debug')
                    except Exception:
                        pass
                settings.endGroup()
            except Exception:
                pass
        except Exception:
            pass

    def _log(self, message, level='info'):
        if QgsMessageLog is None:
            return
        try:
            lvl = Qgis.Info if level == 'info' else Qgis.Debug
            QgsMessageLog.logMessage(message, 'DiscreteProximityFramework', lvl)
        except Exception:
            pass

    def _get_selector(self):
        """Return tuple (id_selector, name_selector) trying common names."""
        return (getattr(self, 'IdFieldSelector', None) or getattr(self, 'idSelector', None),
                getattr(self, 'NameFieldSelector', None) or getattr(self, 'nameSelector', None))

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

        self.fileSelector.setDialogTitle("Select SQLite ODM file")
        self.fileSelector.setFilter("SQLite files (*.sqlite *.db *.gpkg);;All files (*)")

        settings = QSettings()
        last_odm_path = ""
        if settings.contains('DiscreteProximityFramework/last_odm_path'):
            last_odm_path = settings.value('DiscreteProximityFramework/last_odm_path','')
            if os.path.exists(last_odm_path):
                try:
                    self.fileSelector.setFilePath(last_odm_path)
                    self._log(f"Restored last ODM file path: {last_odm_path}")
                except Exception:
                    self._log(f"Failed to restore ODM file path: {last_odm_path}", level='debug')
            else:
                last_odm_path = ""
                settings.setValue('DiscreteProximityFramework/last_odm_path', '')

        speed_raw = settings.value('DiscreteProximityFramework/Speed',4.5)
        max_duration_raw = settings.value('DiscreteProximityFramework/MaxDuration',20)
        max_distance_raw = settings.value('DiscreteProximityFramework/MaxDistance',1.5)

        self.speedDial.setValue(float(speed_raw))
        self.MaxDurationDial.setValue(float(max_duration_raw))
        self.MaxDistanceDial.setValue(float(max_distance_raw))

    def updateLayer(self, layer):
        # allow signals to call with None and resolve currentLayer
        if layer is None:
            layer_widget = getattr(self, 'inputLayer', None)
            if layer_widget is not None and hasattr(layer_widget, 'currentLayer'):
                try:
                    layer = layer_widget.currentLayer()
                except Exception:
                    layer = None

        id_sel, name_sel = self._get_selector()

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

        # set preview widgets' layer if present
        id_feat = getattr(self, 'IdFeature', None)
        name_feat = getattr(self, 'NameFeature', None)
        if id_feat is not None and hasattr(id_feat, 'setLayer'):
            id_feat.setLayer(layer)
        if name_feat is not None and hasattr(name_feat, 'setLayer'):
            name_feat.setLayer(layer)

        # block signals while we programmatically change selectors
        try:
            if id_sel is not None and hasattr(id_sel, 'blockSignals'):
                id_sel.blockSignals(True)
        except Exception:
            pass
        try:
            if name_sel is not None and hasattr(name_sel, 'blockSignals'):
                name_sel.blockSignals(True)
        except Exception:
            pass

        # if selectors support setLayer, try to set it
        try:
            if id_sel is not None and hasattr(id_sel, 'setLayer'):
                id_sel.setLayer(layer)
        except Exception:
            pass
        try:
            if name_sel is not None and hasattr(name_sel, 'setLayer'):
                name_sel.setLayer(layer)
        except Exception:
            pass

        # unblock signals
        try:
            if id_sel is not None and hasattr(id_sel, 'blockSignals'):
                id_sel.blockSignals(False)
        except Exception:
            pass
        try:
            if name_sel is not None and hasattr(name_sel, 'blockSignals'):
                name_sel.blockSignals(False)
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

        # reconnect handlers bound to current layer id
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

        try:
            self.updateFeatureDisplays()
        except Exception:
            pass

    def updateFeatureDisplays(self, *args):
        id_sel, name_sel = self._get_selector()
        id_field = self._get_current_field(id_sel)
        name_field = self._get_current_field(name_sel)

        id_feat = getattr(self, 'IdFeature', None)
        if id_feat is not None and hasattr(id_feat, 'setDisplayExpression'):
            id_feat.setDisplayExpression(f'"{id_field}"' if id_field else '$id')

        name_feat = getattr(self, 'NameFeature', None)
        if name_feat is not None and hasattr(name_feat, 'setDisplayExpression'):
            name_feat.setDisplayExpression(f'"{name_field}"' if name_field else '$id')

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
            except Exception:
                fields = []
            if fields:
                id_field_name = fields[0].name()
                name_field_name = id_field_name

        id_sel, name_sel = self._get_selector()
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

        # connect handlers for persisting changes for this layer
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

        self.updateFeatureDisplays()

    def Evaluate(self, max_features=100):

        # Count features in input layer
        # Count selected features if onlySelectedFeatures is True

        self.labelCurrentStatus.setText("Evaluating dataset...")
        self.repaint()

        src_layer = QgsProject.instance().mapLayer(self.current_layer_id)

        if self.checkBox_ResultDistance.isChecked() == False and self.checkBox_ResultDuration.isChecked() == False:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "No output selected",
                "You have not selected any output (distance and/or duration). Please select at least one output option.",
                QMessageBox.Ok
            )
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
                    # user confirm
                    return True
                else:
                    # user canceled
                    return False
            if (len(selected_features) == 0):

                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "No features selected",
                    "You have chosen to process only selected features, but no features are selected in the input layer. Please select some features or uncheck the 'only selected features' option.",
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
                    # user confirm
                    return True
                else:
                    # user canceled
                    return False
                
        return True

    def Build(self):

        # Load ODM file

        self.labelCurrentStatus.setText("Collecting Features ...")
        self.repaint()

        origins, selection = sub_collectPairs(self, name_field=self.nameSelector.currentText(), id_field=self.idSelector.currentText(), use_name=self.checkBox_IncludeName.isChecked())

        odm_path = self.fileSelector.filePath()

        self.labelCurrentStatus.setText("Reading ODM file ...")
        self.repaint()

        min_limit = min(self.speedDial.value() * (self.MaxDurationDial.value() / 60)*1000, self.MaxDistanceDial.value()*1000)  # in meters

        ODM = read_ODM(odm_path, False, bar=self.progressBar, selection=selection, limit=min_limit)
        if ODM is None:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Error matching origins",
                "It seems that you have selected wrong ID field or the ODM file does not contain matching origins. Please check your selections. Typical attribute is PosID",
                QMessageBox.Ok
            )
            return False

        self.labelCurrentStatus.setText("Building distance map ...")
        self.repaint()

        # ODM[origin][destination] = (distance, duration)

        src_layer = QgsProject.instance().mapLayer(self.current_layer_id)
        distanceMap = sub_BuildDistanceMap(self, ODM, origins, src_layer=src_layer, speed=self.speedDial.value(), bar=self.progressBar)

        self.labelCurrentStatus.setText("Exporting results ...")
        self.repaint()

        sub_Export(self, distanceMap, origins)

        self.labelCurrentStatus.setText("Done")
        self.repaint()

        return True


def sub_collectPairs(self, name_field, id_field, use_name=True):

    src_layer = QgsProject.instance().mapLayer(self.current_layer_id)

    all_features = [feat for feat in src_layer.getFeatures()]

    if (self.onlySelectedFeatures.isChecked() == True):

        features = src_layer.selectedFeatures()
        
    else:

        features = all_features


    origins = []
    selection = []

    self.labelCurrentStatus.setText("Collecting origins ...")
    self.repaint()
    bar = self.progressBar
    bar.setMaximum(len(features))
    bar.setValue(0)
    bar.repaint()
    QCoreApplication.processEvents()

    for i, feat in enumerate(features):

        bar.setValue(i)
        QCoreApplication.processEvents()
        
        id_ = str(feat[id_field])

        if use_name:
            name = str(feat[name_field]) + " ({id})"
        else:
            name = str(id_)  

        origins.append( (id_, name) )
        selection.append(id_)


    

    return origins, selection

def sub_BuildDistanceMap(self, ODM, origins, src_layer, speed=4.5, bar=None):

    # ODM[origin][destination] = (distance, duration)

    DistanceMap = {}

    if bar is not None:
        bar.setMaximum(len(origins))
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()

    for i, (id_, name) in enumerate(origins):

        if bar is not None:
            bar.setValue(i)
            QCoreApplication.processEvents()

        if id_ not in ODM:
            continue

        dests = ODM[id_]

        DistanceMap[id_] = {}


        for dest_id, (distance, duration) in dests.items():


            # if distance > max_range * 1000:  # convert km to m
            #     continue

            walk_time = distance / (speed * 1000 / 60)  # speed km/h -> m/min

            DistanceMap[id_][dest_id] = (distance, duration, walk_time)

    return DistanceMap

def sub_Export(self, distancemap, origins):


    # https://qgis.org/pyqgis/master/core/QgsVectorLayer.html

    src_layer = QgsProject.instance().mapLayer(self.current_layer_id)
    print(src_layer.dataProvider().dataSourceUri())

    # layer = QgsVectorLayer(src_layer.dataProvider().dataSourceUri(), "polygon", "ogr")
    feats = [feat for feat in src_layer.getFeatures()]


    # print(src_layer.crs().authid())
    # print(QgsWkbTypes.displayString(wkb_type))

    wkb_type = src_layer.wkbType()
    uri=QgsWkbTypes.displayString(wkb_type) + "?crs=" + src_layer.crs().authid()

    mem_layer = QgsVectorLayer(uri, "Results", "memory")

    mem_layer_data = mem_layer.dataProvider()
    attr = src_layer.dataProvider().fields().toList()
    mem_layer_data.addAttributes(attr)
    mem_layer.updateFields()
    mem_layer_data.addFeatures(feats)


    # Lets populate all new fields

    mem_layer.startEditing()

    self.labelCurrentStatus.setText("Preparing new fields...")
    self.repaint()

    bar=self.progressBar
    if bar is not None:
        bar.setMaximum(len(origins))
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()



    for i, origin in enumerate(origins):
        bar.setValue(i)
        QCoreApplication.processEvents()

        id_ = origin[0]
        name = origin[1]

        if self.checkBox_ResultDistance.isChecked():
            new_field = QgsField(f"from_{name}_Distance", QVariant.Double)
            mem_layer.addAttribute(new_field)
        if self.checkBox_ResultDuration.isChecked():
            new_field = QgsField(f"from_{name}_Duration", QVariant.Double)
            mem_layer.addAttribute(new_field)

    mem_layer.updateFields()
    mem_layer.commitChanges()

    self.labelCurrentStatus.setText("Populateing attributes with distance data...")
    self.repaint()


    if bar is not None:
        bar.setMaximum(len(feats))
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()


    mem_layer.startEditing()


    for i, f in enumerate(mem_layer.getFeatures()):

        bar.setValue(i)
        QCoreApplication.processEvents()

        destination = f[ self.idSelector.currentText()] # destination ID

        for origin in origins:

            id_ = origin[0]
            name = origin[1]

            result_distance = -1
            result_duration = -1

            if destination == id_:
                result_distance = 0
                result_duration = 0

            if id_  in distancemap:
                if destination  in distancemap[id_]:
                    
                    distance, duration, walk_time = distancemap[id_][destination]

                    result_distance = distance
                    result_duration = duration

            if self.checkBox_ResultDistance.isChecked():
                f[f"from_{name}_Distance"] = result_distance # convert to km
            if self.checkBox_ResultDuration.isChecked():
                f[f"from_{name}_Duration"] = result_duration  # in minutes

            mem_layer.updateFeature(f)

    

    # mem_layer.startEditing()
    # for f in mem_layer.getFeatures():
    #     f["new_column"] = "XX_"  + f["PosID"] 
    #     mem_layer.updateFeature(f)
    # mem_layer.commitChanges()


    QgsProject.instance().addMapLayer(mem_layer)



    # Evalute dataset
    
    # Import ODM
    # 



    # self.copy_via_exporter(src_layer)

    # err = QgsVectorLayerExporter.exportLayer(
    #         src_layer,          # QgsVectorLayer
    #         "",                 # uri (unused for memory)
    #         "memory",           # provider
    #         src_layer.crs(),    # <- destCRS (QgsCoordinateReferenceSystem), NOT a transform context
    #         False              # onlySelected
    #     )
    

    # print(err)
    # QgsProject.instance().addMapLayer(err)


    # mem_layer = exporter.layer()
    # if mem_layer:
    #     mem_layer.setName(src_layer.name() + " (temp)")


    
