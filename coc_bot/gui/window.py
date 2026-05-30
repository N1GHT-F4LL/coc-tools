from PyQt5.QtWidgets import QMainWindow, QTabWidget
from PyQt5.QtCore import QTimer

from .tabs.control   import ControlMixin
from .tabs.studio    import StudioMixin
from .tabs.device    import DeviceMixin
from .tabs.attack    import AttackMixin
from .tabs.scenarios import ScenariosMixin


class MainWindow(ControlMixin, StudioMixin, DeviceMixin, AttackMixin, ScenariosMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CoC Bot")
        self.resize(1200, 780)
        self._bot_thread = None
        self._studio_points = []
        self._last_studio_frame = None
        self._slots_data = []
        self._variants_data = []
        self._current_variant_idx = 0
        self._current_node_id = None
        self._current_deploy_row = -1
        self._current_scenario = None
        self._node_single_action = False

        self._save_debounce = QTimer(self)
        self._save_debounce.setSingleShot(True)
        self._save_debounce.timeout.connect(self._scenario_save)

        tabs = QTabWidget()
        tabs.addTab(self._build_control_tab(),    "Control")
        tabs.addTab(self._build_attack_tab(),     "Attack")
        tabs.addTab(self._build_scenarios_tab(),  "Troops")
        tabs.addTab(self._build_studio_tab(),     "Studio")
        tabs.addTab(self._build_device_tab(),     "Device")
        tabs.currentChanged.connect(
            lambda i: self._graph_canvas.fit_view() if i == 2 else None)
        self.setCentralWidget(tabs)
