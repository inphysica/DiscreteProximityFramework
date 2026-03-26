from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QDialog
import os
from .activeodm_distancemap_dialog import ActiveODMDistanceMapDialog


class DiscreteProximityFramework:
    def __init__(self, iface):
        """Constructor.

        iface: QGIS interface instance.
        """
        self.iface = iface
        # plugin_dir used to locate bundled resources like icons
        # try to compute plugin directory relative to this file
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None

    def tr(self, message):
        return QCoreApplication.translate('DiscreteProximityFramework', message)

# Dialog implementation moved to activeodm_distancemap_dialog.py

    def initGui(self):
        """Create menu entries and toolbar icons inside QGIS GUI."""
        # Load plugin icon from file if available
        # icon_path = os.path.join(self.plugin_dir, 'icons_DistanceMap.png')
        # if os.path.exists(icon_path):
        #     icon = QIcon(icon_path)
        # else:
        #     icon = QIcon()
        self.action = QAction(self._logo_icon(), self.tr('ActiveODM_DistanceMap'), self.iface.mainWindow())
        # keep object name consistent for testing/identification
        self.action.setObjectName('actionActiveODM_DistanceMap')
        self.action.setToolTip(self.tr('Run ActiveODM Distance Map'))
        self.action.triggered.connect(self.run_activeodm_distancemap)

        # Add to Plugins menu
        self.iface.addPluginToMenu(self.tr('&Discrete Proximity Framework'), self.action)
        # Add to toolbar (create toolbar if needed)
        try:
            self.iface.addToolBarIcon(self.action)
        except Exception:
            # Older/newer QGIS may differ; ignore if toolbar API not present
            pass

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

    def run_activeodm_distancemap(self):
        """Handler for 'ActiveODM_DistanceMap' action.

        For now it shows a simple message box. Replace with actual logic later.
        """
        # diagnostic message to QGIS log when the action is triggered
        # try:
        #     from qgis.core import QgsMessageLog, Qgis
        #     QgsMessageLog.logMessage('ActiveODM_DistanceMap action triggered', 'DiscreteProximityFramework', Qgis.Info)
        # except Exception:
        #     pass

        dialog = ActiveODMDistanceMapDialog(self.iface.mainWindow(), iface=self.iface)
        result = dialog.exec_()
        # if result == QDialog.Accepted:
        #     QMessageBox.information(self.iface.mainWindow(), self.tr('ActiveODM_DistanceMap'), self.tr('ActiveODM Distance Map: OK pressed.'))
        # else:
        #     QMessageBox.information(self.iface.mainWindow(), self.tr('ActiveODM_DistanceMap'), self.tr('ActiveODM Distance Map: Cancelled.'))


    def _logo_icon(self):
        """Load the MCP logo from the plugin directory."""
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "DistanceMap.png")
        return QIcon(icon_path)