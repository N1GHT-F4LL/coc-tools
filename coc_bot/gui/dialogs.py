import cv2
from PyQt5.QtWidgets import (
    QLabel, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage


class DeviceView(QLabel):
    point_added     = pyqtSignal(int, int)
    region_selected = pyqtSignal(int, int, int, int)

    MODE_POINTS = "points"
    MODE_CROP   = "crop"

    def __init__(self):
        super().__init__()
        self._orig_frame = None
        self._mode       = self.MODE_POINTS
        self._markers    = []
        self._drag_start = None
        self._drag_end   = None
        self._scale_x    = 1.0
        self._scale_y    = 1.0
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setCursor(Qt.CrossCursor)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#11111b; border:1px solid #313244; border-radius:6px;")
        self.setText("No screenshot yet.\nClick 'Capture Screenshot' to begin.")

    def set_frame(self, bgr_array):
        self._orig_frame = bgr_array.copy()
        self._markers.clear()
        self._drag_start = None
        self._drag_end   = None
        self._redraw()

    def set_mode(self, mode):
        self._mode = mode
        if mode == self.MODE_POINTS:
            self._drag_start = None
            self._drag_end   = None
        else:
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

    def get_crop(self, x1, y1, x2, y2):
        if self._orig_frame is None:
            return None
        h, w = self._orig_frame.shape[:2]
        x1, x2 = sorted((max(0, x1), min(w, x2)))
        y1, y2 = sorted((max(0, y1), min(h, y2)))
        if x2 <= x1 or y2 <= y1:
            return None
        return self._orig_frame[y1:y2, x1:x2].copy()

    def _orig_coords(self, event):
        ox = int(event.x() / self._scale_x)
        oy = int(event.y() / self._scale_y)
        if self._orig_frame is not None:
            h, w = self._orig_frame.shape[:2]
            ox = max(0, min(w - 1, ox))
            oy = max(0, min(h - 1, oy))
        return ox, oy

    def mousePressEvent(self, event):
        if self._orig_frame is not None and event.button() == Qt.LeftButton:
            ox, oy = self._orig_coords(event)
            if self._mode == self.MODE_POINTS:
                self.add_marker(ox, oy)
                self.point_added.emit(ox, oy)
            else:
                self._drag_start = (ox, oy)
                self._drag_end   = (ox, oy)
                self._redraw()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._mode == self.MODE_CROP and self._drag_start is not None:
            self._drag_end = self._orig_coords(event)
            self._redraw()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (self._mode == self.MODE_CROP and
                self._drag_start is not None and
                event.button() == Qt.LeftButton):
            self._drag_end = self._orig_coords(event)
            self._redraw()
            x1 = min(self._drag_start[0], self._drag_end[0])
            y1 = min(self._drag_start[1], self._drag_end[1])
            x2 = max(self._drag_start[0], self._drag_end[0])
            y2 = max(self._drag_start[1], self._drag_end[1])
            if x2 > x1 and y2 > y1:
                self.region_selected.emit(x1, y1, x2, y2)
        super().mouseReleaseEvent(event)

    def _redraw(self):
        if self._orig_frame is None:
            return
        frame = self._orig_frame.copy()
        if self._mode == self.MODE_POINTS:
            for i, (ox, oy) in enumerate(self._markers):
                cv2.circle(frame, (ox, oy), 10, (0, 0, 255), 2)
                cv2.putText(frame, str(i + 1), (ox + 12, oy - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 80, 255), 1, cv2.LINE_AA)
        else:
            if self._drag_start and self._drag_end:
                x1 = min(self._drag_start[0], self._drag_end[0])
                y1 = min(self._drag_start[1], self._drag_end[1])
                x2 = max(self._drag_start[0], self._drag_end[0])
                y2 = max(self._drag_start[1], self._drag_end[1])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
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

    def resizeEvent(self, event):
        self._redraw()
        super().resizeEvent(event)


class _CoordPickerDialog(QDialog):
    """Modal dialog to pick screen coordinates from a device screenshot.
    multi=False → closes automatically after the first click.
    multi=True  → stays open; user picks N points then presses Done."""

    def __init__(self, frame, multi=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick Coordinates — click on the screenshot")
        self.resize(920, 580)
        self._multi  = multi
        self._picked = []

        v = QVBoxLayout(self)
        self._view = DeviceView()
        self._view.set_mode(DeviceView.MODE_POINTS)
        self._view.point_added.connect(self._on_point)
        v.addWidget(self._view, 1)

        self._lbl = QLabel("Click on the screenshot to pick a coordinate.")
        self._lbl.setStyleSheet("color:#a6adc8;")
        v.addWidget(self._lbl)

        btn_row = QHBoxLayout()
        if multi:
            btn_clear = QPushButton("Clear")
            btn_clear.clicked.connect(self._clear)
            btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        btn_ok     = QPushButton("Done")
        btn_ok.setObjectName("btn_primary")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        v.addLayout(btn_row)

        if frame is not None:
            self._view.set_frame(frame)
        else:
            self._view.setText(
                "No screenshot yet.\n"
                "Go to the Studio tab → Capture Screenshot first.")

    def _on_point(self, x, y):
        self._picked.append((x, y))
        if self._multi:
            self._lbl.setText(
                f"Picked {len(self._picked)} point(s). Click more or press Done.")
        else:
            self.accept()

    def _clear(self):
        self._picked.clear()
        self._view.clear_markers()
        self._lbl.setText("Click on the screenshot to pick a coordinate.")

    def picked(self):
        return list(self._picked)
