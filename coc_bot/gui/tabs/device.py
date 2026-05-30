from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QGroupBox, QFormLayout,
    QComboBox, QLineEdit, QPushButton, QCheckBox, QSpinBox, QDoubleSpinBox,
    QLabel, QMessageBox, QFileDialog,
)
from PyQt5.QtCore import Qt

from gui import load_settings, save_settings


class DeviceMixin:

    _PROFILE_DEFAULT_SERIALS = {
        "bluestacks":       "127.0.0.1:5555",
        "ldplayer":         "127.0.0.1:5555",
        "nox":              "127.0.0.1:62001",
        "mumu":             "127.0.0.1:7555",
        "android_emulator": "127.0.0.1:5554",
    }

    def _build_device_tab(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(12)
        v.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        s = load_settings()
        dev    = s.get("device", {})
        delays = s.get("delays", {})
        jitter = s.get("jitter", {})

        def hrow(*widgets):
            c = QWidget()
            c.setStyleSheet("background: transparent;")
            h = QHBoxLayout(c)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            for ww in widgets:
                h.addWidget(ww)
            return c

        def dspin(lo, hi, val, dec=2):
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setDecimals(dec)
            sb.setValue(val)
            return sb

        # ── Emulator Profile ─────────────────────────────────────────────────
        grp_prof = QGroupBox("Emulator Profile")
        pf = QFormLayout(grp_prof)
        pf.setSpacing(8)
        pf.setLabelAlignment(Qt.AlignRight)

        self._dev_profile = QComboBox()
        for key, lbl in [
            ("bluestacks",       "BlueStacks"),
            ("ldplayer",         "LDPlayer"),
            ("nox",              "Nox"),
            ("mumu",             "MuMu"),
            ("android_emulator", "Android Emulator"),
        ]:
            self._dev_profile.addItem(lbl, key)
        idx = self._dev_profile.findData(dev.get("profile", "bluestacks"))
        if idx >= 0:
            self._dev_profile.setCurrentIndex(idx)
        pf.addRow("Profile", self._dev_profile)

        self._dev_emu_path = QLineEdit(dev.get("emulator_path", ""))
        self._dev_emu_path.setPlaceholderText("Emulator .exe path  (auto-detect if empty)")
        btn_browse_emu = QPushButton("Browse…")
        pf.addRow("Emulator exe", hrow(self._dev_emu_path, btn_browse_emu))

        self._dev_adb_path = QLineEdit(dev.get("adb_path", ""))
        self._dev_adb_path.setPlaceholderText("adb.exe path  (auto-detect from PATH if empty)")
        btn_browse_adb = QPushButton("Browse…")
        pf.addRow("ADB path", hrow(self._dev_adb_path, btn_browse_adb))

        self._dev_auto_launch = QCheckBox("Auto-launch emulator if not running")
        self._dev_auto_launch.setChecked(dev.get("auto_launch_profile", True))
        pf.addRow("", self._dev_auto_launch)

        v.addWidget(grp_prof)

        # ── ADB Connection ───────────────────────────────────────────────────
        grp_conn = QGroupBox("ADB Connection")
        cf = QFormLayout(grp_conn)
        cf.setSpacing(8)
        cf.setLabelAlignment(Qt.AlignRight)

        self._dev_serial = QLineEdit(dev.get("serial", ""))
        self._dev_serial.setPlaceholderText("e.g.  127.0.0.1:5555")
        cf.addRow("Serial", self._dev_serial)

        self._dev_endpoint = QLineEdit(dev.get("endpoint", ""))
        self._dev_endpoint.setPlaceholderText("Override connect endpoint  (optional)")
        cf.addRow("Endpoint", self._dev_endpoint)

        self._dev_strict   = QCheckBox("Strict serial — fail if serial not found in adb devices")
        self._dev_auto_sel = QCheckBox("Auto-select single device")
        self._dev_strict.setChecked(dev.get("strict_serial", True))
        self._dev_auto_sel.setChecked(dev.get("auto_select_single", True))
        cf.addRow("", self._dev_strict)
        cf.addRow("", self._dev_auto_sel)

        btn_test = QPushButton("Test Connection")
        self._dev_adb_result = QLabel("—")
        self._dev_adb_result.setWordWrap(True)
        self._dev_adb_result.setStyleSheet("color:#6c7086; font-size:9pt;")
        cf.addRow("", hrow(btn_test))
        cf.addRow("Result", self._dev_adb_result)

        v.addWidget(grp_conn)

        # ── Display ──────────────────────────────────────────────────────────
        grp_disp = QGroupBox("Display")
        df = QFormLayout(grp_disp)
        df.setSpacing(8)
        df.setLabelAlignment(Qt.AlignRight)

        self._dev_enforce_res = QCheckBox("Enforce target resolution at startup")
        self._dev_enforce_res.setChecked(dev.get("enforce_resolution", True))
        df.addRow("", self._dev_enforce_res)

        self._dev_res = QComboBox()
        self._dev_res.setEditable(True)
        for r in ["1600x900", "1280x720", "960x540"]:
            self._dev_res.addItem(r)
        cur_res = dev.get("target_resolution", "1600x900")
        if self._dev_res.findText(cur_res) < 0:
            self._dev_res.addItem(cur_res)
        self._dev_res.setCurrentText(cur_res)
        df.addRow("Resolution", self._dev_res)

        self._dev_density = QSpinBox()
        self._dev_density.setRange(120, 640)
        self._dev_density.setValue(dev.get("target_density", 240))
        df.addRow("Density (DPI)", self._dev_density)

        v.addWidget(grp_disp)

        # ── Timing & Jitter ──────────────────────────────────────────────────
        grp_timing = QGroupBox("Timing & Jitter")
        tf = QFormLayout(grp_timing)
        tf.setSpacing(8)
        tf.setLabelAlignment(Qt.AlignRight)

        self._spin_s_min  = dspin(0, 60,  delays.get("short_min",  0.5))
        self._spin_s_max  = dspin(0, 60,  delays.get("short_max",  1.5))
        self._spin_l_min  = dspin(0, 120, delays.get("long_min",   2.0))
        self._spin_l_max  = dspin(0, 120, delays.get("long_max",   4.0))
        self._spin_jitter = dspin(0, 100, jitter.get("radius",     5.0), dec=1)
        tf.addRow("Short delay min (s)",  self._spin_s_min)
        tf.addRow("Short delay max (s)",  self._spin_s_max)
        tf.addRow("Long delay min (s)",   self._spin_l_min)
        tf.addRow("Long delay max (s)",   self._spin_l_max)
        tf.addRow("Jitter radius (px)",   self._spin_jitter)
        v.addWidget(grp_timing)

        btn_save = QPushButton("Save")
        btn_save.setObjectName("btn_primary")
        v.addWidget(btn_save)
        v.addStretch()

        btn_browse_emu.clicked.connect(self._browse_emu_path)
        btn_browse_adb.clicked.connect(self._browse_adb_path)
        btn_test.clicked.connect(self._test_adb_connection)
        btn_save.clicked.connect(self._save_device)
        self._dev_profile.currentIndexChanged.connect(self._on_profile_changed)

        return w

    def _on_profile_changed(self):
        profile = self._dev_profile.currentData()
        default = self._PROFILE_DEFAULT_SERIALS.get(profile, "127.0.0.1:5555")
        cur = self._dev_serial.text().strip()
        if not cur or cur in self._PROFILE_DEFAULT_SERIALS.values():
            self._dev_serial.setText(default)

    def _browse_emu_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Emulator Executable", "", "Executables (*.exe);;All Files (*)")
        if path:
            self._dev_emu_path.setText(path)

    def _browse_adb_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ADB Executable", "", "Executables (*.exe);;All Files (*)")
        if path:
            self._dev_adb_path.setText(path)

    def _test_adb_connection(self):
        import subprocess
        import shutil as _shutil
        adb = self._dev_adb_path.text().strip() or _shutil.which("adb")
        if not adb:
            self._dev_adb_result.setText("adb not found in PATH.")
            self._dev_adb_result.setStyleSheet("color:#f38ba8;")
            return
        try:
            res = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5)
            lines = [l.strip() for l in (res.stdout or "").splitlines()
                     if l.strip() and "List of devices" not in l]
            if lines:
                self._dev_adb_result.setText("\n".join(lines))
                self._dev_adb_result.setStyleSheet("color:#a6e3a1;")
            else:
                self._dev_adb_result.setText("No devices found.")
                self._dev_adb_result.setStyleSheet("color:#f9e2af;")
        except Exception as e:
            self._dev_adb_result.setText(f"Error: {e}")
            self._dev_adb_result.setStyleSheet("color:#f38ba8;")

    def _save_device(self):
        s = load_settings()
        s.setdefault("device", {})
        d = s["device"]
        d["profile"]             = self._dev_profile.currentData()
        d["emulator_path"]       = self._dev_emu_path.text().strip()
        d["adb_path"]            = self._dev_adb_path.text().strip()
        d["serial"]              = self._dev_serial.text().strip()
        d["endpoint"]            = self._dev_endpoint.text().strip()
        d["strict_serial"]       = self._dev_strict.isChecked()
        d["auto_select_single"]  = self._dev_auto_sel.isChecked()
        d["auto_launch_profile"] = self._dev_auto_launch.isChecked()
        d["enforce_resolution"]  = self._dev_enforce_res.isChecked()
        d["target_resolution"]   = self._dev_res.currentText().strip()
        d["target_density"]      = self._dev_density.value()
        s["delays"]["short_min"] = self._spin_s_min.value()
        s["delays"]["short_max"] = self._spin_s_max.value()
        s["delays"]["long_min"]  = self._spin_l_min.value()
        s["delays"]["long_max"]  = self._spin_l_max.value()
        s["jitter"]["radius"]    = self._spin_jitter.value()
        save_settings(s)
        QMessageBox.information(self, "Saved", "Device settings saved.")
