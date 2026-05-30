from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QMessageBox,
)
from PyQt5.QtCore import Qt

from gui import load_settings, save_settings
from core.scenario import list_scenarios


class AttackMixin:

    def _build_attack_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        s = load_settings()
        farm   = s.get("farm", {})
        deploy = s.get("attack", {}).get("deploy", {})

        def spin(lo, hi, val):
            sb = QSpinBox()
            sb.setRange(lo, hi)
            sb.setValue(val)
            sb.setSingleStep(10000)
            return sb

        def dspin(lo, hi, val, dec=2):
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setDecimals(dec)
            sb.setValue(val)
            return sb

        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.setAlignment(Qt.AlignTop)

        left = QWidget(); left.setStyleSheet("background: transparent;")
        lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(12)
        lv.setAlignment(Qt.AlignTop)

        right = QWidget(); right.setStyleSheet("background: transparent;")
        rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(12)
        rv.setAlignment(Qt.AlignTop)

        # ── Loot Thresholds ──────────────────────────────────────────────────
        grp_loot = QGroupBox("Loot Thresholds")
        lf = QFormLayout(grp_loot)
        lf.setSpacing(10)
        lf.setLabelAlignment(Qt.AlignRight)

        self._spin_gold   = spin(0, 9_999_999, farm.get("min_gold",        500_000))
        self._spin_elixir = spin(0, 9_999_999, farm.get("min_elixir",      500_000))
        self._spin_dark   = spin(0, 99_999,    farm.get("min_dark_elixir", 500))
        self._spin_dark.setSingleStep(100)
        lf.addRow("Min Gold",        self._spin_gold)
        lf.addRow("Min Elixir",      self._spin_elixir)
        lf.addRow("Min Dark Elixir", self._spin_dark)
        lv.addWidget(grp_loot)

        # ── Active Scenario ──────────────────────────────────────────────────
        grp_scen = QGroupBox("Active Scenario")
        sf = QFormLayout(grp_scen)
        sf.setSpacing(10)
        sf.setLabelAlignment(Qt.AlignRight)

        self._atk_scenario_cb = QComboBox()
        for name in list_scenarios():
            self._atk_scenario_cb.addItem(name)
        cur = deploy.get("active_scenario", "")
        if cur:
            idx = self._atk_scenario_cb.findText(cur)
            if idx >= 0:
                self._atk_scenario_cb.setCurrentIndex(idx)
        sf.addRow("Scenario", self._atk_scenario_cb)

        btn_set_active = QPushButton("Set Active")
        btn_set_active.clicked.connect(self._atk_set_active)
        sf.addRow("", btn_set_active)
        lv.addWidget(grp_scen)

        # ── Troop Bar Region ─────────────────────────────────────────────────
        grp_bar = QGroupBox("Troop Bar Region")
        bf = QFormLayout(grp_bar)
        bf.setSpacing(10)
        bf.setLabelAlignment(Qt.AlignRight)

        bar = deploy.get("troop_bar_region", [0, 730, 1600, 910])
        self._atk_bar_x1 = QSpinBox(); self._atk_bar_x1.setRange(0, 3000); self._atk_bar_x1.setValue(int(bar[0]))
        self._atk_bar_y1 = QSpinBox(); self._atk_bar_y1.setRange(0, 3000); self._atk_bar_y1.setValue(int(bar[1]))
        self._atk_bar_x2 = QSpinBox(); self._atk_bar_x2.setRange(0, 3000); self._atk_bar_x2.setValue(int(bar[2]))
        self._atk_bar_y2 = QSpinBox(); self._atk_bar_y2.setRange(0, 3000); self._atk_bar_y2.setValue(int(bar[3]))
        bf.addRow("Left",   self._atk_bar_x1)
        bf.addRow("Top",    self._atk_bar_y1)
        bf.addRow("Right",  self._atk_bar_x2)
        bf.addRow("Bottom", self._atk_bar_y2)
        rv.addWidget(grp_bar)

        # ── Tap Settings ─────────────────────────────────────────────────────
        grp_tap = QGroupBox("Tap Settings")
        tf = QFormLayout(grp_tap)
        tf.setSpacing(10)
        tf.setLabelAlignment(Qt.AlignRight)

        self._atk_tap_interval = dspin(0.0, 5.0, deploy.get("tap_interval", 0.15), dec=2)
        tf.addRow("Interval (s)", self._atk_tap_interval)
        rv.addWidget(grp_tap)

        cols.addWidget(left)
        cols.addWidget(right)
        root.addLayout(cols)
        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_save = QPushButton("Save")
        btn_save.setObjectName("btn_primary")
        btn_save.clicked.connect(self._save_attack)
        btn_row.addWidget(btn_save)
        root.addLayout(btn_row)
        return w

    def _atk_set_active(self):
        name = self._atk_scenario_cb.currentText()
        if not name:
            return
        s = load_settings()
        s["attack"]["deploy"]["active_scenario"] = name
        save_settings(s)
        self._refresh_scenario_list()
        QMessageBox.information(self, "Active", f"'{name}' set as active scenario.")

    def _save_attack(self):
        s = load_settings()
        s["farm"]["min_gold"]        = self._spin_gold.value()
        s["farm"]["min_elixir"]      = self._spin_elixir.value()
        s["farm"]["min_dark_elixir"] = self._spin_dark.value()
        deploy = s.setdefault("attack", {}).setdefault("deploy", {})
        deploy["mode"]             = "slot"
        deploy["troop_bar_region"] = [
            self._atk_bar_x1.value(), self._atk_bar_y1.value(),
            self._atk_bar_x2.value(), self._atk_bar_y2.value(),
        ]
        deploy["tap_interval"]     = self._atk_tap_interval.value()
        save_settings(s)
        QMessageBox.information(self, "Saved", "Attack settings saved.")
