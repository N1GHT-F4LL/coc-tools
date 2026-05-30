import html as _html

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QComboBox, QGroupBox, QCheckBox, QMessageBox,
)
from PyQt5.QtGui import QFont, QTextCursor

from gui import load_settings, save_settings
from gui.workers import BotThread


class ControlMixin:
    _LOG_MAX_LINES = 500

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
        self._act_troops = QCheckBox("Clan Troops")
        self._act_troops.setChecked(_actions.get("request_clan_troops", False))
        _cb_games = QCheckBox("Clan Games  (soon)")
        _cb_games.setEnabled(False)
        _btn_save_act = QPushButton("Save")
        _btn_save_act.clicked.connect(self._save_actions)
        ah.addWidget(self._act_collect)
        ah.addWidget(self._act_farm)
        ah.addSpacing(8)
        ah.addWidget(self._act_troops)
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
        filter_text = self._log_level_cb.currentText()
        if filter_text == "INFO+" and level == "DEBUG":
            return
        if filter_text == "WARNING+" and level not in ("WARNING", "ERROR", "CRITICAL"):
            return
        color = {"ERROR": "#f38ba8", "WARNING": "#f9e2af", "DEBUG": "#585b70"}.get(level, "#bac2de")
        self._log_view.append(f'<span style="color:{color};">{_html.escape(msg)}</span>')
        self._log_view.moveCursor(QTextCursor.End)
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
        s["actions"]["request_clan_troops"] = self._act_troops.isChecked()
        s["actions"]["clan_games"]          = False
        save_settings(s)
        QMessageBox.information(self, "Saved", "Action settings saved.")
