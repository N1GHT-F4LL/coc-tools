import copy
import cv2
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QDoubleSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem,
    QListWidget, QListWidgetItem, QLineEdit, QDialog, QInputDialog, QMessageBox,
    QMenu,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage

from gui import load_settings, save_settings, ASSETS_PATH
from gui.canvas import GraphCanvas, EdgeItem
from gui.dialogs import _CoordPickerDialog
from core.scenario import (
    list_scenarios, load_scenario, save_scenario, delete_scenario, rename_scenario,
)


class ScenariosMixin:

    _CAT_PATTERNS = {
        "Troops":       ("units/troops/*.png",),
        "Super Troops": ("units/super_troops/*.png",),
        "Heroes":       ("units/heroes/*.png",),
        "Spells":       ("units/spells/*.png",),
        "Siege":        ("units/siege/*.png",),
        "Clan Capital": ("units/clan_capital/**/*.png",),
    }
    _FOLDER_TO_CAT = {
        "troops":       "Troops",
        "super_troops": "Super Troops",
        "heroes":       "Heroes",
        "spells":       "Spells",
        "siege":        "Siege",
        "clan_capital": "Clan Capital",
    }
    _TYPE_TO_CAT = {
        "troop":  "Troops",
        "hero":   "Heroes",
        "spell":  "Spells",
        "siege":  "Siege",
    }

    # ------------------------------------------------------------------
    # Tab builder
    # ------------------------------------------------------------------

    def _build_scenarios_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        outer_splitter = QSplitter(Qt.Horizontal)

        # ── Left sidebar ─────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setMinimumWidth(160)
        sidebar.setMaximumWidth(260)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(4, 6, 4, 4)
        sb.setSpacing(4)

        self._nav_tree = QTreeWidget()
        self._nav_tree.setHeaderHidden(True)
        self._nav_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._nav_tree.setIndentation(14)
        sb.addWidget(self._nav_tree, 1)

        # Hidden spinbox — not in layout, used for internal weight tracking only
        self._variant_weight = QSpinBox()
        self._variant_weight.setRange(1, 999)

        _tree_btn_row = QHBoxLayout()
        btn_sc_new  = QPushButton("+ Scenario")
        btn_var_new = QPushButton("+ Variant")
        for _b, _c in ((btn_sc_new, "#a6e3a1"), (btn_var_new, "#89dceb")):
            _b.setStyleSheet(f"color:{_c};font-weight:bold;font-size:10px;")
        _tree_btn_row.addWidget(btn_sc_new)
        _tree_btn_row.addWidget(btn_var_new)
        sb.addLayout(_tree_btn_row)

        _sep2 = QWidget(); _sep2.setFixedHeight(1)
        _sep2.setStyleSheet("background: #313244;")
        sb.addWidget(_sep2)

        btn_node_add = QPushButton("+ Node")
        btn_node_add.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        sb.addWidget(btn_node_add)

        # ── Right area: canvas (top) + bottom drawer ─────────────────────────
        self._right_splitter = QSplitter(Qt.Vertical)

        self._graph_canvas = GraphCanvas()
        self._graph_canvas.node_selected.connect(self._on_node_selected)
        self._graph_canvas.edge_created.connect(self._on_edge_created)
        self._graph_canvas.node_moved.connect(self._on_node_moved)
        self._graph_canvas.node_delete_req.connect(self._graph_del_node_by_id)
        self._graph_canvas.node_unlink_req.connect(self._graph_unlink_by_id)
        self._right_splitter.addWidget(self._graph_canvas)

        # Bottom drawer (hidden until node selected)
        self._bottom_drawer = QWidget()
        self._bottom_drawer.hide()
        bd = QVBoxLayout(self._bottom_drawer)
        bd.setContentsMargins(8, 4, 8, 6)
        bd.setSpacing(4)

        # Row 1 — node identity + after dependencies
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row1.addWidget(QLabel("Type:"))
        self._node_type_cb = QComboBox()
        self._node_type_cb.addItems(["troop", "spell", "hero", "siege", "delay"])
        row1.addWidget(self._node_type_cb)
        row1.addSpacing(4)
        row1.addWidget(QLabel("Label:"))
        self._node_label_edit = QLineEdit()
        row1.addWidget(self._node_label_edit, 2)
        row1.addSpacing(4)
        row1.addWidget(QLabel("Pre-delay:"))
        self._node_delay_spin = QDoubleSpinBox()
        self._node_delay_spin.setRange(0, 30)
        self._node_delay_spin.setSingleStep(0.5)
        self._node_delay_spin.setFixedWidth(70)
        row1.addWidget(self._node_delay_spin)
        row1.addSpacing(4)
        row1.addWidget(QLabel("After:"))
        self._after_chips = QWidget()
        self._after_chips_layout = QHBoxLayout(self._after_chips)
        self._after_chips_layout.setContentsMargins(0, 0, 0, 0)
        self._after_chips_layout.setSpacing(4)
        self._after_chips_layout.addStretch()
        row1.addWidget(self._after_chips, 1)
        btn_after_add = QPushButton("+")
        btn_after_add.setFixedWidth(26)
        row1.addWidget(btn_after_add)
        bd.addLayout(row1)

        _sep3 = QWidget(); _sep3.setFixedHeight(1)
        _sep3.setStyleSheet("background: #313244;")
        bd.addWidget(_sep3)

        # Row 2 — slot editor
        self._slot_editor = QWidget()
        se = QHBoxLayout(self._slot_editor)
        se.setContentsMargins(0, 0, 0, 0)
        se.setSpacing(8)

        se.addWidget(QLabel("Strategy:"))
        self._d_strategy = QComboBox()
        self._d_strategy.addItems(["line", "points", "delay"])
        se.addWidget(self._d_strategy)
        se.addSpacing(4)

        # Troop fields (inline)
        self._d_troop_fields = QWidget()
        _tf = QHBoxLayout(self._d_troop_fields)
        _tf.setContentsMargins(0, 0, 0, 0); _tf.setSpacing(4)
        self._d_cat_lbl = QLabel("Type:")
        self._d_cat_cb  = QComboBox()
        self._d_cat_cb.addItems(list(self._CAT_PATTERNS))
        _tf.addWidget(self._d_cat_lbl)
        _tf.addWidget(self._d_cat_cb)
        self._d_tmpl_cb = QComboBox()
        self._d_tmpl_cb.setMinimumWidth(100)
        _tf.addWidget(self._d_tmpl_cb, 1)
        self._d_thumb = QLabel()
        self._d_thumb.setFixedSize(32, 32)
        self._d_thumb.setStyleSheet(
            "border:1px solid #313244; background:#181825; border-radius:4px;")
        _tf.addWidget(self._d_thumb)
        _tf.addSpacing(4)
        _tf.addWidget(QLabel("Taps:"))
        self._d_taps = QSpinBox(); self._d_taps.setRange(0, 200)
        self._d_taps.setFixedWidth(55)
        _tf.addWidget(self._d_taps)
        _tf.addWidget(QLabel("Bar X:"))
        self._d_bar_x = QSpinBox(); self._d_bar_x.setRange(0, 3000)
        self._d_bar_x.setFixedWidth(60)
        _tf.addWidget(self._d_bar_x)
        _tf.addWidget(QLabel("Y:"))
        self._d_bar_y = QSpinBox(); self._d_bar_y.setRange(0, 3000)
        self._d_bar_y.setFixedWidth(60)
        _tf.addWidget(self._d_bar_y)
        se.addWidget(self._d_troop_fields)

        # Line group (inline)
        self._d_line_grp = QWidget()
        _lg = QHBoxLayout(self._d_line_grp)
        _lg.setContentsMargins(0, 0, 0, 0); _lg.setSpacing(4)
        _lg.addWidget(QLabel("Start:"))
        self._d_x1 = QSpinBox(); self._d_x1.setRange(0, 3000); self._d_x1.setValue(300)
        self._d_y1 = QSpinBox(); self._d_y1.setRange(0, 3000); self._d_y1.setValue(760)
        _lg.addWidget(QLabel("X")); _lg.addWidget(self._d_x1)
        _lg.addWidget(QLabel("Y")); _lg.addWidget(self._d_y1)
        _lg.addSpacing(6)
        _lg.addWidget(QLabel("End:"))
        self._d_x2 = QSpinBox(); self._d_x2.setRange(0, 3000); self._d_x2.setValue(1300)
        self._d_y2 = QSpinBox(); self._d_y2.setRange(0, 3000); self._d_y2.setValue(760)
        _lg.addWidget(QLabel("X")); _lg.addWidget(self._d_x2)
        _lg.addWidget(QLabel("Y")); _lg.addWidget(self._d_y2)
        _lg.addSpacing(6)
        btn_pick_start = QPushButton("Pick Start")
        btn_pick_end   = QPushButton("Pick End")
        for _b in (btn_pick_start, btn_pick_end):
            _b.setFixedWidth(80); _lg.addWidget(_b)
        se.addWidget(self._d_line_grp)

        # Points group — QListWidget with horizontal button row below
        self._d_pts_grp = QWidget()
        _pg = QVBoxLayout(self._d_pts_grp)
        _pg.setContentsMargins(0, 0, 0, 0); _pg.setSpacing(4)
        self._d_pts_list = QListWidget()
        self._d_pts_list.setFixedHeight(90)
        self._d_pts_list.setFixedWidth(170)
        _pg.addWidget(self._d_pts_list)
        _pts_btns = QHBoxLayout()
        btn_pt_add  = QPushButton("+")
        btn_pt_rm   = QPushButton("−")
        btn_pt_pick = QPushButton("Pick")
        for _b in (btn_pt_add, btn_pt_rm, btn_pt_pick):
            _b.setFixedWidth(44)
            _pts_btns.addWidget(_b)
        _pg.addLayout(_pts_btns)
        se.addWidget(self._d_pts_grp)
        self._d_pts_grp.hide()

        # Delay group (inline)
        self._d_delay_grp = QWidget()
        _dg = QHBoxLayout(self._d_delay_grp)
        _dg.setContentsMargins(0, 0, 0, 0); _dg.setSpacing(4)
        _dg.addWidget(QLabel("Seconds:"))
        self._d_delay_secs = QSpinBox()
        self._d_delay_secs.setRange(1, 120)
        self._d_delay_secs.setValue(1)
        self._d_delay_secs.setFixedWidth(70)
        _dg.addWidget(self._d_delay_secs)
        se.addWidget(self._d_delay_grp)
        self._d_delay_grp.hide()

        se.addStretch()
        self._slot_editor.hide()
        bd.addWidget(self._slot_editor)

        self._right_splitter.addWidget(self._bottom_drawer)
        self._right_splitter.setStretchFactor(0, 1)
        self._right_splitter.setStretchFactor(1, 0)
        self._right_splitter.setSizes([600, 0])

        # Hidden slot list (used by _refresh_slot_list / _update_slot_label)
        self._slot_list_panel = QWidget()
        self._slot_list = QListWidget()
        self._slot_list.currentRowChanged.connect(self._on_slot_selected)

        outer_splitter.addWidget(sidebar)
        outer_splitter.addWidget(self._right_splitter)
        outer_splitter.setStretchFactor(0, 0)
        outer_splitter.setStretchFactor(1, 1)
        outer_splitter.setSizes([200, 900])
        root.addWidget(outer_splitter, 1)

        # ── Wiring ────────────────────────────────────────────────────────────
        self._fill_template_combo(self._d_tmpl_cb, "Troops")
        self._d_cat_cb.currentTextChanged.connect(
            lambda cat: self._on_cat_changed(cat, self._d_tmpl_cb, self._d_thumb))
        self._d_tmpl_cb.currentIndexChanged.connect(
            lambda: self._update_thumb(self._d_tmpl_cb, self._d_thumb))
        self._d_tmpl_cb.activated.connect(lambda _: self._update_slot_label())
        self._d_strategy.currentTextChanged.connect(self._toggle_deploy_strategy)

        self._nav_tree.itemClicked.connect(self._on_nav_clicked)
        self._nav_tree.customContextMenuRequested.connect(self._nav_ctx_menu)
        self._variant_weight.valueChanged.connect(self._on_variant_weight_changed)

        btn_sc_new.clicked.connect(self._scenario_new)
        btn_var_new.clicked.connect(self._variant_add)
        btn_node_add.clicked.connect(self._graph_add_node)

        btn_pt_add.clicked.connect(self._pts_add_row)
        btn_pt_rm.clicked.connect(self._deploy_rm_pt_row)
        btn_pt_pick.clicked.connect(self._pick_coords_for_points)
        self._d_pts_list.itemDoubleClicked.connect(self._pts_edit_item)
        btn_pick_start.clicked.connect(self._pick_line_start)
        btn_pick_end.clicked.connect(self._pick_line_end)

        self._node_label_edit.textEdited.connect(self._on_node_label_changed)
        self._node_delay_spin.valueChanged.connect(self._on_node_delay_changed)
        self._node_type_cb.currentTextChanged.connect(self._on_node_type_changed)
        btn_after_add.clicked.connect(self._on_after_add)

        for _sig in (
            self._d_taps.valueChanged,
            self._d_bar_x.valueChanged,
            self._d_bar_y.valueChanged,
            self._d_x1.valueChanged, self._d_y1.valueChanged,
            self._d_x2.valueChanged, self._d_y2.valueChanged,
            self._d_delay_secs.valueChanged,
            self._d_strategy.currentTextChanged,
            self._d_tmpl_cb.currentIndexChanged,
        ):
            _sig.connect(self._schedule_save)
        self._d_pts_list.itemChanged.connect(self._schedule_save)
        self._node_label_edit.textEdited.connect(self._schedule_save)
        self._node_delay_spin.valueChanged.connect(self._schedule_save)
        self._node_type_cb.currentTextChanged.connect(self._schedule_save)

        self._refresh_scenario_list()
        return w

    # ------------------------------------------------------------------
    # Scenario list + tree
    # ------------------------------------------------------------------

    def _refresh_scenario_list(self):
        s = load_settings()
        active = s.get("attack", {}).get("deploy", {}).get("active_scenario")
        self._nav_tree.blockSignals(True)
        self._nav_tree.clear()
        sel_item = None
        for sc_name in list_scenarios():
            text = f"★  {sc_name}" if sc_name == active else sc_name
            sc_item = QTreeWidgetItem([text])
            sc_item.setData(0, Qt.UserRole, sc_name)
            _f = sc_item.font(0); _f.setBold(True); sc_item.setFont(0, _f)
            self._nav_tree.addTopLevelItem(sc_item)
            if sc_name == self._current_scenario and self._variants_data:
                for vi, v in enumerate(self._variants_data):
                    vtext = f"  {v.get('name', '?')}  ×{v.get('weight', 1)}"
                    var_item = QTreeWidgetItem([vtext])
                    var_item.setData(0, Qt.UserRole, vi)
                    sc_item.addChild(var_item)
                    if vi == self._current_variant_idx:
                        sel_item = var_item
                sc_item.setExpanded(True)
                if sel_item is None:
                    sel_item = sc_item
        self._nav_tree.blockSignals(False)
        if sel_item:
            self._nav_tree.setCurrentItem(sel_item)
        if not self._current_scenario and self._nav_tree.topLevelItemCount() > 0:
            self._on_nav_clicked(self._nav_tree.topLevelItem(0), 0)

    def _on_scenario_selected(self, row):
        if self._current_scenario:
            if self._current_node_id and 0 <= self._current_deploy_row < len(self._slots_data):
                self._collect_slot(self._current_deploy_row)
            save_scenario(self._current_scenario, self._variants_data)
        self._slot_editor.hide()
        item = self._nav_tree.topLevelItem(row) if row >= 0 else None
        name = item.data(0, Qt.UserRole) if item else None
        if not name:
            self._current_scenario = None
            self._slots_data = []
            self._variants_data = []
            self._refresh_slot_list()
            return
        self._current_scenario = name
        self._current_deploy_row = -1
        self._load_deploy_slots()

    def _scenario_new(self):
        name, ok = QInputDialog.getText(self, "New Scenario", "Scenario name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        default_node = {"id": "n0", "label": "Deploy", "after": [], "delay": 0, "slots": []}
        default_variants = [{"name": "Default", "weight": 1, "nodes": [default_node]}]
        save_scenario(name, default_variants)
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
        self._variants_data = []
        self._current_variant_idx = 0
        self._current_node_id = None
        self._refresh_graph()
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

    # ------------------------------------------------------------------
    # Template combos / thumbs
    # ------------------------------------------------------------------

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
                combo.addItem(p.stem.replace("_", " ").title(), rel)

    def _on_cat_changed(self, cat, combo, thumb):
        self._fill_template_combo(combo, cat)
        self._update_thumb(combo, thumb)

    def _cat_from_rel(self, rel):
        parts = rel.split("/")
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

    # ------------------------------------------------------------------
    # Deploy slots
    # ------------------------------------------------------------------

    def _load_deploy_slots(self):
        default_node = {"id": "n0", "label": "Deploy", "after": [], "delay": 0, "slots": []}
        if not self._current_scenario:
            self._variants_data = [{"name": "Default", "weight": 1, "nodes": [dict(default_node)]}]
            self._current_variant_idx = 0
            self._current_node_id = None
            self._slots_data = []
            self._refresh_variant_list()
            self._refresh_graph()
            return
        try:
            data = load_scenario(self._current_scenario)
            variants = data.get("variants") or [{"name": "Default", "weight": 1, "slots": data.get("slots", [])}]
        except FileNotFoundError:
            variants = [{"name": "Default", "weight": 1, "nodes": [dict(default_node)]}]
        for v in variants:
            if "slots" in v and "nodes" not in v:
                v["nodes"] = [{"id": "n0", "label": "Deploy", "after": [], "delay": 0, "slots": v.pop("slots")}]
        self._variants_data = variants
        self._current_variant_idx = 0
        self._current_node_id = None
        self._slots_data = []
        self._refresh_variant_list()
        self._refresh_graph()

    def _update_slot_label(self):
        row = self._current_deploy_row
        item = self._slot_list.item(row)
        if item is None:
            return
        rel = self._d_tmpl_cb.currentData() or "?"
        item.setText(rel.split("/")[-1] if "/" in rel else rel)

    def _refresh_slot_list(self):
        if self._node_single_action:
            if self._slots_data:
                n = self._slots_data[0]
                if n.get("type") == "delay":
                    n["strategy"] = "delay"
                elif n.get("strategy") == "delay":
                    n.pop("strategy", None)
            self._on_slot_selected(0)
            return
        self._slot_list.blockSignals(True)
        self._slot_list.clear()
        for slot in self._slots_data:
            if slot.get("strategy") == "delay" or slot.get("type") == "delay":
                self._slot_list.addItem(f"wait {slot.get('seconds', 1)}s")
            else:
                key = slot.get("template", "?")
                self._slot_list.addItem(key.split("/")[-1] if "/" in key else key)
        self._slot_list.blockSignals(False)

    def _on_slot_selected(self, row):
        if 0 <= self._current_deploy_row < len(self._slots_data):
            self._collect_slot(self._current_deploy_row)
        self._current_deploy_row = row
        self._slot_editor.setVisible(0 <= row < len(self._slots_data))
        if row < 0 or row >= len(self._slots_data):
            return
        slot = self._slots_data[row]
        strategy = slot.get("strategy", "line")
        self._d_strategy.setCurrentText(strategy)
        self._toggle_deploy_strategy(strategy)

        if strategy == "delay":
            self._d_delay_secs.setValue(int(slot.get("seconds", 1)))
            return

        rel = slot.get("template", "")
        if self._node_single_action:
            node_type = slot.get("type", "troop")
            cat = self._TYPE_TO_CAT.get(node_type, self._cat_from_rel(rel))
            self._d_cat_lbl.setVisible(False)
            self._d_cat_cb.setVisible(False)
        else:
            cat = self._cat_from_rel(rel)
            self._d_cat_lbl.setVisible(True)
            self._d_cat_cb.setVisible(True)
        self._d_cat_cb.blockSignals(True)
        self._d_cat_cb.setCurrentText(cat)
        self._d_cat_cb.blockSignals(False)
        self._fill_template_combo(self._d_tmpl_cb, cat)
        idx = self._d_tmpl_cb.findData(rel)
        if idx >= 0:
            self._d_tmpl_cb.setCurrentIndex(idx)

        self._d_taps.setValue(int(slot.get("taps", 5)))
        self._d_bar_x.setValue(int(slot.get("bar_x", 0)))
        self._d_bar_y.setValue(int(slot.get("bar_y", 0)))
        self._d_x1.setValue(int(slot.get("x1", slot.get("x_start", 300))))
        self._d_y1.setValue(int(slot.get("y1", 760)))
        self._d_x2.setValue(int(slot.get("x2", slot.get("x_end", 1300))))
        self._d_y2.setValue(int(slot.get("y2", 760)))
        self._d_pts_list.blockSignals(True)
        self._d_pts_list.clear()
        for pt in slot.get("points", []):
            self._d_pts_list.addItem(f"{pt[0]}, {pt[1]}")
        self._d_pts_list.blockSignals(False)

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
            for r in range(self._d_pts_list.count()):
                item = self._d_pts_list.item(r)
                if item:
                    parts = [p.strip() for p in item.text().split(",")]
                    if len(parts) == 2:
                        try:
                            pts.append([int(parts[0]), int(parts[1])])
                        except ValueError:
                            pass
            slot["points"] = pts
            for k in ("y", "x_start", "x_end", "seconds"):
                slot.pop(k, None)

    def _pts_add_row(self):
        item = QListWidgetItem("0, 0")
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self._d_pts_list.addItem(item)
        self._d_pts_list.setCurrentItem(item)
        self._d_pts_list.editItem(item)

    def _pts_edit_item(self, item):
        text, ok = QInputDialog.getText(self, "Edit Point", "x, y:", text=item.text())
        if ok and text.strip():
            item.setText(text.strip())
            self._schedule_save()

    def _deploy_add_slot(self):
        if not self._current_node_id:
            QMessageBox.information(self, "No Node", "Select a node in the graph first.")
            return
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
        row = self._d_pts_list.currentRow()
        if row >= 0:
            self._d_pts_list.takeItem(row)

    # ------------------------------------------------------------------
    # Graph canvas methods
    # ------------------------------------------------------------------

    def _refresh_graph(self, keep_selected=None):
        from PyQt5.QtCore import QTimer
        v = self._variants_data[self._current_variant_idx] if self._variants_data else None
        nodes = v.get("nodes", []) if v else []
        self._graph_canvas.load_graph(nodes)
        QTimer.singleShot(0, self._graph_canvas.fit_view)
        if keep_selected and any(n["id"] == keep_selected for n in nodes):
            self._graph_canvas.highlight_node(keep_selected)
        else:
            self._current_node_id = None
            self._current_deploy_row = -1
            self._slots_data = []
            self._refresh_slot_list()
            self._bottom_drawer.setVisible(False)
            self._right_splitter.setSizes([self._right_splitter.height(), 0])

    def _on_node_selected(self, nid):
        if self._current_node_id and 0 <= self._current_deploy_row < len(self._slots_data):
            self._collect_slot(self._current_deploy_row)
        self._current_node_id = nid
        v = self._variants_data[self._current_variant_idx] if self._variants_data else None
        node = next((n for n in (v.get("nodes", []) if v else []) if n["id"] == nid), None)
        if not node:
            return
        self._node_label_edit.blockSignals(True)
        self._node_label_edit.setText(node.get("label", nid))
        self._node_label_edit.blockSignals(False)
        self._node_delay_spin.blockSignals(True)
        self._node_delay_spin.setValue(float(node.get("delay", 0)))
        self._node_delay_spin.blockSignals(False)
        self._node_type_cb.blockSignals(True)
        node_type = node.get("type", "troop")
        idx = self._node_type_cb.findText(node_type)
        self._node_type_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._node_single_action = True
        self._slots_data = [node]
        self._current_deploy_row = -1
        self._refresh_slot_list()
        self._node_type_cb.blockSignals(False)
        self._refresh_after_list()
        self._bottom_drawer.setVisible(True)
        total = self._right_splitter.height()
        self._right_splitter.setSizes([max(100, total - 160), 160])
        self._graph_canvas.highlight_node(nid)

    def _refresh_after_list(self):
        if not self._current_node_id or not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        node = next((n for n in v.get("nodes", []) if n["id"] == self._current_node_id), None)
        if not node:
            return
        after = node.get("after", [])
        lay = self._after_chips_layout
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for dep_id in after:
            dep_node = next((n for n in v.get("nodes", []) if n["id"] == dep_id), None)
            lbl = dep_node.get("label", dep_id) if dep_node else dep_id
            chip = QPushButton(f"{lbl}  ×")
            chip.setFixedHeight(22)
            chip.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #45475a;border-radius:10px;"
                "color:#cdd6f4;padding:1px 8px;font-size:11px;}"
                "QPushButton:hover{background:#f38ba8;border-color:#f38ba8;color:#1e1e2e;}"
            )
            chip.clicked.connect(lambda _, d=dep_id: self._on_after_remove_dep(d))
            lay.addWidget(chip)
        lay.addStretch()

    def _on_after_add(self):
        if not self._current_node_id or not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        node = next((n for n in v.get("nodes", []) if n["id"] == self._current_node_id), None)
        if not node:
            return
        after = node.get("after", [])
        available = [
            (n["id"], n.get("label", n["id"]))
            for n in v.get("nodes", [])
            if n["id"] != self._current_node_id and n["id"] not in after
        ]
        if not available:
            return
        menu = QMenu(self)
        for nid, lbl in available:
            act = menu.addAction(lbl)
            act.setData(nid)
        btn = self.sender()
        chosen = menu.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))
        if not chosen:
            return
        dep_id = chosen.data()
        if not dep_id or dep_id in node.get("after", []):
            return
        node.setdefault("after", []).append(dep_id)
        nid = self._current_node_id
        self._refresh_graph(keep_selected=nid)
        self._refresh_after_list()
        self._schedule_save()

    def _on_after_remove_dep(self, dep_id):
        if not self._current_node_id or not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        node = next((n for n in v.get("nodes", []) if n["id"] == self._current_node_id), None)
        if not node or dep_id not in node.get("after", []):
            return
        node["after"].remove(dep_id)
        nid = self._current_node_id
        self._refresh_graph(keep_selected=nid)
        self._refresh_after_list()
        self._schedule_save()

    def _on_node_label_changed(self, text):
        if not self._current_node_id or not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        node = next((n for n in v.get("nodes", []) if n["id"] == self._current_node_id), None)
        if node:
            node["label"] = text
            self._graph_canvas.update_node_label(self._current_node_id, text)

    def _on_node_delay_changed(self, val):
        if not self._current_node_id or not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        node = next((n for n in v.get("nodes", []) if n["id"] == self._current_node_id), None)
        if node:
            node["delay"] = val

    def _on_node_type_changed(self, text):
        if not self._current_node_id or not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        node = next((n for n in v.get("nodes", []) if n["id"] == self._current_node_id), None)
        if not node:
            return
        node["type"] = text
        self._node_single_action = True
        self._slots_data = [node]
        self._current_deploy_row = -1
        self._d_cat_lbl.setVisible(False)
        self._d_cat_cb.setVisible(False)
        if text == "delay":
            for k in ("strategy", "template", "taps", "bar_x", "bar_y",
                      "x1", "y1", "x2", "y2", "x_start", "x_end", "y", "points"):
                node.pop(k, None)
        else:
            node.pop("strategy", None)
            node.pop("seconds", None)
        self._schedule_save()
        self._refresh_slot_list()

    def _on_edge_created(self, src_id, dst_id):
        if not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        dst_node = next((n for n in v.get("nodes", []) if n["id"] == dst_id), None)
        if not dst_node or src_id in dst_node.get("after", []):
            return
        dst_node.setdefault("after", []).append(src_id)
        nid = self._current_node_id
        self._refresh_graph(keep_selected=nid)
        if dst_id == nid:
            self._refresh_after_list()
        self._schedule_save()

    def _on_node_moved(self, nid, x, y):
        if not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        node = next((n for n in v.get("nodes", []) if n["id"] == nid), None)
        if node:
            node["x"] = x
            node["y"] = y

    def _graph_relayout(self):
        self._refresh_graph()

    def _graph_add_node(self):
        if not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        nodes = v.setdefault("nodes", [])
        existing_ids = {n["id"] for n in nodes}
        idx = len(nodes)
        nid = f"n{idx}"
        while nid in existing_ids:
            idx += 1
            nid = f"n{idx}"
        nodes.append({
            "id": nid, "label": f"Node {len(nodes) + 1}",
            "after": [], "delay": 0, "slots": [],
        })
        self._refresh_graph()
        self._schedule_save()

    def _graph_del_node(self):
        if not self._current_node_id or not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        nid = self._current_node_id
        v["nodes"] = [n for n in v.get("nodes", []) if n["id"] != nid]
        for n in v["nodes"]:
            n["after"] = [d for d in n.get("after", []) if d != nid]
        self._current_node_id = None
        self._current_deploy_row = -1
        self._slots_data = []
        self._refresh_graph()
        self._schedule_save()

    def _graph_unlink(self):
        if not self._current_node_id or not self._variants_data:
            return
        v = self._variants_data[self._current_variant_idx]
        node = next((n for n in v.get("nodes", []) if n["id"] == self._current_node_id), None)
        if not node or not node.get("after"):
            QMessageBox.information(self, "Unlink Edge", "This node has no dependencies to remove.")
            return
        nodes_map = {n["id"]: n for n in v.get("nodes", [])}
        options = [f"{nodes_map.get(nid, {}).get('label', nid)} ({nid})" for nid in node["after"]]
        item, ok = QInputDialog.getItem(
            self, "Remove Dependency",
            f"Remove which dependency from '{node.get('label', node['id'])}'?",
            options, 0, False,
        )
        if not ok:
            return
        removed_idx = options.index(item)
        src_id = node["after"].pop(removed_idx)
        dst_id = self._current_node_id
        self._graph_canvas._edges = [
            e for e in self._graph_canvas._edges
            if not (e.src.nid == src_id and e.dst.nid == dst_id)
        ]
        for scene_item in list(self._graph_canvas._scene.items()):
            if isinstance(scene_item, EdgeItem) and scene_item.src.nid == src_id and scene_item.dst.nid == dst_id:
                self._graph_canvas._scene.removeItem(scene_item)

    def _graph_del_node_by_id(self, nid):
        self._current_node_id = nid
        self._graph_del_node()

    def _graph_unlink_by_id(self, nid):
        self._current_node_id = nid
        self._graph_unlink()

    # ------------------------------------------------------------------
    # Navigation tree
    # ------------------------------------------------------------------

    def _on_nav_clicked(self, item, col):
        parent = item.parent()
        if parent is None:
            name = item.data(0, Qt.UserRole)
            if name == self._current_scenario:
                return
            sc_row = self._nav_tree.indexOfTopLevelItem(item)
            self._on_scenario_selected(sc_row)
        else:
            sc_name = parent.data(0, Qt.UserRole)
            var_idx  = parent.indexOfChild(item)
            if sc_name != self._current_scenario:
                sc_row = self._nav_tree.indexOfTopLevelItem(parent)
                self._on_scenario_selected(sc_row)
            if var_idx != self._current_variant_idx:
                self._on_variant_changed(var_idx)

    def _nav_ctx_menu(self, pos):
        item = self._nav_tree.itemAt(pos)
        if not item:
            return
        self._on_nav_clicked(item, 0)
        m = QMenu(self._nav_tree)
        if item.parent() is None:
            m.addAction("Rename",           self._scenario_rename)
            m.addAction("Delete",           self._scenario_delete)
            m.addSeparator()
            m.addAction("Set Active",       self._scenario_set_active)
            m.addAction("Add Variant",      self._variant_add)
        else:
            m.addAction("Duplicate",            self._variant_dup)
            m.addAction("Rename",               self._variant_rename)
            m.addAction("Delete",               self._variant_delete)
            m.addSeparator()
            m.addAction("Change Weight...",     self._variant_change_weight)
        m.exec_(self._nav_tree.viewport().mapToGlobal(pos))

    def _variant_change_weight(self):
        if not self._variants_data:
            return
        cur = self._variants_data[self._current_variant_idx].get("weight", 1)
        val, ok = QInputDialog.getInt(self, "Change Weight", "Weight:", cur, 1, 999)
        if not ok:
            return
        self._variants_data[self._current_variant_idx]["weight"] = val
        self._variant_weight.blockSignals(True)
        self._variant_weight.setValue(val)
        self._variant_weight.blockSignals(False)
        self._refresh_scenario_list()
        self._schedule_save()

    def _refresh_variant_list(self):
        self._variant_weight.blockSignals(True)
        if self._variants_data:
            self._variant_weight.setValue(
                self._variants_data[self._current_variant_idx].get("weight", 1))
        self._variant_weight.blockSignals(False)
        self._refresh_scenario_list()

    def _on_variant_changed(self, idx):
        if idx < 0 or idx == self._current_variant_idx or not self._variants_data:
            return
        if self._current_node_id and 0 <= self._current_deploy_row < len(self._slots_data):
            self._collect_slot(self._current_deploy_row)
        self._current_variant_idx = idx
        self._current_node_id = None
        self._current_deploy_row = -1
        self._slots_data = []
        self._variant_weight.blockSignals(True)
        self._variant_weight.setValue(self._variants_data[idx].get("weight", 1))
        self._variant_weight.blockSignals(False)
        self._refresh_graph()

    def _on_variant_weight_changed(self, val):
        if not self._variants_data:
            return
        self._variants_data[self._current_variant_idx]["weight"] = val
        self._refresh_scenario_list()
        self._schedule_save()

    def _variant_dup(self):
        if not self._variants_data:
            return
        src = self._variants_data[self._current_variant_idx]
        clone = copy.deepcopy(src)
        clone["name"] = src.get("name", "Variant") + " Copy"
        self._variants_data.insert(self._current_variant_idx + 1, clone)
        self._current_variant_idx += 1
        self._current_node_id = None
        self._current_deploy_row = -1
        self._slots_data = []
        self._refresh_variant_list()
        self._refresh_graph()
        self._schedule_save()

    def _variant_add(self):
        if self._current_node_id and 0 <= self._current_deploy_row < len(self._slots_data):
            self._collect_slot(self._current_deploy_row)
        n = len(self._variants_data) + 1
        default_node = {"id": "n0", "label": "Deploy", "after": [], "delay": 0, "slots": []}
        self._variants_data.append({"name": f"Variant {n}", "weight": 1, "nodes": [default_node]})
        self._current_variant_idx = len(self._variants_data) - 1
        self._current_node_id = None
        self._current_deploy_row = -1
        self._slots_data = []
        self._refresh_variant_list()
        self._refresh_graph()
        self._schedule_save()

    def _variant_delete(self):
        if len(self._variants_data) <= 1:
            QMessageBox.warning(self, "Cannot Delete", "A scenario must have at least one variant.")
            return
        del self._variants_data[self._current_variant_idx]
        self._current_variant_idx = max(0, self._current_variant_idx - 1)
        self._current_node_id = None
        self._current_deploy_row = -1
        self._slots_data = []
        self._refresh_variant_list()
        self._refresh_graph()
        self._schedule_save()

    def _variant_rename(self):
        if not self._variants_data:
            return
        cur_name = self._variants_data[self._current_variant_idx].get("name", "")
        new_name, ok = QInputDialog.getText(self, "Rename Variant", "Variant name:", text=cur_name)
        if not ok or not new_name.strip() or new_name.strip() == cur_name:
            return
        self._variants_data[self._current_variant_idx]["name"] = new_name.strip()
        self._refresh_variant_list()
        self._schedule_save()

    # ------------------------------------------------------------------
    # Coordinate picker helpers
    # ------------------------------------------------------------------

    def _open_picker(self, multi=False):
        dlg = _CoordPickerDialog(self._last_studio_frame, multi=multi, parent=self)
        return dlg if dlg.exec_() == QDialog.Accepted else None

    def _pick_coords_for_points(self):
        dlg = _CoordPickerDialog(self._last_studio_frame, multi=True, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        for x, y in dlg.picked():
            item = QListWidgetItem(f"{x}, {y}")
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self._d_pts_list.addItem(item)

    def _pick_line_start(self):
        dlg = _CoordPickerDialog(self._last_studio_frame, multi=False, parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.picked():
            x, y = dlg.picked()[0]
            self._d_x1.setValue(x)
            self._d_y1.setValue(y)

    def _pick_line_end(self):
        dlg = _CoordPickerDialog(self._last_studio_frame, multi=False, parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.picked():
            x, y = dlg.picked()[0]
            self._d_x2.setValue(x)
            self._d_y2.setValue(y)

    def _schedule_save(self, *_):
        if self._current_scenario:
            self._save_debounce.start(600)

    def _scenario_save(self):
        if not self._current_scenario:
            return
        if self._current_node_id and 0 <= self._current_deploy_row < len(self._slots_data):
            self._collect_slot(self._current_deploy_row)
        save_scenario(self._current_scenario, self._variants_data)
