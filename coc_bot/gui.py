# torch DLLs must be loaded in the main thread BEFORE Qt loads its own DLLs,
# otherwise Windows raises WinError 1114 (DLL_INIT_FAILED) when torch is first
# imported inside a QThread. Importing here (at module level, before PyQt5)
# ensures _load_dll_libraries() runs in a clean main-thread context once.
try:
    import torch  # noqa: F401
except (ImportError, OSError):
    pass

import sys
import os
import json
import logging
import threading
import traceback
import html as _html
from pathlib import Path

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTextEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QListWidget, QTableWidget, QTableWidgetItem,
    QGroupBox, QFormLayout, QSplitter, QScrollArea,
    QHeaderView, QMessageBox, QSizePolicy, QInputDialog,
    QLineEdit, QCheckBox, QFileDialog,
)
from core.scenario import list_scenarios, load_scenario, save_scenario, delete_scenario, rename_scenario
from PyQt5.QtCore import Qt, QThread, QRunnable, QThreadPool, QObject, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QFont, QTextCursor

# gui.py lives in coc_bot/ — same sys.path as main.py
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
ASSETS_PATH   = os.path.join(os.path.dirname(__file__), "assets")


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def load_settings():
    with open(SETTINGS_PATH) as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


# ---------------------------------------------------------------------------
# Qt log handler — bridges Python logging into the GUI log panel
# ---------------------------------------------------------------------------

class _LogSignals(QObject):
    record = pyqtSignal(str, str)  # (levelname, formatted_message)

class QtLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.signals = _LogSignals()
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))

    def emit(self, record):
        try:
            self.signals.record.emit(record.levelname, self.format(record))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Bot background thread
# ---------------------------------------------------------------------------

class BotThread(QThread):
    log_line = pyqtSignal(str, str)  # (levelname, formatted_message)
    status   = pyqtSignal(str)       # "running" | "stopped" | "error:<msg>"

    def __init__(self):
        super().__init__()
        self._stop = None

    def run(self):
        from core.logging_utils import setup_logging
        from main import run_bot, load_settings as _load

        # setup_logging clears handlers — call it first, then add our Qt handler
        setup_logging(logging.INFO)
        qt_handler = QtLogHandler()
        qt_handler.signals.record.connect(self.log_line)
        logging.getLogger().addHandler(qt_handler)

        self._stop = threading.Event()
        try:
            settings = _load()
            self.status.emit("running")
            run_bot(settings, stop_event=self._stop, non_interactive=True)
            self.status.emit("stopped")
        except Exception as e:
            self.log_line.emit("ERROR", traceback.format_exc())
            self.status.emit(f"error:{e}")
        finally:
            logging.getLogger().removeHandler(qt_handler)

    def request_stop(self):
        if self._stop is not None:
            self._stop.set()


# ---------------------------------------------------------------------------
# Screenshot worker — runs in thread pool to keep GUI responsive
# ---------------------------------------------------------------------------

class _SsSignals(QObject):
    done  = pyqtSignal(object)  # numpy BGR array
    error = pyqtSignal(str)

class ScreenshotWorker(QRunnable):
    def __init__(self, settings):
        super().__init__()
        self.signals = _SsSignals()
        self._settings = settings

    def run(self):
        try:
            from ppadb.client import Client as AdbClient
            serial = self._settings.get("device", {}).get("serial", "127.0.0.1:5555")
            client = AdbClient(host="127.0.0.1", port=5037)
            dev = client.device(serial)
            if dev is None:
                self.signals.error.emit(f"Device '{serial}' not found. Is ADB running?")
                return
            raw = dev.screencap()
            arr = np.frombuffer(raw, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                self.signals.error.emit("screencap returned empty data.")
                return
            self.signals.done.emit(frame)
        except Exception as e:
            self.signals.error.emit(str(e))


# ---------------------------------------------------------------------------
# Clickable image label with point-overlay for macro recorder
# ---------------------------------------------------------------------------

class ClickableImageLabel(QLabel):
    point_added = pyqtSignal(int, int)  # original device (x, y)

    def __init__(self):
        super().__init__()
        self._orig_frame = None
        self._markers = []      # [(orig_x, orig_y), ...]
        self._scale_x = 1.0
        self._scale_y = 1.0
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setCursor(Qt.CrossCursor)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#11111b; border:1px solid #313244; border-radius:6px;")
        self.setText("No screenshot yet.\nClick 'Capture Screenshot' to begin.")

    # --- public API ---

    def set_frame(self, bgr_array):
        self._orig_frame = bgr_array.copy()
        self._markers.clear()
        self._redraw()

    def add_marker(self, ox, oy):
        self._markers.append((ox, oy))
        self._redraw()

    def remove_last_marker(self):
        if self._markers:
            self._markers.pop()
            self._redraw()

    def clear_markers(self):
        self._markers.clear()
        self._redraw()

    # --- internal ---

    def _redraw(self):
        if self._orig_frame is None:
            return
        frame = self._orig_frame.copy()
        for i, (ox, oy) in enumerate(self._markers):
            cv2.circle(frame, (ox, oy), 10, (0, 0, 255), 2)
            cv2.putText(frame, str(i + 1), (ox + 12, oy - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 80, 255), 1, cv2.LINE_AA)
        h, w = frame.shape[:2]
        avail_w = max(self.width(), 480)
        avail_h = max(self.height(), 270)
        scale = min(avail_w / w, avail_h / h, 1.0)
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
        self._scale_x = dw / w
        self._scale_y = dh / h
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (dw, dh), interpolation=cv2.INTER_AREA)
        qi = QImage(resized.data, dw, dh, dw * 3, QImage.Format_RGB888)
        self.setPixmap(QPixmap.fromImage(qi))

    def mousePressEvent(self, event):
        if self._orig_frame is not None:
            ox = int(event.x() / self._scale_x)
            oy = int(event.y() / self._scale_y)
            h, w = self._orig_frame.shape[:2]
            ox = max(0, min(w - 1, ox))
            oy = max(0, min(h - 1, oy))
            self.add_marker(ox, oy)
            self.point_added.emit(ox, oy)
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        self._redraw()
        super().resizeEvent(event)


# ---------------------------------------------------------------------------
# Dark theme stylesheet
# ---------------------------------------------------------------------------

_DARK_STYLE = """
/* ═══════════════════════════════════════════════════
   Catppuccin Mocha — high-contrast, easy on the eyes
   ═══════════════════════════════════════════════════ */

/* ── Base ─────────────────────────────────────────── */
* { font-family: "Segoe UI", Arial, sans-serif; }
QWidget     { background: #1e1e2e; color: #cdd6f4; font-size: 10pt; }
QMainWindow { background: #181825; }
QDialog     { background: #1e1e2e; }
QMessageBox { background: #1e1e2e; }
QMessageBox QLabel { color: #cdd6f4; }

/* ── Tab bar — underline style ────────────────────── */
QTabWidget::pane { border: none; border-top: 1px solid #313244; background: #1e1e2e; }
QTabBar          { background: #181825; }
QTabBar::tab {
    background: transparent; color: #6c7086;
    padding: 11px 26px; border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px; font-weight: 500;
}
QTabBar::tab:selected        { color: #cdd6f4; border-bottom: 2px solid #89b4fa; }
QTabBar::tab:hover:!selected { color: #a6adc8; border-bottom: 2px solid #45475a; }

/* ── Buttons (default) ────────────────────────────── */
QPushButton {
    background: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 5px 10px; min-height: 28px; font-weight: 500;
}
QPushButton:hover   { background: #45475a; border-color: #89b4fa; color: #e6e9ef; }
QPushButton:pressed { background: #585b70; border-color: #89b4fa; color: #cdd6f4; }
QPushButton:disabled { background: #1e1e2e; color: #45475a; border-color: #313244; }

/* ── Primary button (Start Bot, Save) ─────────────── */
QPushButton#btn_primary {
    background: #89b4fa; color: #1e1e2e;
    border: none; border-radius: 6px; font-weight: 600;
}
QPushButton#btn_primary:hover   { background: #b4d0fb; color: #181825; }
QPushButton#btn_primary:pressed { background: #74a8f8; color: #1e1e2e; }
QPushButton#btn_primary:disabled { background: #313244; color: #6c7086; border: none; }

/* ── Danger button (Stop Bot) ─────────────────────── */
QPushButton#btn_danger {
    background: transparent; color: #f38ba8; border: 1px solid #7d2a3a;
}
QPushButton#btn_danger:hover   { background: #3d1420; border-color: #f38ba8; color: #f5a8bc; }
QPushButton#btn_danger:pressed { background: #7d2a3a; color: #f5c2e7; }
QPushButton#btn_danger:disabled { color: #6c7086; border-color: #313244; }

/* ── Inputs ───────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background: #181825; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 4px 10px; min-height: 28px;
    selection-background-color: #89b4fa; selection-color: #1e1e2e;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #89b4fa; background: #1e1e2e;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: #313244; border: none; width: 18px;
    border-left: 1px solid #45475a;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #45475a; }

/* ── ComboBox ─────────────────────────────────────── */
QComboBox {
    background: #181825; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 4px 10px; min-height: 28px;
    selection-background-color: #89b4fa; selection-color: #1e1e2e;
}
QComboBox:focus { border-color: #89b4fa; background: #1e1e2e; }
QComboBox::drop-down {
    background: #313244; border-left: 1px solid #45475a;
    width: 24px; border-radius: 0 6px 6px 0;
}
QComboBox QAbstractItemView {
    background: #181825; color: #cdd6f4;
    selection-background-color: #89b4fa; selection-color: #1e1e2e;
    border: 1px solid #45475a; outline: none; padding: 2px;
}
QComboBox QAbstractItemView::item { padding: 5px 8px; min-height: 26px; border-radius: 4px; }
QComboBox QAbstractItemView::item:selected { background: #89b4fa; color: #1e1e2e; }

/* ── Lists & Tables ───────────────────────────────── */
QListWidget, QTableWidget {
    background: #181825; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px;
    gridline-color: #313244; outline: none;
    alternate-background-color: #1e1e2e;
}
QListWidget::item { padding: 5px 8px; border-radius: 4px; margin: 1px 4px; }
QListWidget::item:selected        { background: #89b4fa; color: #1e1e2e; }
QListWidget::item:hover:!selected { background: #313244; }
QTableWidget::item:selected       { background: #89b4fa; color: #1e1e2e; }
QTableWidget::item:hover:!selected { background: #313244; }

/* ── Text areas (log) ─────────────────────────────── */
QTextEdit, QPlainTextEdit {
    background: #11111b; color: #bac2de;
    border: 1px solid #313244; border-radius: 6px;
    selection-background-color: #89b4fa; selection-color: #1e1e2e;
    padding: 4px;
}

/* ── Group boxes ──────────────────────────────────── */
QGroupBox {
    background: #181825; border: 1px solid #313244; border-radius: 8px;
    margin-top: 20px; padding: 14px 10px 10px 10px;
    font-weight: 600; color: #a6adc8;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 14px; padding: 2px 8px;
    color: #b4befe; background: #181825; border-radius: 4px;
}

/* ── Scroll bars ──────────────────────────────────── */
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical   { background: transparent; width: 8px;  margin: 0; border: none; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 0; border: none; }
QScrollBar::handle:vertical   { background: #45475a; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:horizontal { background: #45475a; border-radius: 4px; min-width:  24px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #89b4fa; }
QScrollBar::add-line:vertical,  QScrollBar::sub-line:vertical   { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:  0; }
QScrollBar::add-page:vertical,   QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

/* ── Splitter ─────────────────────────────────────── */
QSplitter::handle            { background: #313244; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical   { height: 1px; }

/* ── Table headers ────────────────────────────────── */
QHeaderView::section {
    background: #1e1e2e; color: #a6adc8;
    border: none; border-bottom: 1px solid #313244;
    border-right: 1px solid #313244;
    padding: 6px 8px; font-weight: 600;
}
QHeaderView { background: transparent; }

/* ── Checkboxes ───────────────────────────────────── */
QCheckBox { color: #cdd6f4; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1.5px solid #585b70; border-radius: 4px;
    background: #181825;
}
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QCheckBox::indicator:hover   { border-color: #89b4fa; }

/* ── Tooltips ─────────────────────────────────────── */
QToolTip {
    background: #313244; color: #cdd6f4;
    border: 1px solid #585b70; border-radius: 4px; padding: 6px 10px;
}

/* ── Labels ───────────────────────────────────────── */
QLabel { color: #cdd6f4; }
QFormLayout QLabel { color: #a6adc8; }
"""


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CoC Bot")
        self.resize(1200, 780)
        self._bot_thread = None
        self._macro_points = []
        self._slots_data = []
        self._current_deploy_row = -1
        self._current_scenario = None

        tabs = QTabWidget()
        tabs.addTab(self._build_control_tab(),    "Control")
        tabs.addTab(self._build_attack_tab(),     "Attack")
        tabs.addTab(self._build_scenarios_tab(),  "Troops")
        tabs.addTab(self._build_macro_tab(),      "Recorder")
        tabs.addTab(self._build_device_tab(),     "Device")
        self.setCentralWidget(tabs)

    # -----------------------------------------------------------------------
    # Tab 1 — Control
    # -----------------------------------------------------------------------

    _LOG_MAX_LINES = 500

    _CAT_PATTERNS = {
        "Troops":       ("units/troops/*.png",),
        "Super Troops": ("units/super_troops/*.png",),
        "Heroes":       ("units/heroes/*.png",),
        "Spells":       ("units/spells/*.png",),
        "Siege":        ("units/siege/*.png",),
        "Clan Capital": ("clan_capital/**/*.png",),
    }
    _FOLDER_TO_CAT = {
        "troops":       "Troops",
        "super_troops": "Super Troops",
        "heroes":       "Heroes",
        "spells":       "Spells",
        "siege":        "Siege",
    }

    def _build_control_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._btn_start = QPushButton("▶  Start Bot")
        self._btn_start.setObjectName("btn_primary")
        self._btn_start.setMinimumWidth(120)
        self._btn_stop  = QPushButton("■  Stop")
        self._btn_stop.setObjectName("btn_danger")
        self._btn_stop.setEnabled(False)
        btn_clear_log = QPushButton("Clear Log")
        self._status_lbl = QLabel("● Stopped")
        self._status_lbl.setStyleSheet("color:#6c7086; font-weight:600;")

        self._log_level_cb = QComboBox()
        self._log_level_cb.addItems(["All", "INFO+", "WARNING+"])
        self._log_level_cb.setFixedWidth(100)

        toolbar.addWidget(self._btn_start)
        toolbar.addWidget(self._btn_stop)
        toolbar.addSpacing(16)
        toolbar.addWidget(self._status_lbl)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("Show:"))
        toolbar.addWidget(self._log_level_cb)
        toolbar.addWidget(btn_clear_log)
        v.addLayout(toolbar)

        _actions = load_settings().get("actions", {})
        grp_act = QGroupBox("Bot Actions")
        ah = QHBoxLayout(grp_act)
        ah.setSpacing(14)
        self._act_collect = QCheckBox("Collect Resources")
        self._act_collect.setChecked(_actions.get("collect_resources", True))
        self._act_farm = QCheckBox("Farm Attack")
        self._act_farm.setChecked(_actions.get("farm_attack", True))
        _cb_troops = QCheckBox("Clan Troops  (soon)")
        _cb_troops.setEnabled(False)
        _cb_games  = QCheckBox("Clan Games  (soon)")
        _cb_games.setEnabled(False)
        _btn_save_act = QPushButton("Save")
        _btn_save_act.clicked.connect(self._save_actions)
        ah.addWidget(self._act_collect)
        ah.addWidget(self._act_farm)
        ah.addSpacing(8)
        ah.addWidget(_cb_troops)
        ah.addWidget(_cb_games)
        ah.addStretch()
        ah.addWidget(_btn_save_act)
        v.addWidget(grp_act)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Consolas", 9))
        v.addWidget(self._log_view)

        self._btn_start.clicked.connect(self._start_bot)
        self._btn_stop.clicked.connect(self._stop_bot)
        btn_clear_log.clicked.connect(self._log_view.clear)
        return w

    def _start_bot(self):
        if self._bot_thread and self._bot_thread.isRunning():
            return
        self._log_view.clear()
        self._btn_start.setEnabled(False)
        self._bot_thread = BotThread()
        self._bot_thread.log_line.connect(self._append_log)
        self._bot_thread.status.connect(self._on_bot_status)
        self._bot_thread.start()
        self._btn_stop.setEnabled(True)

    def _stop_bot(self):
        if self._bot_thread:
            self._bot_thread.request_stop()
            self._btn_stop.setEnabled(False)

    def _append_log(self, level, msg):
        # Level filter
        filter_text = self._log_level_cb.currentText()
        if filter_text == "INFO+" and level == "DEBUG":
            return
        if filter_text == "WARNING+" and level not in ("WARNING", "ERROR", "CRITICAL"):
            return

        color = {"ERROR": "#f38ba8", "WARNING": "#f9e2af", "DEBUG": "#585b70"}.get(level, "#bac2de")
        self._log_view.append(f'<span style="color:{color};">{_html.escape(msg)}</span>')
        self._log_view.moveCursor(QTextCursor.End)

        # Trim oldest lines when the log grows too long
        doc = self._log_view.document()
        while doc.blockCount() > self._LOG_MAX_LINES:
            cursor = QTextCursor(doc.begin())
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

    def _on_bot_status(self, status):
        if status == "running":
            self._status_lbl.setText("● Running")
            self._status_lbl.setStyleSheet("color:#a6e3a1; font-weight:600;")
        elif status == "stopped":
            self._status_lbl.setText("● Stopped")
            self._status_lbl.setStyleSheet("color:#6c7086; font-weight:600;")
            self._btn_start.setEnabled(True)
            self._btn_stop.setEnabled(False)
        elif status.startswith("error:"):
            self._status_lbl.setText(f"● Error: {status[6:][:70]}")
            self._status_lbl.setStyleSheet("color:#f38ba8; font-weight:600;")
            self._btn_start.setEnabled(True)
            self._btn_stop.setEnabled(False)

    def _save_actions(self):
        s = load_settings()
        s.setdefault("actions", {})
        s["actions"]["collect_resources"]   = self._act_collect.isChecked()
        s["actions"]["farm_attack"]         = self._act_farm.isChecked()
        s["actions"]["request_clan_troops"] = False
        s["actions"]["clan_games"]          = False
        save_settings(s)
        QMessageBox.information(self, "Saved", "Action settings saved.")

    # -----------------------------------------------------------------------
    # Tab 3 — Device
    # -----------------------------------------------------------------------

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

        # ── Save ─────────────────────────────────────────────────────────────
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

    # -----------------------------------------------------------------------
    # Tab 4 — Attack
    # -----------------------------------------------------------------------

    def _build_attack_tab(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(14)
        v.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

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
        v.addWidget(grp_loot)

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
        v.addWidget(grp_scen)

        # ── Deploy Settings ──────────────────────────────────────────────────
        grp_dep = QGroupBox("Deploy Settings")
        df = QFormLayout(grp_dep)
        df.setSpacing(10)
        df.setLabelAlignment(Qt.AlignRight)

        bar = deploy.get("troop_bar_region", [0, 730, 1600, 910])
        self._atk_bar_x1 = QSpinBox(); self._atk_bar_x1.setRange(0, 3000); self._atk_bar_x1.setValue(int(bar[0]))
        self._atk_bar_y1 = QSpinBox(); self._atk_bar_y1.setRange(0, 3000); self._atk_bar_y1.setValue(int(bar[1]))
        self._atk_bar_x2 = QSpinBox(); self._atk_bar_x2.setRange(0, 3000); self._atk_bar_x2.setValue(int(bar[2]))
        self._atk_bar_y2 = QSpinBox(); self._atk_bar_y2.setRange(0, 3000); self._atk_bar_y2.setValue(int(bar[3]))

        bar_row1 = QWidget()
        br1 = QHBoxLayout(bar_row1); br1.setContentsMargins(0, 0, 0, 0); br1.setSpacing(6)
        br1.addWidget(QLabel("x1")); br1.addWidget(self._atk_bar_x1)
        br1.addWidget(QLabel("y1")); br1.addWidget(self._atk_bar_y1)
        bar_row2 = QWidget()
        br2 = QHBoxLayout(bar_row2); br2.setContentsMargins(0, 0, 0, 0); br2.setSpacing(6)
        br2.addWidget(QLabel("x2")); br2.addWidget(self._atk_bar_x2)
        br2.addWidget(QLabel("y2")); br2.addWidget(self._atk_bar_y2)
        df.addRow("Bar region (top)", bar_row1)
        df.addRow("Bar region (bot)", bar_row2)

        self._atk_tap_interval = dspin(0.0, 5.0, deploy.get("tap_interval", 0.15), dec=2)
        df.addRow("Tap interval (s)", self._atk_tap_interval)
        v.addWidget(grp_dep)

        btn_save = QPushButton("Save")
        btn_save.setObjectName("btn_primary")
        btn_save.clicked.connect(self._save_attack)
        v.addWidget(btn_save)
        v.addStretch()
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

    # -----------------------------------------------------------------------
    # Tab 5 — Troops (scenario editor)
    # -----------------------------------------------------------------------

    def _build_scenarios_tab(self):
        w = QWidget()
        root = QHBoxLayout(w)

        # --- Scenario list panel ---
        sc_panel = QWidget()
        sc_panel.setFixedWidth(200)
        sv = QVBoxLayout(sc_panel)
        sv.addWidget(QLabel("Scenarios"))
        self._scenario_list = QListWidget()
        self._scenario_list.currentRowChanged.connect(self._on_scenario_selected)
        sv.addWidget(self._scenario_list)
        sc_btns = QHBoxLayout()
        btn_sc_new = QPushButton("+ New")
        btn_sc_ren = QPushButton("Rename")
        btn_sc_del = QPushButton("Delete")
        for b in (btn_sc_new, btn_sc_ren, btn_sc_del):
            sc_btns.addWidget(b)
        sv.addLayout(sc_btns)
        btn_sc_active = QPushButton("★ Set Active")
        sv.addWidget(btn_sc_active)

        # --- Slot list panel ---
        slot_panel = QWidget()
        slot_panel.setFixedWidth(200)
        lv = QVBoxLayout(slot_panel)
        lv.addWidget(QLabel("Slots  (deploy order)"))
        self._slot_list = QListWidget()
        self._slot_list.currentRowChanged.connect(self._on_slot_selected)
        lv.addWidget(self._slot_list)
        btn_row = QHBoxLayout()
        btn_add = QPushButton("+")
        btn_rm  = QPushButton("−")
        btn_up  = QPushButton("↑")
        btn_dn  = QPushButton("↓")
        for b in (btn_add, btn_rm, btn_up, btn_dn):
            b.setFixedWidth(40)
            btn_row.addWidget(b)
        lv.addLayout(btn_row)
        btn_save_d = QPushButton("Save")
        lv.addWidget(btn_save_d)

        # --- Slot editor form ---
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setAlignment(Qt.AlignTop)
        rv.addWidget(QLabel("Edit Selected Slot"))

        # Strategy always visible
        strat_form = QFormLayout()
        self._d_strategy = QComboBox()
        self._d_strategy.addItems(["line", "points", "delay"])
        strat_form.addRow("Strategy", self._d_strategy)
        rv.addLayout(strat_form)

        # Troop-specific fields — hidden when strategy == "delay"
        self._d_troop_fields = QWidget()
        form = QFormLayout(self._d_troop_fields)
        form.setContentsMargins(0, 0, 0, 0)

        self._d_cat_cb = QComboBox()
        self._d_cat_cb.addItems(list(self._CAT_PATTERNS))
        form.addRow("Category", self._d_cat_cb)

        self._d_tmpl_cb  = QComboBox()
        self._d_thumb    = QLabel()
        self._d_thumb.setFixedSize(48, 48)
        self._d_thumb.setStyleSheet("border:1px solid #313244; background:#181825; border-radius:4px;")
        tmpl_h = QHBoxLayout()
        tmpl_h.addWidget(self._d_tmpl_cb)
        tmpl_h.addWidget(self._d_thumb)
        form.addRow("Template", tmpl_h)

        self._d_taps = QSpinBox(); self._d_taps.setRange(1, 200)
        form.addRow("Taps", self._d_taps)

        self._d_bar_x = QSpinBox(); self._d_bar_x.setRange(0, 3000)
        self._d_bar_y = QSpinBox(); self._d_bar_y.setRange(0, 3000)
        form.addRow("Bar X  (0 = auto)", self._d_bar_x)
        form.addRow("Bar Y  (0 = auto)", self._d_bar_y)

        rv.addWidget(self._d_troop_fields)

        self._d_line_grp = QGroupBox("Line deployment  (start → end, any direction)")
        lg = QFormLayout(self._d_line_grp)
        self._d_x1 = QSpinBox(); self._d_x1.setRange(0, 3000); self._d_x1.setValue(300)
        self._d_y1 = QSpinBox(); self._d_y1.setRange(0, 3000); self._d_y1.setValue(760)
        self._d_x2 = QSpinBox(); self._d_x2.setRange(0, 3000); self._d_x2.setValue(1300)
        self._d_y2 = QSpinBox(); self._d_y2.setRange(0, 3000); self._d_y2.setValue(760)
        lg.addRow("Start X", self._d_x1)
        lg.addRow("Start Y", self._d_y1)
        lg.addRow("End X",   self._d_x2)
        lg.addRow("End Y",   self._d_y2)
        rv.addWidget(self._d_line_grp)

        self._d_pts_grp = QGroupBox("Points deployment")
        pg = QVBoxLayout(self._d_pts_grp)
        self._d_pts_tbl = QTableWidget(0, 2)
        self._d_pts_tbl.setHorizontalHeaderLabels(["X", "Y"])
        self._d_pts_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._d_pts_tbl.setFixedHeight(150)
        pg.addWidget(self._d_pts_tbl)
        pts_btn = QHBoxLayout()
        btn_pt_add = QPushButton("+ Row")
        btn_pt_rm  = QPushButton("− Row")
        pts_btn.addWidget(btn_pt_add); pts_btn.addWidget(btn_pt_rm)
        pg.addLayout(pts_btn)
        rv.addWidget(self._d_pts_grp)
        self._d_pts_grp.hide()

        self._d_delay_grp = QGroupBox("Delay")
        dg = QFormLayout(self._d_delay_grp)
        self._d_delay_secs = QSpinBox()
        self._d_delay_secs.setRange(1, 120)
        self._d_delay_secs.setValue(1)
        dg.addRow("Seconds", self._d_delay_secs)
        rv.addWidget(self._d_delay_grp)
        self._d_delay_grp.hide()

        root.addWidget(sc_panel)
        root.addWidget(slot_panel)
        root.addWidget(right)

        self._fill_template_combo(self._d_tmpl_cb, "Troops")
        self._d_cat_cb.currentTextChanged.connect(
            lambda cat: self._on_cat_changed(cat, self._d_tmpl_cb, self._d_thumb))
        self._d_tmpl_cb.currentIndexChanged.connect(
            lambda: self._update_thumb(self._d_tmpl_cb, self._d_thumb))
        self._d_tmpl_cb.activated.connect(
            lambda _: self._update_slot_label())
        self._d_strategy.currentTextChanged.connect(self._toggle_deploy_strategy)

        btn_sc_new.clicked.connect(self._scenario_new)
        btn_sc_ren.clicked.connect(self._scenario_rename)
        btn_sc_del.clicked.connect(self._scenario_delete)
        btn_sc_active.clicked.connect(self._scenario_set_active)
        btn_add.clicked.connect(self._deploy_add_slot)
        btn_rm.clicked.connect(self._deploy_rm_slot)
        btn_up.clicked.connect(self._deploy_move_up)
        btn_dn.clicked.connect(self._deploy_move_dn)
        btn_save_d.clicked.connect(self._scenario_save)
        btn_pt_add.clicked.connect(
            lambda: self._d_pts_tbl.insertRow(self._d_pts_tbl.rowCount()))
        btn_pt_rm.clicked.connect(self._deploy_rm_pt_row)

        self._refresh_scenario_list()
        return w

    def _refresh_scenario_list(self):
        s = load_settings()
        active = s.get("attack", {}).get("deploy", {}).get("active_scenario")
        self._scenario_list.blockSignals(True)
        self._scenario_list.clear()
        for name in list_scenarios():
            self._scenario_list.addItem(f"★ {name}" if name == active else f"  {name}")
        self._scenario_list.blockSignals(False)
        if self._current_scenario:
            names = list_scenarios()
            if self._current_scenario in names:
                self._scenario_list.setCurrentRow(names.index(self._current_scenario))

    def _on_scenario_selected(self, row):
        if self._current_scenario:
            if 0 <= self._current_deploy_row < len(self._slots_data):
                self._collect_slot(self._current_deploy_row)
            save_scenario(self._current_scenario, self._slots_data)
        names = list_scenarios()
        if row < 0 or row >= len(names):
            self._current_scenario = None
            self._slots_data = []
            self._refresh_slot_list()
            return
        self._current_scenario = names[row]
        self._current_deploy_row = -1
        self._load_deploy_slots()

    def _scenario_new(self):
        name, ok = QInputDialog.getText(self, "New Scenario", "Scenario name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        save_scenario(name, [])
        self._current_scenario = name
        self._refresh_scenario_list()
        self._load_deploy_slots()

    def _scenario_rename(self):
        if not self._current_scenario:
            return
        new_name, ok = QInputDialog.getText(self, "Rename Scenario",
                                            "New name:", text=self._current_scenario)
        if not ok or not new_name.strip() or new_name.strip() == self._current_scenario:
            return
        new_name = new_name.strip()
        rename_scenario(self._current_scenario, new_name)
        s = load_settings()
        if s.get("attack", {}).get("deploy", {}).get("active_scenario") == self._current_scenario:
            s["attack"]["deploy"]["active_scenario"] = new_name
            save_settings(s)
        self._current_scenario = new_name
        self._refresh_scenario_list()

    def _scenario_delete(self):
        if not self._current_scenario:
            return
        reply = QMessageBox.question(self, "Delete Scenario",
                                     f"Delete '{self._current_scenario}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        delete_scenario(self._current_scenario)
        s = load_settings()
        if s.get("attack", {}).get("deploy", {}).get("active_scenario") == self._current_scenario:
            s["attack"]["deploy"]["active_scenario"] = None
            save_settings(s)
        self._current_scenario = None
        self._slots_data = []
        self._refresh_slot_list()
        self._refresh_scenario_list()

    def _scenario_set_active(self):
        if not self._current_scenario:
            return
        s = load_settings()
        s["attack"]["deploy"]["active_scenario"] = self._current_scenario
        save_settings(s)
        self._refresh_scenario_list()
        QMessageBox.information(self, "Active",
                                f"'{self._current_scenario}' set as active scenario.")

    def _toggle_deploy_strategy(self, strategy):
        self._d_troop_fields.setVisible(strategy != "delay")
        self._d_line_grp.setVisible(strategy == "line")
        self._d_pts_grp.setVisible(strategy == "points")
        self._d_delay_grp.setVisible(strategy == "delay")

    def _fill_template_combo(self, combo, category="Troops"):
        combo.clear()
        assets = Path(ASSETS_PATH)
        for pattern in self._CAT_PATTERNS.get(category, ("units/**/*.png",)):
            for p in sorted(assets.glob(pattern)):
                rel = p.relative_to(assets).with_suffix("").as_posix()
                combo.addItem(p.stem, rel)

    def _on_cat_changed(self, cat, combo, thumb):
        self._fill_template_combo(combo, cat)
        self._update_thumb(combo, thumb)

    def _cat_from_rel(self, rel):
        parts = rel.split("/")
        if parts and parts[0] == "clan_capital":
            return "Clan Capital"
        if len(parts) >= 2:
            return self._FOLDER_TO_CAT.get(parts[1], "Troops")
        return "Troops"

    def _update_thumb(self, combo, lbl):
        rel = combo.currentData()
        if not rel:
            return
        path = str(Path(ASSETS_PATH) / (rel + ".png"))
        img = cv2.imread(path)
        if img is None:
            lbl.clear()
            return
        h, w = img.shape[:2]
        scale = min(48 / w, 48 / h)
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
        rgb = cv2.cvtColor(cv2.resize(img, (dw, dh)), cv2.COLOR_BGR2RGB)
        qi = QImage(rgb.data, dw, dh, dw * 3, QImage.Format_RGB888)
        lbl.setPixmap(QPixmap.fromImage(qi))

    def _load_deploy_slots(self):
        if not self._current_scenario:
            self._slots_data = []
            self._refresh_slot_list()
            return
        try:
            self._slots_data = list(load_scenario(self._current_scenario).get("slots", []))
        except FileNotFoundError:
            self._slots_data = []
        self._refresh_slot_list()

    def _update_slot_label(self):
        row = self._current_deploy_row
        item = self._slot_list.item(row)
        if item is None:
            return
        rel = self._d_tmpl_cb.currentData() or "?"
        item.setText(rel.split("/")[-1] if "/" in rel else rel)

    def _refresh_slot_list(self):
        self._slot_list.blockSignals(True)
        self._slot_list.clear()
        for slot in self._slots_data:
            if slot.get("strategy") == "delay":
                self._slot_list.addItem(f"wait {slot.get('seconds', 1)}s")
            else:
                key = slot.get("template", "?")
                self._slot_list.addItem(key.split("/")[-1] if "/" in key else key)
        self._slot_list.blockSignals(False)

    def _on_slot_selected(self, row):
        if 0 <= self._current_deploy_row < len(self._slots_data):
            self._collect_slot(self._current_deploy_row)
        self._current_deploy_row = row
        if row < 0 or row >= len(self._slots_data):
            return
        slot = self._slots_data[row]
        strategy = slot.get("strategy", "line")
        self._d_strategy.setCurrentText(strategy)   # triggers _toggle_deploy_strategy

        if strategy == "delay":
            self._d_delay_secs.setValue(int(slot.get("seconds", 1)))
            return

        rel = slot.get("template", "")
        cat = self._cat_from_rel(rel)
        self._d_cat_cb.blockSignals(True)
        self._d_cat_cb.setCurrentText(cat)
        self._d_cat_cb.blockSignals(False)
        self._fill_template_combo(self._d_tmpl_cb, cat)
        idx = self._d_tmpl_cb.findData(rel)
        if idx >= 0:
            self._d_tmpl_cb.setCurrentIndex(idx)

        self._d_taps.setValue(slot.get("taps", 5))
        self._d_bar_x.setValue(slot.get("bar_x", 0))
        self._d_bar_y.setValue(slot.get("bar_y", 0))
        old_y = slot.get("y", 760)
        self._d_x1.setValue(slot.get("x1", slot.get("x_start", 300)))
        self._d_y1.setValue(slot.get("y1", old_y))
        self._d_x2.setValue(slot.get("x2", slot.get("x_end", 1300)))
        self._d_y2.setValue(slot.get("y2", old_y))
        self._d_pts_tbl.setRowCount(0)
        for pt in slot.get("points", []):
            r = self._d_pts_tbl.rowCount()
            self._d_pts_tbl.insertRow(r)
            self._d_pts_tbl.setItem(r, 0, QTableWidgetItem(str(pt[0])))
            self._d_pts_tbl.setItem(r, 1, QTableWidgetItem(str(pt[1])))

    def _collect_slot(self, row):
        if row < 0 or row >= len(self._slots_data):
            return
        slot = self._slots_data[row]
        slot["template"] = self._d_tmpl_cb.currentData() or ""
        slot["taps"]     = self._d_taps.value()
        slot["strategy"] = self._d_strategy.currentText()
        bx = self._d_bar_x.value()
        by = self._d_bar_y.value()
        if bx:
            slot["bar_x"] = bx
        else:
            slot.pop("bar_x", None)
        if by:
            slot["bar_y"] = by
        else:
            slot.pop("bar_y", None)
        if slot["strategy"] == "delay":
            slot["seconds"] = int(self._d_delay_secs.value())
            for k in ("template", "taps", "bar_x", "bar_y",
                      "x1", "y1", "x2", "y2", "x_start", "x_end", "y", "points"):
                slot.pop(k, None)
        elif slot["strategy"] == "line":
            slot["x1"] = self._d_x1.value()
            slot["y1"] = self._d_y1.value()
            slot["x2"] = self._d_x2.value()
            slot["y2"] = self._d_y2.value()
            for k in ("x_start", "x_end", "y", "points", "seconds"):
                slot.pop(k, None)
        else:
            pts = []
            for r in range(self._d_pts_tbl.rowCount()):
                xi = self._d_pts_tbl.item(r, 0)
                yi = self._d_pts_tbl.item(r, 1)
                if xi and yi:
                    try:
                        pts.append([int(xi.text()), int(yi.text())])
                    except ValueError:
                        pass
            slot["points"] = pts
            for k in ("y", "x_start", "x_end", "seconds"):
                slot.pop(k, None)

    def _deploy_add_slot(self):
        self._slots_data.append({
            "template": "units/troops/barbarian",
            "taps": 5, "strategy": "line",
            "x1": 300, "y1": 760, "x2": 1300, "y2": 760,
        })
        self._refresh_slot_list()
        self._slot_list.setCurrentRow(len(self._slots_data) - 1)

    def _deploy_rm_slot(self):
        row = self._slot_list.currentRow()
        if 0 <= row < len(self._slots_data):
            self._slots_data.pop(row)
            self._current_deploy_row = -1
            self._refresh_slot_list()

    def _deploy_move_up(self):
        row = self._slot_list.currentRow()
        if row > 0:
            self._slots_data[row], self._slots_data[row - 1] = \
                self._slots_data[row - 1], self._slots_data[row]
            self._current_deploy_row = row - 1
            self._refresh_slot_list()
            self._slot_list.setCurrentRow(row - 1)

    def _deploy_move_dn(self):
        row = self._slot_list.currentRow()
        if 0 <= row < len(self._slots_data) - 1:
            self._slots_data[row], self._slots_data[row + 1] = \
                self._slots_data[row + 1], self._slots_data[row]
            self._current_deploy_row = row + 1
            self._refresh_slot_list()
            self._slot_list.setCurrentRow(row + 1)

    def _deploy_rm_pt_row(self):
        row = self._d_pts_tbl.currentRow()
        if row >= 0:
            self._d_pts_tbl.removeRow(row)

    def _scenario_save(self):
        if not self._current_scenario:
            QMessageBox.warning(self, "No Scenario", "Select or create a scenario first.")
            return
        if 0 <= self._current_deploy_row < len(self._slots_data):
            self._collect_slot(self._current_deploy_row)
        save_scenario(self._current_scenario, self._slots_data)
        self._refresh_slot_list()
        QMessageBox.information(self, "Saved", f"Scenario '{self._current_scenario}' saved.")

    # -----------------------------------------------------------------------
    # Tab 4 — Macro Recorder
    # -----------------------------------------------------------------------

    def _build_macro_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        # Top bar
        top = QHBoxLayout()
        btn_cap = QPushButton("Capture Screenshot")
        self._m_res_lbl = QLabel("No screenshot captured")
        top.addWidget(btn_cap)
        top.addWidget(self._m_res_lbl)
        top.addStretch()
        v.addLayout(top)

        # Splitter: image | controls
        splitter = QSplitter(Qt.Horizontal)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._m_img = ClickableImageLabel()
        self._m_img.point_added.connect(self._macro_on_click)
        scroll.setWidget(self._m_img)
        splitter.addWidget(scroll)

        # Right controls
        right = QWidget()
        right.setMinimumWidth(230)
        right.setMaximumWidth(290)
        rv = QVBoxLayout(right)

        rv.addWidget(QLabel("Recorded Points"))
        self._m_pts_list = QListWidget()
        rv.addWidget(self._m_pts_list)

        btn_rm_last = QPushButton("Remove Last")
        btn_clear   = QPushButton("Clear All")
        rv.addWidget(btn_rm_last)
        rv.addWidget(btn_clear)

        rv.addSpacing(12)
        rv.addWidget(QLabel("Save as Slot"))
        form = QFormLayout()

        self._m_cat_cb = QComboBox()
        self._m_cat_cb.addItems(list(self._CAT_PATTERNS))
        form.addRow("Category", self._m_cat_cb)

        self._m_tmpl_cb = QComboBox()
        self._m_thumb   = QLabel()
        self._m_thumb.setFixedSize(48, 48)
        self._m_thumb.setStyleSheet("border:1px solid #313244; background:#181825; border-radius:4px;")
        tmpl_h = QHBoxLayout()
        tmpl_h.addWidget(self._m_tmpl_cb)
        tmpl_h.addWidget(self._m_thumb)
        form.addRow("Template", tmpl_h)

        self._m_taps = QSpinBox()
        self._m_taps.setRange(1, 200)
        self._m_taps.setValue(1)
        form.addRow("Taps", self._m_taps)
        rv.addLayout(form)

        btn_add_pts  = QPushButton("Save as Points")
        btn_add_line = QPushButton("Save as Line")
        rv.addWidget(btn_add_pts)
        rv.addWidget(btn_add_line)
        rv.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([820, 280])
        v.addWidget(splitter)

        # Wire
        self._fill_template_combo(self._m_tmpl_cb, "Troops")
        self._m_cat_cb.currentTextChanged.connect(
            lambda cat: self._on_cat_changed(cat, self._m_tmpl_cb, self._m_thumb))
        self._m_tmpl_cb.currentIndexChanged.connect(
            lambda: self._update_thumb(self._m_tmpl_cb, self._m_thumb))
        btn_cap.clicked.connect(self._macro_capture)
        btn_rm_last.clicked.connect(self._macro_rm_last)
        btn_clear.clicked.connect(self._macro_clear)
        btn_add_pts.clicked.connect(self._macro_save_slot)
        btn_add_line.clicked.connect(self._macro_save_line)
        return w

    def _macro_capture(self):
        self._m_res_lbl.setText("Connecting to device…")
        s = load_settings()
        worker = ScreenshotWorker(s)
        worker.signals.done.connect(self._macro_on_frame)
        worker.signals.error.connect(self._macro_on_error)
        QThreadPool.globalInstance().start(worker)

    def _macro_on_frame(self, frame):
        h, w = frame.shape[:2]
        self._m_res_lbl.setText(f"Resolution: {w}×{h}  — click to record taps")
        self._macro_points.clear()
        self._m_pts_list.clear()
        self._m_taps.setValue(1)
        self._m_img.set_frame(frame)

    def _macro_on_error(self, msg):
        self._m_res_lbl.setText(f"Error: {msg}")
        QMessageBox.warning(self, "Screenshot Error", msg)

    def _macro_on_click(self, x, y):
        self._macro_points.append((x, y))
        idx = len(self._macro_points)
        self._m_pts_list.addItem(f"{idx}.  ({x}, {y})")
        self._m_taps.setValue(idx)

    def _macro_rm_last(self):
        if self._macro_points:
            self._macro_points.pop()
            self._m_pts_list.takeItem(self._m_pts_list.count() - 1)
            self._m_img.remove_last_marker()
            self._m_taps.setValue(max(1, len(self._macro_points)))

    def _macro_clear(self):
        self._macro_points.clear()
        self._m_pts_list.clear()
        self._m_img.clear_markers()
        self._m_taps.setValue(1)

    def _macro_save_slot(self):
        if not self._macro_points:
            QMessageBox.warning(self, "No Points",
                                "Record at least one tap point before saving.")
            return
        if not self._current_scenario:
            QMessageBox.warning(self, "No Scenario",
                                "Select or create a scenario in the Scenarios tab first.")
            return
        rel  = self._m_tmpl_cb.currentData() or ""
        taps = self._m_taps.value()
        slot = {
            "template": rel,
            "taps": taps,
            "strategy": "points",
            "points": [[x, y] for x, y in self._macro_points],
        }
        self._slots_data.append(slot)
        save_scenario(self._current_scenario, self._slots_data)
        self._refresh_slot_list()
        name = rel.split("/")[-1] if "/" in rel else rel
        QMessageBox.information(self, "Added",
                                f"Slot '{name}' added to scenario '{self._current_scenario}'.")

    def _macro_save_line(self):
        if len(self._macro_points) < 2:
            QMessageBox.warning(self, "Need 2 Points",
                                "Record exactly 2 points (start and end of the line).")
            return
        if not self._current_scenario:
            QMessageBox.warning(self, "No Scenario",
                                "Select or create a scenario in the Scenarios tab first.")
            return
        rel  = self._m_tmpl_cb.currentData() or ""
        taps = self._m_taps.value()
        x1, y1 = self._macro_points[0]
        x2, y2 = self._macro_points[-1]
        slot = {
            "template": rel,
            "taps": taps,
            "strategy": "line",
            "x1": x1, "y1": y1,
            "x2": x2, "y2": y2,
        }
        self._slots_data.append(slot)
        save_scenario(self._current_scenario, self._slots_data)
        self._refresh_slot_list()
        name = rel.split("/")[-1] if "/" in rel else rel
        QMessageBox.information(self, "Added",
                                f"Line slot '{name}' ({x1},{y1})→({x2},{y2}) added.")


# ---------------------------------------------------------------------------
# Windows dark title bar
# ---------------------------------------------------------------------------

def _apply_dark_titlebar(hwnd: int) -> None:
    """Enable dark mode for the native Win32 title bar (Windows 10 19041+ / 11)."""
    try:
        import ctypes
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(_DARK_STYLE)
    win = MainWindow()
    win.show()
    _apply_dark_titlebar(int(win.winId()))
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
