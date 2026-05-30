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

_HERE    = os.path.dirname(__file__)   # coc_bot/gui/
_BOT_DIR = os.path.dirname(_HERE)      # coc_bot/

SETTINGS_PATH = os.path.join(_BOT_DIR, "settings.json")
ASSETS_PATH   = os.path.join(_BOT_DIR, "assets")

_CAT_TO_FOLDER = {
    "Troops":                 "units/troops",
    "Super Troops":           "units/super_troops",
    "Heroes":                 "units/heroes",
    "Spells":                 "units/spells",
    "Siege":                  "units/siege",
    "Clan Capital / Troops":  "units/clan_capital/troops",
    "Clan Capital / Spells":  "units/clan_capital/spells",
    "Buildings / Defenses":   "buildings/defenses",
    "Buildings / Collectors": "buildings/resource_collectors",
    "Buildings / Storages":   "buildings/storages",
    "Buildings / Utility":    "buildings/utility",
    "Buildings / Walls":      "buildings/walls",
    "Buttons / Attack":       "buttons/attack",
    "Buttons / Battle":       "buttons/battle",
    "Buttons / Home":         "buttons/home",
    "Buttons / Popup":        "buttons/popup",
    "Icons / Resources":      "icons/resources",
    "Icons / Status":         "icons/status",
}


def load_settings():
    with open(SETTINGS_PATH) as f:
        return json.load(f)


def save_settings(settings):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


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
    padding: 4px 9px; min-height: 26px; min-width: 0px; font-weight: 500;
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
QComboBox:on    { border-color: #89b4fa; background: #1e1e2e; }
QComboBox::drop-down {
    background: #313244; border-left: 1px solid #45475a;
    width: 24px; border-radius: 0 6px 6px 0;
}
QComboBox QAbstractItemView {
    background: #181825; color: #cdd6f4;
    selection-background-color: #89b4fa; selection-color: #1e1e2e;
    alternate-background-color: #1e1e2e;
    border: 1px solid #45475a; outline: none; padding: 2px;
}
QComboBox QAbstractItemView::item { padding: 5px 8px; min-height: 26px; border-radius: 4px; }
QComboBox QAbstractItemView::item:selected              { background: #89b4fa; color: #1e1e2e; }
QComboBox QAbstractItemView::item:hover:!selected       { background: #313244; }

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
    background: transparent; border: 1px solid #313244; border-radius: 8px;
    margin-top: 20px; padding: 14px 10px 10px 10px;
    font-weight: 600; color: #a6adc8;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 0px; padding: 2px 8px 2px 14px;
    color: #b4befe; background: transparent; border-radius: 4px;
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

/* ── Tree views ───────────────────────────────────── */
QTreeWidget, QTreeView {
    background: #181825; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px;
    outline: none; alternate-background-color: #1e1e2e;
}
QTreeWidget::item, QTreeView::item { padding: 4px 8px; border-radius: 4px; margin: 1px 4px; }
QTreeWidget::item:selected, QTreeView::item:selected { background: #89b4fa; color: #1e1e2e; }
QTreeWidget::item:hover:!selected, QTreeView::item:hover:!selected { background: #313244; }
QTreeWidget::branch, QTreeView::branch { background: #181825; }
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeView::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings,
QTreeView::branch:closed:has-children:has-siblings {
    image: url(none); border-image: none;
    color: #6c7086;
}
QTreeWidget::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:!has-siblings,
QTreeWidget::branch:open:has-children:has-siblings,
QTreeView::branch:open:has-children:has-siblings {
    image: url(none); border-image: none;
    color: #6c7086;
}

/* ── Checkboxes ───────────────────────────────────── */
QCheckBox { color: #cdd6f4; background: transparent; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1.5px solid #585b70; border-radius: 4px;
    background: #181825;
}
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QCheckBox::indicator:hover   { border-color: #89b4fa; }

/* ── Radio buttons ────────────────────────────────── */
QRadioButton { color: #cdd6f4; background: transparent; spacing: 8px; }
QRadioButton::indicator {
    width: 16px; height: 16px;
    border: 1.5px solid #585b70; border-radius: 8px;
    background: #181825;
}
QRadioButton::indicator:checked {
    background: #89b4fa; border-color: #89b4fa;
    image: none;
}
QRadioButton::indicator:checked::after { }
QRadioButton::indicator:hover { border-color: #89b4fa; }

/* ── Tooltips ─────────────────────────────────────── */
QToolTip {
    background: #313244; color: #cdd6f4;
    border: 1px solid #585b70; border-radius: 4px; padding: 6px 10px;
}

/* ── Labels ───────────────────────────────────────── */
QLabel { color: #cdd6f4; background: transparent; }
QFormLayout QLabel { color: #a6adc8; background: transparent; }
"""


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


def _dark_palette():
    from PyQt5.QtGui import QPalette, QColor
    p = QPalette()
    c = {
        QPalette.Window:          "#1e1e2e",
        QPalette.WindowText:      "#cdd6f4",
        QPalette.Base:            "#181825",
        QPalette.AlternateBase:   "#1e1e2e",
        QPalette.ToolTipBase:     "#313244",
        QPalette.ToolTipText:     "#cdd6f4",
        QPalette.Text:            "#cdd6f4",
        QPalette.Button:          "#313244",
        QPalette.ButtonText:      "#cdd6f4",
        QPalette.BrightText:      "#f38ba8",
        QPalette.Link:            "#89b4fa",
        QPalette.Highlight:       "#89b4fa",
        QPalette.HighlightedText: "#1e1e2e",
        QPalette.Disabled + QPalette.Text:       "#6c7086",
        QPalette.Disabled + QPalette.ButtonText: "#6c7086",
        QPalette.Disabled + QPalette.WindowText: "#6c7086",
    }
    for role, hex_color in c.items():
        p.setColor(role, QColor(hex_color))
    return p


def main():
    from PyQt5.QtWidgets import QApplication
    from .window import MainWindow
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setStyleSheet(_DARK_STYLE)
    win = MainWindow()
    _apply_dark_titlebar(int(win.winId()))
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
