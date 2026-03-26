from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QDialog
import os
from .activeodm_distancemap_dialog import ActiveODMDistanceMapDialog
from .combinedodm_distancemap_dialog import CombinedODMDistanceMapDialog


class DiscreteProximityFramework:
    def __init__(self, iface):
        """Constructor.

        iface: QGIS interface instance.
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.multimodal_action = None

    def tr(self, message):
        return QCoreApplication.translate('DiscreteProximityFramework', message)

# Dialog implementation moved to activeodm_distancemap_dialog.py

    def initGui(self):
        """Create menu entries and toolbar icons inside QGIS GUI."""

        # ActiveODM Distance Map action
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "ActiveDistanceMap.png")
        self.action = QAction(QIcon(icon_path), self.tr('Active Model Distance Map'), self.iface.mainWindow())
        # keep object name consistent for testing/identification
        self.action.setObjectName('actionActiveODM_DistanceMap')
        self.action.setToolTip(self.tr('Run Active Model Distance Map'))
        self.action.triggered.connect(self.run_activeodm_distancemap)

        # Add to Plugins menu
        self.iface.addPluginToMenu(self.tr('&Discrete Proximity Framework'), self.action)
        # Add to toolbar (create toolbar if needed)
        try:
            self.iface.addToolBarIcon(self.action)
        except Exception:
            # Older/newer QGIS may differ; ignore if toolbar API not present
            pass

        # Combined Model Distance Map action

        icon_path = os.path.join(os.path.dirname(__file__), "icons", "CombinedDistanceMap.png")
        self.multimodal_action = QAction(QIcon(icon_path), self.tr('Combined Model Distance Map'), self.iface.mainWindow())
        self.multimodal_action.setObjectName('actionCombinedModel_DistanceMap')
        self.multimodal_action.setToolTip(self.tr('Run Combined Model Distance Map (ActiveODM + GTFS + Walking)'))
        self.multimodal_action.triggered.connect(self.run_combinedodm_distancemap)

        # Add to Plugins menu
        self.iface.addPluginToMenu(self.tr('&Discrete Proximity Framework'), self.multimodal_action)

    def unload(self):
        """Remove the plugin menu item and icon."""
        if self.action:
            try:
                self.iface.removePluginMenu(self.tr('&Discrete Proximity Framework'), self.action)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.action)
            except Exception:
                pass
        if self.multimodal_action:
            try:
                self.iface.removePluginMenu(self.tr('&Discrete Proximity Framework'), self.multimodal_action)
            except Exception:
                pass

    def run_activeodm_distancemap(self):
        """Handler for 'ActiveODM_DistanceMap' action."""
        dialog = ActiveODMDistanceMapDialog(self.iface.mainWindow(), iface=self.iface)
        result = dialog.exec_()

    def run_combinedodm_distancemap(self):
        """Handler for 'Multimodal_DistanceMap' action."""
        dialog = CombinedODMDistanceMapDialog(self.iface.mainWindow(), iface=self.iface)
        result = dialog.exec_()


