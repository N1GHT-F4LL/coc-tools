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
    QHeaderView, QMessageBox, QSizePolicy,
)
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
        self.setStyleSheet("background:#1a1a2e; border:1px solid #444;")
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
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CoC Bot")
        self.resize(1150, 720)
        self._bot_thread = None
        self._macro_points = []
        self._slots_data = []
        self._current_deploy_row = -1

        tabs = QTabWidget()
        tabs.addTab(self._build_control_tab(),  "Control")
        tabs.addTab(self._build_farm_tab(),      "Farm Settings")
        tabs.addTab(self._build_deploy_tab(),    "Deploy Config")
        tabs.addTab(self._build_macro_tab(),     "Macro Recorder")
        self.setCentralWidget(tabs)

    # -----------------------------------------------------------------------
    # Tab 1 — Control
    # -----------------------------------------------------------------------

    _LOG_MAX_LINES = 500

    def _build_control_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        toolbar = QHBoxLayout()
        self._btn_start = QPushButton("▶  Start Bot")
        self._btn_stop  = QPushButton("■  Stop Bot")
        self._btn_stop.setEnabled(False)
        btn_clear_log = QPushButton("Clear Log")
        self._status_lbl = QLabel("● Stopped")
        self._status_lbl.setStyleSheet("color:#aaa; font-weight:bold;")

        # Log-level filter
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

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Consolas", 9))
        self._log_view.setStyleSheet("background:#111; color:#ccc;")
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

        color = {"ERROR": "#f55", "WARNING": "#fa0", "DEBUG": "#777"}.get(level, "#ccc")
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
            self._status_lbl.setStyleSheet("color:#4f4; font-weight:bold;")
        elif status == "stopped":
            self._status_lbl.setText("● Stopped")
            self._status_lbl.setStyleSheet("color:#aaa; font-weight:bold;")
            self._btn_start.setEnabled(True)
            self._btn_stop.setEnabled(False)
        elif status.startswith("error:"):
            self._status_lbl.setText(f"● Error: {status[6:][:70]}")
            self._status_lbl.setStyleSheet("color:#f55; font-weight:bold;")
            self._btn_start.setEnabled(True)
            self._btn_stop.setEnabled(False)

    # -----------------------------------------------------------------------
    # Tab 2 — Farm Settings
    # -----------------------------------------------------------------------

    def _build_farm_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignTop)

        s = load_settings()
        farm   = s.get("farm", {})
        delays = s.get("delays", {})
        jitter = s.get("jitter", {})

        form = QFormLayout()

        def spin(lo, hi, val):
            sb = QSpinBox()
            sb.setRange(lo, hi)
            sb.setValue(val)
            return sb

        def dspin(lo, hi, val, dec=2):
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setDecimals(dec)
            sb.setValue(val)
            return sb

        self._spin_gold   = spin(0, 9_999_999, farm.get("min_gold", 500_000))
        self._spin_elixir = spin(0, 9_999_999, farm.get("min_elixir", 500_000))
        self._spin_dark   = spin(0, 99_999,    farm.get("min_dark_elixir", 500))
        form.addRow("Min Gold",        self._spin_gold)
        form.addRow("Min Elixir",      self._spin_elixir)
        form.addRow("Min Dark Elixir", self._spin_dark)

        self._spin_s_min = dspin(0, 60, delays.get("short_min", 0.5))
        self._spin_s_max = dspin(0, 60, delays.get("short_max", 1.5))
        self._spin_l_min = dspin(0, 120, delays.get("long_min", 2.0))
        self._spin_l_max = dspin(0, 120, delays.get("long_max", 4.0))
        self._spin_jitter = dspin(0, 100, jitter.get("radius", 5), dec=1)
        form.addRow("Short delay min (s)", self._spin_s_min)
        form.addRow("Short delay max (s)", self._spin_s_max)
        form.addRow("Long delay min (s)",  self._spin_l_min)
        form.addRow("Long delay max (s)",  self._spin_l_max)
        form.addRow("Jitter radius (px)",  self._spin_jitter)

        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self._save_farm)

        v.addLayout(form)
        v.addSpacing(12)
        v.addWidget(btn_save)
        return w

    def _save_farm(self):
        s = load_settings()
        s["farm"]["min_gold"]        = self._spin_gold.value()
        s["farm"]["min_elixir"]      = self._spin_elixir.value()
        s["farm"]["min_dark_elixir"] = self._spin_dark.value()
        s["delays"]["short_min"]     = self._spin_s_min.value()
        s["delays"]["short_max"]     = self._spin_s_max.value()
        s["delays"]["long_min"]      = self._spin_l_min.value()
        s["delays"]["long_max"]      = self._spin_l_max.value()
        s["jitter"]["radius"]        = self._spin_jitter.value()
        save_settings(s)
        QMessageBox.information(self, "Saved", "Farm settings saved.")

    # -----------------------------------------------------------------------
    # Tab 3 — Deploy Config
    # -----------------------------------------------------------------------

    def _build_deploy_tab(self):
        w = QWidget()
        root = QHBoxLayout(w)

        # --- Left: slot list ---
        left = QWidget()
        left.setMaximumWidth(220)
        lv = QVBoxLayout(left)
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
        btn_save_d = QPushButton("Save Deploy Config")
        lv.addWidget(btn_save_d)

        # --- Right: editor form ---
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setAlignment(Qt.AlignTop)
        rv.addWidget(QLabel("Edit Selected Slot"))

        form = QFormLayout()

        # Template picker + thumbnail
        self._d_tmpl_cb  = QComboBox()
        self._d_thumb    = QLabel()
        self._d_thumb.setFixedSize(48, 48)
        self._d_thumb.setStyleSheet("border:1px solid #555; background:#222;")
        tmpl_h = QHBoxLayout()
        tmpl_h.addWidget(self._d_tmpl_cb)
        tmpl_h.addWidget(self._d_thumb)
        form.addRow("Template", tmpl_h)

        self._d_taps     = QSpinBox(); self._d_taps.setRange(1, 200)
        form.addRow("Taps", self._d_taps)

        self._d_strategy = QComboBox()
        self._d_strategy.addItems(["line", "points"])
        form.addRow("Strategy", self._d_strategy)

        self._d_bar_x = QSpinBox(); self._d_bar_x.setRange(0, 3000)
        self._d_bar_y = QSpinBox(); self._d_bar_y.setRange(0, 3000)
        form.addRow("Bar X  (0 = auto)", self._d_bar_x)
        form.addRow("Bar Y  (0 = auto)", self._d_bar_y)

        rv.addLayout(form)

        # Line group
        self._d_line_grp = QGroupBox("Line deployment")
        lg = QFormLayout(self._d_line_grp)
        self._d_y  = QSpinBox(); self._d_y.setRange(0, 3000);  self._d_y.setValue(760)
        self._d_xs = QSpinBox(); self._d_xs.setRange(0, 3000); self._d_xs.setValue(300)
        self._d_xe = QSpinBox(); self._d_xe.setRange(0, 3000); self._d_xe.setValue(1300)
        lg.addRow("y",       self._d_y)
        lg.addRow("x start", self._d_xs)
        lg.addRow("x end",   self._d_xe)
        rv.addWidget(self._d_line_grp)

        # Points group
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

        root.addWidget(left)
        root.addWidget(right)

        # Populate template combo and wire signals
        self._fill_template_combo(self._d_tmpl_cb)
        self._d_tmpl_cb.currentIndexChanged.connect(
            lambda: self._update_thumb(self._d_tmpl_cb, self._d_thumb))
        self._d_strategy.currentTextChanged.connect(self._toggle_deploy_strategy)

        btn_add.clicked.connect(self._deploy_add_slot)
        btn_rm.clicked.connect(self._deploy_rm_slot)
        btn_up.clicked.connect(self._deploy_move_up)
        btn_dn.clicked.connect(self._deploy_move_dn)
        btn_save_d.clicked.connect(self._save_deploy)
        btn_pt_add.clicked.connect(
            lambda: self._d_pts_tbl.insertRow(self._d_pts_tbl.rowCount()))
        btn_pt_rm.clicked.connect(self._deploy_rm_pt_row)

        self._load_deploy_slots()
        return w

    def _toggle_deploy_strategy(self, strategy):
        self._d_line_grp.setVisible(strategy == "line")
        self._d_pts_grp.setVisible(strategy == "points")

    def _fill_template_combo(self, combo):
        combo.clear()
        assets = Path(ASSETS_PATH)
        for pattern in ("units/**/*.png", "clan_capital/**/*.png"):
            for p in sorted(assets.glob(pattern)):
                rel = p.relative_to(assets).with_suffix("").as_posix()
                combo.addItem(p.stem, rel)

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
        s = load_settings()
        self._slots_data = list(s.get("attack", {}).get("deploy", {}).get("slots", []))
        self._refresh_slot_list()

    def _refresh_slot_list(self):
        self._slot_list.blockSignals(True)
        self._slot_list.clear()
        for slot in self._slots_data:
            key = slot.get("template", "?")
            self._slot_list.addItem(key.split("/")[-1] if "/" in key else key)
        self._slot_list.blockSignals(False)

    def _on_slot_selected(self, row):
        # Save current edits back to the slot we're leaving
        if 0 <= self._current_deploy_row < len(self._slots_data):
            self._collect_slot(self._current_deploy_row)
        self._current_deploy_row = row
        if row < 0 or row >= len(self._slots_data):
            return
        slot = self._slots_data[row]
        rel = slot.get("template", "")
        idx = self._d_tmpl_cb.findData(rel)
        if idx >= 0:
            self._d_tmpl_cb.setCurrentIndex(idx)
        self._d_taps.setValue(slot.get("taps", 5))
        strategy = slot.get("strategy", "line")
        self._d_strategy.setCurrentText(strategy)
        self._d_bar_x.setValue(slot.get("bar_x", 0))
        self._d_bar_y.setValue(slot.get("bar_y", 0))
        self._d_y.setValue(slot.get("y", 760))
        self._d_xs.setValue(slot.get("x_start", 300))
        self._d_xe.setValue(slot.get("x_end", 1300))
        self._d_pts_tbl.setRowCount(0)
        for pt in slot.get("points", []):
            r = self._d_pts_tbl.rowCount()
            self._d_pts_tbl.insertRow(r)
            self._d_pts_tbl.setItem(r, 0, QTableWidgetItem(str(pt[0])))
            self._d_pts_tbl.setItem(r, 1, QTableWidgetItem(str(pt[1])))
        self._update_thumb(self._d_tmpl_cb, self._d_thumb)

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
        if slot["strategy"] == "line":
            slot["y"]       = self._d_y.value()
            slot["x_start"] = self._d_xs.value()
            slot["x_end"]   = self._d_xe.value()
            slot.pop("points", None)
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
            for k in ("y", "x_start", "x_end"):
                slot.pop(k, None)

    def _deploy_add_slot(self):
        self._slots_data.append({
            "template": "units/troops/barbarian",
            "taps": 5, "strategy": "line",
            "y": 760, "x_start": 300, "x_end": 1300,
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

    def _save_deploy(self):
        if 0 <= self._current_deploy_row < len(self._slots_data):
            self._collect_slot(self._current_deploy_row)
        s = load_settings()
        s["attack"]["deploy"]["slots"] = self._slots_data
        save_settings(s)
        self._refresh_slot_list()
        QMessageBox.information(self, "Saved", "Deploy config saved.")

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

        self._m_tmpl_cb = QComboBox()
        self._m_thumb   = QLabel()
        self._m_thumb.setFixedSize(48, 48)
        self._m_thumb.setStyleSheet("border:1px solid #555; background:#222;")
        tmpl_h = QHBoxLayout()
        tmpl_h.addWidget(self._m_tmpl_cb)
        tmpl_h.addWidget(self._m_thumb)
        form.addRow("Template", tmpl_h)

        self._m_taps = QSpinBox()
        self._m_taps.setRange(1, 200)
        self._m_taps.setValue(1)
        form.addRow("Taps", self._m_taps)
        rv.addLayout(form)

        btn_add_slot = QPushButton("Add to Deploy Config")
        rv.addWidget(btn_add_slot)
        rv.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([820, 280])
        v.addWidget(splitter)

        # Wire
        self._fill_template_combo(self._m_tmpl_cb)
        self._m_tmpl_cb.currentIndexChanged.connect(
            lambda: self._update_thumb(self._m_tmpl_cb, self._m_thumb))
        btn_cap.clicked.connect(self._macro_capture)
        btn_rm_last.clicked.connect(self._macro_rm_last)
        btn_clear.clicked.connect(self._macro_clear)
        btn_add_slot.clicked.connect(self._macro_save_slot)
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
        rel  = self._m_tmpl_cb.currentData() or ""
        taps = self._m_taps.value()
        slot = {
            "template": rel,
            "taps": taps,
            "strategy": "points",
            "points": [[x, y] for x, y in self._macro_points[:taps]],
        }
        s = load_settings()
        s["attack"]["deploy"]["slots"].append(slot)
        save_settings(s)
        self._load_deploy_slots()  # refresh Deploy Config tab
        name = rel.split("/")[-1] if "/" in rel else rel
        QMessageBox.information(self, "Added",
                                f"Slot '{name}' added to Deploy Config.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
