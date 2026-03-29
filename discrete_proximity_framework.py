from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QDialog
import os
from .activeodm_distancemap_dialog import ActiveODMDistanceMapDialog
from .combinedodm_distancemap_dialog import CombinedODMDistanceMapDialog
from .combinedreach_analysis_dialog import CombinedReachAnalysisDialog
from .poi_combined_reach_dialog import POICombinedReach
from .odm_reach_dialog import ODMReachDialog

from qgis.core import QgsMessageLog, Qgis


class DiscreteProximityFramework:
    def __init__(self, iface):
        """Constructor.

        iface: QGIS interface instance.
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.multimodal_action = None
        self.POICombinedReach = None
        self.ODMReach = None

    def tr(self, message):
        return QCoreApplication.translate('DiscreteProximityFramework', message)

    # Dialog implementation moved to activeodm_distancemap_dialog.py

    def initGui(self):
        """Create menu entries and toolbar icons inside QGIS GUI."""

        message = "2026-03-29C: Version 0.1.3-beta of Discrete Proximity Framework plugin loaded."
        QgsMessageLog.logMessage(message, 'DiscreteProximityFramework', Qgis.Info )
        
        # ActiveODM Distance Map action
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "ActiveDistanceMap.png")
        self.ActiveDistanceMap = QAction(QIcon(icon_path), self.tr('Active Model Distance Map'), self.iface.mainWindow())
        # keep object name consistent for testing/identification
        self.ActiveDistanceMap.setObjectName('actionActiveODM_DistanceMap')
        self.ActiveDistanceMap.setToolTip(self.tr('Run Active Model Distance Map'))
        self.ActiveDistanceMap.triggered.connect(self.run_activeodm_distancemap)

        # Add to Plugins menu
        self.iface.addPluginToMenu(self.tr('&Discrete Proximity Framework'), self.ActiveDistanceMap)
        # Add to toolbar (create toolbar if needed)
        try:
            self.iface.addToolBarIcon(self.ActiveDistanceMap)
        except Exception:
            # Older/newer QGIS may differ; ignore if toolbar API not present
            pass

        # Combined Model Distance Map action

        icon_path = os.path.join(os.path.dirname(__file__), "icons", "CombinedDistanceMap.png")
        self.CombinedDistanceMap = QAction(QIcon(icon_path), self.tr('Combined Model Distance Map'), self.iface.mainWindow())
        self.CombinedDistanceMap.setObjectName('actionCombinedModel_DistanceMap')
        self.CombinedDistanceMap.setToolTip(self.tr('Run Combined Model Distance Map (ActiveODM + GTFS + Walking)'))
        self.CombinedDistanceMap.triggered.connect(self.run_combinedodm_distancemap)

        # Add to Plugins menu
        self.iface.addPluginToMenu(self.tr('&Discrete Proximity Framework'), self.CombinedDistanceMap)

        try:
            self.iface.addToolBarIcon(self.CombinedDistanceMap)
        except Exception:
            # Older/newer QGIS may differ; ignore if toolbar API not present
            pass

        # ODM Reach action
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "Reach.png")
        self.ODMReach = QAction(QIcon(icon_path), self.tr('ODM Reach'), self.iface.mainWindow())
        self.ODMReach.setObjectName('actionODMReach')
        self.ODMReach.setToolTip(self.tr('Run ODM Reach Analysis'))
        self.ODMReach.triggered.connect(self.run_odm_reach)

        # Add to Plugins menu
        self.iface.addPluginToMenu(self.tr('&Discrete Proximity Framework'), self.ODMReach)

        try:
            self.iface.addToolBarIcon(self.ODMReach)
        except Exception:
            # Older/newer QGIS may differ; ignore if toolbar API not present
            pass

        # Combined Reach Analysis action

        # icon_path = os.path.join(os.path.dirname(__file__), "icons", "CombinedReach.png")
        # self.CombinedReach = QAction(QIcon(icon_path), self.tr('Combined Reach Analysis'), self.iface.mainWindow())
        # self.CombinedReach.setObjectName('actionCombinedReach')
        # self.CombinedReach.setToolTip(self.tr('Run Combined Reach Analysis'))
        # self.CombinedReach.triggered.connect(self.run_combinedreach)

        # # Add to Plugins menu
        # self.iface.addPluginToMenu(self.tr('&Discrete Proximity Framework'), self.CombinedReach)

        # try:
        #     self.iface.addToolBarIcon(self.CombinedReach)
        # except Exception:
        #     # Older/newer QGIS may differ; ignore if toolbar API not present
        #     pass

        # POI Combined Reach action

        icon_path = os.path.join(os.path.dirname(__file__), "icons", "CombinedReach.png")
        self.POICombinedReach = QAction(QIcon(icon_path), self.tr('POI Combined Reach'), self.iface.mainWindow())
        self.POICombinedReach.setObjectName('actionPOICombinedReach')
        self.POICombinedReach.setToolTip(self.tr('Run POI Combined Reach Analysis'))
        self.POICombinedReach.triggered.connect(self.run_poi_combined_reach)

        # Add to Plugins menu
        self.iface.addPluginToMenu(self.tr('&Discrete Proximity Framework'), self.POICombinedReach)

        try:
            self.iface.addToolBarIcon(self.POICombinedReach)
        except Exception:
            # Older/newer QGIS may differ; ignore if toolbar API not present
            pass

    def unload(self):
        """Remove the plugin menu item and icon."""
        if self.ActiveDistanceMap:
            try:
                self.iface.removePluginMenu(self.tr('&Discrete Proximity Framework'), self.ActiveDistanceMap)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.ActiveDistanceMap)
            except Exception:
                pass
        if self.CombinedDistanceMap:
            try:
                self.iface.removePluginMenu(self.tr('&Discrete Proximity Framework'), self.CombinedDistanceMap)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.CombinedDistanceMap)
            except Exception:
                pass
        if self.ODMReach:
            try:
                self.iface.removePluginMenu(self.tr('&Discrete Proximity Framework'), self.ODMReach)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.ODMReach)
            except Exception:
                pass
        # if self.CombinedReach:
        #     try:
        #         self.iface.removePluginMenu(self.tr('&Discrete Proximity Framework'), self.CombinedReach)
        #     except Exception:
        #         pass
        #     try:
        #         self.iface.removeToolBarIcon(self.CombinedReach)
        #     except Exception:
        #         pass
        if self.POICombinedReach:
            try:
                self.iface.removePluginMenu(self.tr('&Discrete Proximity Framework'), self.POICombinedReach)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.POICombinedReach)
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

    def run_odm_reach(self):
        """Handler for 'ODM Reach' action."""
        dialog = ODMReachDialog(self.iface.mainWindow(), iface=self.iface)
        result = dialog.exec_()

    # def run_combinedreach(self):
    #     """Handler for 'Combined Reach Analysis' action."""
    #     dialog = CombinedReachAnalysisDialog(self.iface.mainWindow(), iface=self.iface)
    #     result = dialog.exec_()

    def run_poi_combined_reach(self):
        """Handler for 'POI Combined Reach' action."""
        dialog = POICombinedReach(self.iface.mainWindow(), iface=self.iface)
        result = dialog.exec_()


