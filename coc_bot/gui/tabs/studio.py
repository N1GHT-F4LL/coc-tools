import re
import cv2
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSplitter, QStackedWidget, QRadioButton, QTreeWidget, QTreeWidgetItem,
    QListWidget, QLineEdit, QFormLayout, QMessageBox, QThreadPool,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage

from gui import load_settings, ASSETS_PATH, _CAT_TO_FOLDER
from gui.workers import ScreenshotWorker
from gui.dialogs import DeviceView
from core.scenario import save_scenario


class StudioMixin:

    def _build_studio_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        top = QHBoxLayout()
        self._s_btn_cap = QPushButton("Capture Screenshot")
        self._s_btn_cap.setObjectName("btn_primary")
        self._s_res_lbl = QLabel("No screenshot captured.")
        self._s_res_lbl.setStyleSheet("color:#a6adc8;")
        self._s_mode_rec  = QRadioButton("Record Taps")
        self._s_mode_crop = QRadioButton("Add Asset")
        self._s_mode_rec.setChecked(True)
        top.addWidget(self._s_btn_cap)
        top.addWidget(self._s_res_lbl, 1)
        top.addWidget(self._s_mode_rec)
        top.addWidget(self._s_mode_crop)
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        self._studio_view = DeviceView()
        splitter.addWidget(self._studio_view)

        self._s_stack = QStackedWidget()
        self._s_stack.setMinimumWidth(270)
        self._s_stack.setMaximumWidth(340)
        self._s_stack.addWidget(self._build_studio_record_panel())
        self._s_stack.addWidget(self._build_studio_crop_panel())
        splitter.addWidget(self._s_stack)
        splitter.setSizes([900, 300])

        root.addWidget(splitter, 1)

        self._s_btn_cap.clicked.connect(self._studio_capture)
        self._studio_view.point_added.connect(self._studio_on_click)
        self._studio_view.region_selected.connect(self._studio_on_region)
        self._s_mode_rec.toggled.connect(self._studio_mode_changed)

        self._fill_template_combo(self._s_tmpl_cb, "Troops")
        self._s_cat_cb.currentTextChanged.connect(
            lambda c: self._on_cat_changed(c, self._s_tmpl_cb, self._s_thumb))
        self._s_tmpl_cb.currentIndexChanged.connect(
            lambda: self._update_thumb(self._s_tmpl_cb, self._s_thumb))
        self._s_asset_cat_cb.addItems(sorted(_CAT_TO_FOLDER.keys()))
        self._s_asset_cat_cb.setCurrentText("Troops")
        self._s_asset_name_le.textChanged.connect(self._studio_name_changed)
        self._s_asset_cat_cb.currentTextChanged.connect(self._studio_update_key_label)
        self._assets_populate_tree()
        return w

    def _build_studio_record_panel(self):
        w = QWidget()
        rv = QVBoxLayout(w)
        rv.setContentsMargins(8, 8, 8, 8)
        rv.setSpacing(6)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._s_cat_cb = QComboBox()
        self._s_cat_cb.addItems(list(self._CAT_PATTERNS))
        form.addRow("Unit Type", self._s_cat_cb)

        self._s_tmpl_cb = QComboBox()
        form.addRow("Troop", self._s_tmpl_cb)
        self._s_thumb = QLabel()
        self._s_thumb.setFixedSize(48, 48)
        self._s_thumb.setStyleSheet(
            "border:1px solid #313244; background:#181825; border-radius:4px;")
        _s_thumb_row = QHBoxLayout()
        _s_thumb_row.setContentsMargins(0, 0, 0, 0)
        _s_thumb_row.addWidget(self._s_thumb)
        _s_thumb_row.addStretch()
        form.addRow("", _s_thumb_row)

        from PyQt5.QtWidgets import QSpinBox
        self._s_taps = QSpinBox()
        self._s_taps.setRange(1, 200)
        self._s_taps.setValue(1)
        form.addRow("Taps", self._s_taps)
        rv.addLayout(form)

        sep = QLabel("Recorded Points")
        sep.setStyleSheet("color:#a6adc8; font-weight:600; margin-top:8px;")
        rv.addWidget(sep)

        self._s_pts_list = QListWidget()
        rv.addWidget(self._s_pts_list, 1)

        btn_row1 = QHBoxLayout()
        btn_rm_last = QPushButton("Remove Last")
        btn_clear   = QPushButton("Clear All")
        btn_row1.addWidget(btn_rm_last)
        btn_row1.addWidget(btn_clear)
        rv.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        btn_save_pts  = QPushButton("Save as Points")
        btn_save_line = QPushButton("Save as Line")
        btn_row2.addWidget(btn_save_pts)
        btn_row2.addWidget(btn_save_line)
        rv.addLayout(btn_row2)

        btn_rm_last.clicked.connect(self._studio_rm_last)
        btn_clear.clicked.connect(self._studio_clear)
        btn_save_pts.clicked.connect(self._studio_save_slot)
        btn_save_line.clicked.connect(self._studio_save_line)
        return w

    def _build_studio_crop_panel(self):
        w = QWidget()
        rv = QVBoxLayout(w)
        rv.setContentsMargins(8, 8, 8, 8)
        rv.setSpacing(6)

        preview_row = QHBoxLayout()
        preview_lbl = QLabel("Crop Preview:")
        preview_lbl.setStyleSheet("color:#a6adc8;")
        self._s_crop_preview = QLabel()
        self._s_crop_preview.setFixedSize(96, 96)
        self._s_crop_preview.setAlignment(Qt.AlignCenter)
        self._s_crop_preview.setStyleSheet(
            "background:#181825; border:1px solid #313244; border-radius:4px;")
        preview_row.addWidget(preview_lbl)
        preview_row.addWidget(self._s_crop_preview)
        preview_row.addStretch()
        rv.addLayout(preview_row)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._s_asset_cat_cb = QComboBox()
        form.addRow("Category", self._s_asset_cat_cb)

        self._s_asset_name_le = QLineEdit()
        self._s_asset_name_le.setPlaceholderText("e.g. wizard")
        form.addRow("Name", self._s_asset_name_le)

        self._s_asset_key_lbl = QLabel("—")
        self._s_asset_key_lbl.setStyleSheet("color:#a6adc8; font-size:9pt;")
        form.addRow("Key", self._s_asset_key_lbl)
        rv.addLayout(form)

        self._s_btn_save_asset = QPushButton("Save Asset")
        self._s_btn_save_asset.setObjectName("btn_primary")
        self._s_btn_save_asset.setEnabled(False)
        rv.addWidget(self._s_btn_save_asset)

        sep = QLabel("Asset Library")
        sep.setStyleSheet("color:#a6adc8; font-weight:600; margin-top:8px;")
        rv.addWidget(sep)

        self._assets_tree = QTreeWidget()
        self._assets_tree.setHeaderLabel("Asset")
        self._assets_tree.setRootIsDecorated(True)
        self._assets_tree.setUniformRowHeights(True)
        rv.addWidget(self._assets_tree, 1)

        btn_del = QPushButton("Delete Selected")
        btn_del.clicked.connect(self._assets_delete)
        rv.addWidget(btn_del)

        self._s_crop_bgr = None
        self._s_btn_save_asset.clicked.connect(self._studio_save_asset)
        return w

    def _assets_populate_tree(self):
        expanded = {
            self._assets_tree.topLevelItem(i).text(0)
            for i in range(self._assets_tree.topLevelItemCount())
            if self._assets_tree.topLevelItem(i).isExpanded()
        }
        self._assets_tree.clear()
        base = Path(ASSETS_PATH)
        groups = {}
        for p in sorted(base.rglob("*.png")):
            folder = p.parent.relative_to(base).as_posix()
            groups.setdefault(folder, []).append(p)

        for folder in sorted(groups):
            top = QTreeWidgetItem([folder])
            top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
            for p in groups[folder]:
                rel = p.relative_to(base).with_suffix("").as_posix()
                child = QTreeWidgetItem([p.stem])
                child.setData(0, Qt.UserRole, rel)
                top.addChild(child)
            self._assets_tree.addTopLevelItem(top)
            if folder in expanded:
                top.setExpanded(True)

    def _assets_delete(self):
        items = self._assets_tree.selectedItems()
        if not items:
            return
        item = items[0]
        rel = item.data(0, Qt.UserRole)
        if not rel:
            return
        path = Path(ASSETS_PATH) / (rel + ".png")
        ans = QMessageBox.question(
            self, "Xác nhận xóa",
            f"Xóa asset '{rel}'?\nFile sẽ bị xóa khỏi disk.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        try:
            path.unlink()
        except OSError as e:
            QMessageBox.warning(self, "Lỗi", str(e))
            return
        from core.vision import vision as _vision
        _vision.cache.clear()
        _vision.load_assets(ASSETS_PATH)
        self._assets_populate_tree()
        self._assets_refresh_combos()

    def _assets_refresh_combos(self):
        self._fill_template_combo(self._d_tmpl_cb, self._d_cat_cb.currentText())
        self._fill_template_combo(self._s_tmpl_cb, self._s_cat_cb.currentText())

    def _studio_capture(self):
        self._s_res_lbl.setText("Connecting to device…")
        worker = ScreenshotWorker(load_settings())
        worker.signals.done.connect(self._studio_on_frame)
        worker.signals.error.connect(self._studio_on_error)
        QThreadPool.globalInstance().start(worker)

    def _studio_on_frame(self, frame):
        h, w = frame.shape[:2]
        self._s_res_lbl.setText(f"Resolution: {w}×{h}")
        self._last_studio_frame = frame
        self._studio_view.set_frame(frame)

    def _studio_on_error(self, msg):
        self._s_res_lbl.setText(f"Error: {msg}")
        QMessageBox.warning(self, "Screenshot Error", msg)

    def _studio_mode_changed(self, rec_checked):
        if rec_checked:
            self._studio_view.set_mode(DeviceView.MODE_POINTS)
            self._s_stack.setCurrentIndex(0)
        else:
            self._studio_view.set_mode(DeviceView.MODE_CROP)
            self._s_stack.setCurrentIndex(1)

    def _studio_on_click(self, x, y):
        self._studio_points.append((x, y))
        idx = len(self._studio_points)
        self._s_pts_list.addItem(f"{idx}.  ({x}, {y})")
        self._s_taps.setValue(idx)

    def _studio_rm_last(self):
        if self._studio_points:
            self._studio_points.pop()
            self._s_pts_list.takeItem(self._s_pts_list.count() - 1)
            self._studio_view.remove_last_marker()
            self._s_taps.setValue(max(1, len(self._studio_points)))

    def _studio_clear(self):
        self._studio_points.clear()
        self._s_pts_list.clear()
        self._studio_view.clear_markers()
        self._s_taps.setValue(1)

    def _studio_save_slot(self):
        if not self._studio_points:
            QMessageBox.warning(self, "No Points",
                                "Record at least one tap point before saving.")
            return
        if not self._current_scenario:
            QMessageBox.warning(self, "No Scenario",
                                "Select or create a scenario in the Troops tab first.")
            return
        if not self._current_node_id:
            QMessageBox.warning(self, "No Node Selected",
                                "Select a node in the Troops tab graph before adding a slot.")
            return
        rel  = self._s_tmpl_cb.currentData() or ""
        taps = self._s_taps.value()
        slot = {
            "template": rel, "taps": taps, "strategy": "points",
            "points": [[x, y] for x, y in self._studio_points],
        }
        self._slots_data.append(slot)
        save_scenario(self._current_scenario, self._variants_data)
        self._refresh_slot_list()
        name = rel.split("/")[-1] if "/" in rel else rel
        QMessageBox.information(self, "Added",
                                f"Slot '{name}' added to '{self._current_scenario}'.")

    def _studio_save_line(self):
        if len(self._studio_points) < 2:
            QMessageBox.warning(self, "Need 2 Points",
                                "Record exactly 2 points (start and end of the line).")
            return
        if not self._current_scenario:
            QMessageBox.warning(self, "No Scenario",
                                "Select or create a scenario in the Troops tab first.")
            return
        if not self._current_node_id:
            QMessageBox.warning(self, "No Node Selected",
                                "Select a node in the Troops tab graph before adding a slot.")
            return
        rel  = self._s_tmpl_cb.currentData() or ""
        taps = self._s_taps.value()
        x1, y1 = self._studio_points[0]
        x2, y2 = self._studio_points[-1]
        slot = {
            "template": rel, "taps": taps, "strategy": "line",
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        }
        self._slots_data.append(slot)
        save_scenario(self._current_scenario, self._variants_data)
        self._refresh_slot_list()
        name = rel.split("/")[-1] if "/" in rel else rel
        QMessageBox.information(self, "Added",
                                f"Line slot '{name}' ({x1},{y1})→({x2},{y2}) added.")

    def _studio_on_region(self, x1, y1, x2, y2):
        crop = self._studio_view.get_crop(x1, y1, x2, y2)
        if crop is None:
            return
        self._s_crop_bgr = crop
        h, w = crop.shape[:2]
        scale = min(96 / w, 96 / h, 4.0)
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
        rgb = cv2.cvtColor(cv2.resize(crop, (dw, dh), interpolation=cv2.INTER_NEAREST),
                           cv2.COLOR_BGR2RGB)
        qi = QImage(rgb.data, dw, dh, dw * 3, QImage.Format_RGB888)
        self._s_crop_preview.setPixmap(QPixmap.fromImage(qi))
        self._studio_update_save_btn()

    def _studio_name_changed(self, text):
        self._studio_update_key_label()
        self._studio_update_save_btn()

    def _studio_update_key_label(self):
        cat  = self._s_asset_cat_cb.currentText()
        name = re.sub(r"[^a-z0-9_]", "_", self._s_asset_name_le.text().strip().lower())
        if cat and name:
            folder = _CAT_TO_FOLDER.get(cat, "units/troops")
            self._s_asset_key_lbl.setText(f"{folder}/{name}")
        else:
            self._s_asset_key_lbl.setText("—")

    def _studio_update_save_btn(self):
        name = self._s_asset_name_le.text().strip()
        self._s_btn_save_asset.setEnabled(bool(name and self._s_crop_bgr is not None))

    def _studio_save_asset(self):
        if self._s_crop_bgr is None:
            return
        name = re.sub(r"[^a-z0-9_]", "_", self._s_asset_name_le.text().strip().lower())
        if not name:
            QMessageBox.warning(self, "No Name", "Enter an asset name before saving.")
            return
        cat    = self._s_asset_cat_cb.currentText()
        folder = _CAT_TO_FOLDER.get(cat, "units/troops")
        dest   = Path(ASSETS_PATH) / folder / f"{name}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(dest), self._s_crop_bgr):
            QMessageBox.critical(self, "Lỗi", f"Không thể ghi file:\n{dest}")
            return
        from core.vision import vision as _vision
        rel_key = dest.relative_to(Path(ASSETS_PATH)).with_suffix("").as_posix()
        _vision.cache[name]    = self._s_crop_bgr
        _vision.cache[rel_key] = self._s_crop_bgr
        self._assets_populate_tree()
        self._assets_refresh_combos()
        self._s_crop_bgr = None
        self._s_crop_preview.clear()
        self._s_asset_name_le.clear()
        self._s_btn_save_asset.setEnabled(False)
        self._s_res_lbl.setText(f"Asset '{name}' saved to {folder}/")
