from PyQt5.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsItem, QGraphicsPathItem,
    QWidget, QHBoxLayout, QPushButton, QMenu,
)
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QRectF, QPointF
from PyQt5.QtGui import QPen, QBrush, QColor, QPainterPath, QPainter


_TAP_INTERVAL   = 0.15   # seconds between taps (matches DEPLOY_TAP_INTERVAL)
_CLICK_OVERHEAD = 0.30   # initial slot-click delay before strategy execution


def _topo_layers(nodes):
    """Return nodes grouped by topological layer (list of lists of node ids).
    Returns (layers, cycle_nodes) where cycle_nodes is a set of IDs involved in cycles."""
    all_ids = {n["id"] for n in nodes}
    id_to_deps = {n["id"]: set(n.get("after", [])) & all_ids for n in nodes}
    layers, placed = [], set()
    while id_to_deps:
        layer = [nid for nid, deps in id_to_deps.items() if deps <= placed]
        if not layer:
            cycle_nodes = set(id_to_deps.keys())
            layer = list(cycle_nodes)
            for nid in layer:
                del id_to_deps[nid]
            layers.append(layer)
            placed |= set(layer)
            return layers, cycle_nodes
        for nid in layer:
            del id_to_deps[nid]
        layers.append(layer)
        placed |= set(layer)
    return layers, set()


def _auto_layout(nodes):
    """Layered layout with barycenter heuristic to minimise edge crossings.
    Returns {nid: (x, y)}."""
    if not nodes:
        return {}

    node_map = {n["id"]: n for n in nodes}
    successors = {n["id"]: [] for n in nodes}
    for n in nodes:
        for dep in n.get("after", []):
            if dep in successors:
                successors[dep].append(n["id"])

    layers, _ = _topo_layers(nodes)

    X_STEP, Y_STEP = 140, 90
    CENTER_X, Y_OFFSET = 300, 40

    rank = {}
    for layer in layers:
        n = len(layer)
        for i, nid in enumerate(layer):
            rank[nid] = float(i) - (n - 1) / 2.0

    def _recentre(layer, scores):
        ordered = sorted(layer, key=lambda x: scores.get(x, rank[x]))
        n = len(ordered)
        for i, nid in enumerate(ordered):
            rank[nid] = float(i) - (n - 1) / 2.0

    for _ in range(4):
        for col, layer in enumerate(layers):
            if col == 0:
                continue
            bar = {}
            for nid in layer:
                preds = [p for p in node_map[nid].get("after", []) if p in rank]
                bar[nid] = (sum(rank[p] for p in preds) / len(preds)) if preds else rank[nid]
            _recentre(layer, bar)

        for col in range(len(layers) - 2, -1, -1):
            layer = layers[col]
            bar = {}
            for nid in layer:
                succs = [s for s in successors.get(nid, []) if s in rank]
                bar[nid] = (sum(rank[s] for s in succs) / len(succs)) if succs else rank[nid]
            _recentre(layer, bar)

    return {
        nid: (round(CENTER_X + rank[nid] * X_STEP), round(Y_OFFSET + col * Y_STEP))
        for col, layer in enumerate(layers)
        for nid in layer
    }


def _node_dur(n):
    """Estimated execution duration of a single node in seconds."""
    if n.get("type") == "delay" or n.get("strategy") == "delay":
        return float(n.get("seconds", 1))
    taps = int(n.get("taps", 1))
    return _CLICK_OVERHEAD + taps * _TAP_INTERVAL


def _time_layout(nodes):
    """Time-proportional swimlane layout.
    Returns (pos: {nid:(x,y)}, time_marks: [(t_sec, x)], max_lane: int)."""
    if not nodes:
        return {}, [], 0
    layers, _cycle = _topo_layers(nodes)
    node_map = {n["id"]: n for n in nodes}

    finish_t, start_t = {}, {}
    for layer in layers:
        batch_start = 0.0
        for nid in layer:
            preds = [p for p in node_map[nid].get("after", []) if p in finish_t]
            if preds:
                batch_start = max(batch_start, max(finish_t[p] for p in preds))
        seq_t = batch_start
        for nid in layer:
            start_t[nid]  = batch_start
            finish_t[nid] = seq_t + _node_dur(node_map[nid])
            seq_t = finish_t[nid]

    layer_t = [start_t[layer[0]] for layer in layers]

    max_t      = max(finish_t.values(), default=1.0)
    px_per_sec = max(40.0, 1600.0 / max(max_t, 1.0))
    MIN_STEP   = 140
    X_OFFSET   = 50
    Y_OFFSET   = 58
    Y_STEP     = 75

    col_x = []
    for col, t in enumerate(layer_t):
        tx = round(X_OFFSET + t * px_per_sec)
        col_x.append(tx if col == 0 else max(col_x[-1] + MIN_STEP, tx))

    lane_of, layer_of = {}, {}
    for col, layer in enumerate(layers):
        for nid in layer:
            layer_of[nid] = col
        taken, assigned = set(), {}
        for nid in layer:
            preds = [p for p in node_map[nid].get("after", []) if p in lane_of]
            if preds:
                pref = lane_of[preds[0]]
                if pref not in taken:
                    assigned[nid] = pref
                    taken.add(pref)
        free = 0
        for nid in layer:
            if nid not in assigned:
                while free in taken:
                    free += 1
                assigned[nid] = free
                taken.add(free)
        lane_of.update(assigned)

    pos = {
        nid: (col_x[layer_of[nid]], round(Y_OFFSET + lane_of[nid] * Y_STEP))
        for nid in lane_of
    }

    time_marks, prev_t = [], -999.0
    for t, x in zip(layer_t, col_x):
        if (t - prev_t) >= 1.0:
            time_marks.append((round(t, 1), x))
            prev_t = t

    max_lane = max(lane_of.values(), default=0)
    return pos, time_marks, max_lane


def _node_label(nodes, nid):
    for n in nodes:
        if n["id"] == nid:
            return n.get("label", nid)
    return nid


class _NodeSignals(QObject):
    clicked = pyqtSignal(str)
    moved   = pyqtSignal(str, float, float)


class NodeItem(QGraphicsItem):
    W, H = 120, 36

    def __init__(self, nid, label, delay, x, y):
        super().__init__()
        self.nid = nid
        self.label = label
        self.delay = delay
        self.setPos(x, y)
        self.setAcceptHoverEvents(True)
        self.signals = _NodeSignals()
        self._highlighted = False

    def boundingRect(self):
        return QRectF(-2, -2, self.W + 12, self.H + 4)

    def paint(self, painter, option, widget=None):
        bg = QColor("#89b4fa") if self._highlighted else QColor("#313244")
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(QColor("#cdd6f4"), 1))
        painter.drawRoundedRect(QRectF(0, 0, self.W, self.H), 6, 6)
        painter.setPen(QColor("#cdd6f4"))
        text = self.label
        if self.delay:
            text += f" +{self.delay}s"
        painter.drawText(QRectF(0, 0, self.W, self.H), Qt.AlignCenter, text)
        painter.setBrush(QBrush(QColor("#a6e3a1")))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(self.W - 4, self.H / 2 - 6, 12, 12))

    def set_highlighted(self, v):
        self._highlighted = v
        self.update()

    def set_label(self, label):
        self.label = label
        self.update()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.signals.clicked.emit(self.nid)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, src: "NodeItem", dst: "NodeItem"):
        super().__init__()
        self.src = src
        self.dst = dst
        self.setPen(QPen(QColor("#89b4fa"), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(-1)
        src.signals.moved.connect(self._update)
        dst.signals.moved.connect(self._update)
        self._update()

    def _update(self, *_):
        sp = self.src.scenePos()
        dp = self.dst.scenePos()
        sx = sp.x() + NodeItem.W + 4
        sy = sp.y() + NodeItem.H / 2
        dx = dp.x() - 2
        dy = dp.y() + NodeItem.H / 2
        cx = (sx + dx) / 2
        path = QPainterPath(QPointF(sx, sy))
        path.cubicTo(QPointF(cx, sy), QPointF(cx, dy), QPointF(dx, dy))
        self.setPath(path)


class GraphCanvas(QGraphicsView):
    node_selected   = pyqtSignal(str)
    edge_created    = pyqtSignal(str, str)
    node_moved      = pyqtSignal(str, float, float)
    node_delete_req = pyqtSignal(str)
    node_unlink_req = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._nodes: dict = {}
        self._edges: list = []
        self._connect_src = None
        self._temp_edge = None
        self._pan_active = False
        self._pan_last = None
        self._zoom = 1.0
        self._scene.setSceneRect(-4000, -4000, 10000, 10000)
        self.setStyleSheet(
            "background: #11111b; border: 1px solid #313244; border-radius: 4px;"
        )
        self._overlay = QWidget(self)
        _ol = QHBoxLayout(self._overlay)
        _ol.setContentsMargins(4, 4, 4, 4)
        _ol.setSpacing(4)
        self._btn_relayout = QPushButton("⟳")
        self._btn_fit      = QPushButton("⊡")
        _btn_style = (
            "QPushButton{background:#1e1e2e;border:1px solid #45475a;"
            "border-radius:4px;color:#cdd6f4;font-size:14px;}"
            "QPushButton:hover{background:#313244;}"
        )
        for _b in (self._btn_relayout, self._btn_fit):
            _b.setFixedSize(28, 28)
            _b.setStyleSheet(_btn_style)
            _ol.addWidget(_b)
        self._overlay.adjustSize()
        self._overlay.raise_()

    def load_graph(self, nodes):
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._connect_src = None
        self._temp_edge = None
        if not nodes:
            return
        pos, time_marks, max_lane = _time_layout(nodes)
        _, cycle_nodes = _topo_layers(nodes)
        Y_STEP  = 75
        Y_TOTAL = (max_lane + 1) * Y_STEP + 30
        RULER_Y = 10

        if time_marks:
            x0    = time_marks[0][1]
            x_end = max(x for _, x in time_marks) + NodeItem.W + 60
            rl = self._scene.addLine(x0, RULER_Y + 20, x_end, RULER_Y + 20,
                                      QPen(QColor("#45475a"), 1))
            rl.setZValue(-2)

        for t, mx in time_marks:
            cx = mx + NodeItem.W / 2
            guide = self._scene.addLine(cx, RULER_Y + 20, cx, RULER_Y + 20 + Y_TOTAL,
                                         QPen(QColor("#2a2a3e"), 1, Qt.DotLine))
            guide.setZValue(-3)
            self._scene.addLine(cx, RULER_Y + 12, cx, RULER_Y + 20,
                                 QPen(QColor("#585b70"), 1)).setZValue(-2)
            label = f"{int(t)}s" if t == int(t) else f"{t:.1f}s"
            ti = self._scene.addSimpleText(label)
            ti.setBrush(QBrush(QColor("#6c7086")))
            ti.setPos(cx - len(label) * 3, RULER_Y)
            ti.setZValue(-2)
            tf = ti.font(); tf.setPointSize(8); ti.setFont(tf)

        if cycle_nodes:
            warn_text = f"⚠ Cycle detected: {', '.join(sorted(cycle_nodes))}"
            ti = self._scene.addSimpleText(warn_text)
            ti.setBrush(QBrush(QColor("#f38ba8")))
            ti.setPos(4, RULER_Y)
            tf = ti.font(); tf.setPointSize(9); tf.setBold(True); ti.setFont(tf)
            ti.setZValue(10)

        for n in nodes:
            x, y = pos.get(n["id"], (50, 60))
            item = NodeItem(n["id"], n.get("label", n["id"]), n.get("delay", 0), x, y)
            item.signals.clicked.connect(self.node_selected)
            if n["id"] in cycle_nodes:
                item.set_highlighted(True)
            self._scene.addItem(item)
            self._nodes[n["id"]] = item

        for n in nodes:
            for dep_id in n.get("after", []):
                if dep_id in self._nodes and n["id"] in self._nodes:
                    edge = EdgeItem(self._nodes[dep_id], self._nodes[n["id"]])
                    self._scene.addItem(edge)
                    self._edges.append(edge)

    def _port_node_at(self, view_pos):
        scene_pos = self.mapToScene(view_pos)
        for item in self._scene.items(scene_pos):
            if isinstance(item, NodeItem):
                local = item.mapFromScene(scene_pos)
                if abs(local.x() - item.W) < 14 and abs(local.y() - item.H / 2) < 14:
                    return item
        return None

    def _start_pan(self, pos):
        self._pan_active = True
        self._pan_last = pos
        self.setCursor(Qt.ClosedHandCursor)

    def _stop_pan(self):
        self._pan_active = False
        self._pan_last = None
        self.setCursor(Qt.ArrowCursor)

    def _do_pan(self, pos):
        delta = pos - self._pan_last
        self._pan_last = pos
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._start_pan(event.pos())
            return
        if event.button() == Qt.LeftButton:
            port_node = self._port_node_at(event.pos())
            if port_node:
                self._connect_src = port_node
                self._temp_edge = self._scene.addPath(
                    QPainterPath(),
                    QPen(QColor("#f38ba8"), 1.5, Qt.DashLine),
                )
                return
            if not self._scene.items(self.mapToScene(event.pos())):
                self._start_pan(event.pos())
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_active:
            self._do_pan(event.pos())
            return
        if self._connect_src and self._temp_edge:
            sp = self._connect_src.scenePos()
            sx = sp.x() + NodeItem.W + 4
            sy = sp.y() + NodeItem.H / 2
            ep = self.mapToScene(event.pos())
            path = QPainterPath(QPointF(sx, sy))
            path.lineTo(ep)
            self._temp_edge.setPath(path)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_active and event.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._stop_pan()
            return
        if self._connect_src and event.button() == Qt.LeftButton:
            if self._temp_edge:
                self._scene.removeItem(self._temp_edge)
                self._temp_edge = None
            scene_pos = self.mapToScene(event.pos())
            dst = None
            for item in self._scene.items(scene_pos):
                if isinstance(item, NodeItem) and item is not self._connect_src:
                    dst = item
                    break
            if dst:
                self.edge_created.emit(self._connect_src.nid, dst.nid)
            self._connect_src = None
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        dx = event.angleDelta().x()
        dy = event.angleDelta().y()
        if dy != 0:
            steps = dy / 120.0
            new_zoom = max(0.05, min(8.0, self._zoom * (1.10 ** steps)))
            self.scale(new_zoom / self._zoom, new_zoom / self._zoom)
            self._zoom = new_zoom
        if dx != 0:
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - dx
            )

    def showEvent(self, event):
        super().showEvent(event)
        if self._nodes:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self.fit_view)

    def fit_view(self):
        if not self.isVisible():
            return
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            return
        self.fitInView(rect.adjusted(-24, -24, 24, 24), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        ow = self._overlay.sizeHint().width()
        self._overlay.move(self.width() - ow - 6, 6)

    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        node = None
        for item in self._scene.items(scene_pos):
            if isinstance(item, NodeItem):
                node = item
                break
        if not node:
            return
        m = QMenu(self)
        m.addAction("Delete Node",          lambda: self.node_delete_req.emit(node.nid))
        m.addAction("Remove dependency...", lambda: self.node_unlink_req.emit(node.nid))
        m.exec_(event.globalPos())
        event.accept()

    def highlight_node(self, nid):
        for nid2, item in self._nodes.items():
            item.set_highlighted(nid2 == nid)

    def update_node_label(self, nid, label):
        if nid in self._nodes:
            self._nodes[nid].set_label(label)
