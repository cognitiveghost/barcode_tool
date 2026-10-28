"""Template builder dialog: drag-on-canvas editor for one layout (1 scene unit = 1 mm).

Every change goes through ``_commit``, which pushes the previous layout as a JSON snapshot
so ``undo`` can restore it. Items are rebuilt from the layout after each commit.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.layout_builder import default_element, normalise_layout, sample_for

INK = QColor("#000")
ACCENT = QColor("#1a73e8")
PAPER_SURROUND = QColor("#9aa0a6")
GRID_1MM = QColor("#e8e8e8")
GRID_10MM = QColor("#c8c8c8")
SAFE_MARGIN = QColor("#d0021b")
NUDGE_MM = 0.5
MARGIN_MM = 5
PALETTE = (
    ("Text", "text"),
    ("Barcode", "barcode"),
    ("QR", "qr"),
    ("Box", "box"),
    ("Line", "line"),
)
_ALIGN = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight}


def _display_rect(el: dict) -> QRectF:
    if el["type"] == "line":
        t = el["thickness_mm"]
        return (
            QRectF(0, 0, el["w_mm"], t)
            if el["orientation"] == "h"
            else QRectF(0, 0, t, el["h_mm"])
        )
    return QRectF(0, 0, el["w_mm"], el["h_mm"])


def _draw_text(
    painter, rect: QRectF, text: str, size_mm: float, flags, bold: bool
) -> None:
    # Font at 100 px, scaled so one em is size_mm: keeps the text in mm scene units.
    scale = size_mm / 100
    painter.setClipRect(rect)
    painter.save()
    painter.scale(scale, scale)
    font = QFont("JetBrains Mono")
    font.setPixelSize(100)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(INK)
    painter.drawText(
        QRectF(0, 0, rect.width() / scale, rect.height() / scale), flags, text
    )
    painter.restore()
    painter.setClipping(False)


class ElementItem(QGraphicsRectItem):
    def __init__(self, dialog: TemplateBuilderDialog, index: int, el: dict):
        super().__init__(_display_rect(el))
        self.dialog = dialog
        self.index = index
        self.element = el
        self.setPos(el["x_mm"], el["y_mm"])
        self.setFlag(QGraphicsItem.ItemIsMovable, True)

    def paint(self, painter, option, widget=None):
        rect = self.rect()
        el = self.element
        painter.setRenderHint(QPainter.TextAntialiasing)
        if el["type"] == "text":
            flags = _ALIGN[el["align"]] | Qt.AlignVCenter
            if el["wrap"]:
                flags |= Qt.TextWordWrap
            text = el["content"].upper() if el["uppercase"] else el["content"]
            _draw_text(painter, rect, text, el["max_mm"], flags, el["bold"])
        elif el["type"] in ("barcode", "qr"):
            painter.fillRect(rect, QBrush(INK, Qt.BDiagPattern))
            _draw_text(painter, rect, el["field"], 3, Qt.AlignCenter, False)
        elif el["type"] == "box":
            t = el["thickness_mm"]
            painter.setPen(QPen(INK, t))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(t / 2, t / 2, -t / 2, -t / 2))
        elif el["type"] == "line":
            painter.fillRect(rect, INK)
        if self.dialog.selected == self.index:
            painter.setClipping(False)
            painter.setPen(QPen(ACCENT, 0))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        self.dialog.select(self.index)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        QTimer.singleShot(0, self.commit_drag)

    def commit_drag(self) -> None:
        x, y = max(0, round(self.pos().x())), max(0, round(self.pos().y()))
        if (x, y) == (self.element["x_mm"], self.element["y_mm"]):
            return
        self.dialog.set_geometry(
            self.index, x, y, self.element["w_mm"], self.element["h_mm"]
        )

    def resize_to(self, w: float, h: float) -> None:
        if self.element["type"] == "line":
            t = self.element["thickness_mm"]
            w, h = (w, t) if self.element["orientation"] == "h" else (t, h)
        self.setRect(0, 0, max(w, 0), max(h, 0))


class _ResizeHandle(QGraphicsRectItem):
    """2 mm square at the bottom-right of the selected element."""

    def __init__(self, parent_item: ElementItem):
        super().__init__(QRectF(0, 0, 2, 2), parent_item)
        self.setBrush(QBrush(ACCENT))
        self.setPen(QPen(Qt.NoPen))
        self.setCursor(Qt.SizeFDiagCursor)
        self.setZValue(1)
        self.drag_to(parent_item.rect().width(), parent_item.rect().height())

    def drag_to(self, w: float, h: float) -> None:
        parent = self.parentItem()
        parent.resize_to(w, h)
        r = parent.rect()
        self.setPos(r.width() - 2, r.height() - 2)

    def commit_resize(self) -> None:
        parent = self.parentItem()
        r = parent.rect()
        parent.dialog.set_geometry(
            parent.index,
            round(parent.pos().x()),
            round(parent.pos().y()),
            max(1, round(r.width())),
            max(1, round(r.height())),
        )

    def mousePressEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        p = self.parentItem().mapFromScene(event.scenePos())
        # The cursor sits on the handle centre, 1 mm in from the corner.
        self.drag_to(p.x() + 1, p.y() + 1)
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()
        QTimer.singleShot(0, self.commit_resize)


_NUDGE = {
    Qt.Key_Left: (-NUDGE_MM, 0),
    Qt.Key_Right: (NUDGE_MM, 0),
    Qt.Key_Up: (0, -NUDGE_MM),
    Qt.Key_Down: (0, NUDGE_MM),
}


class _Canvas(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, dialog: TemplateBuilderDialog):
        super().__init__(scene)
        self._dialog = dialog

    def keyPressEvent(self, event):
        key = event.key()
        if key in _NUDGE:
            self._dialog.move_selected(*_NUDGE[key])
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            self._dialog.delete_selected()
        else:
            super().keyPressEvent(event)


class TemplateBuilderDialog(QDialog):
    def __init__(
        self,
        layout: dict,
        shared_folder: Path,
        *,
        edit_folder: Path | None = None,
        sample: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Template builder")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.layout = normalise_layout(layout)
        self.shared_folder = shared_folder
        self.edit_folder = edit_folder
        self.sample = sample_for(self.layout["mode"], sample)
        self.saved_name: str | None = None
        self.dirty = False
        self.selected: int | None = None
        self.items: list[ElementItem] = []
        self._handle: _ResizeHandle | None = None
        self._undo: list[str] = []

        self.scene = QGraphicsScene(self)
        self.view = _Canvas(self.scene, self)
        self.view.setBackgroundBrush(PAPER_SURROUND)
        self.view.setRenderHint(QPainter.Antialiasing)
        QShortcut(QKeySequence.Undo, self, self.undo)

        self.top_bar = QHBoxLayout()
        self.properties_panel = QWidget()
        palette = QVBoxLayout()
        for label, type_ in PALETTE:
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, t=type_: self.add_element(t))
            palette.addWidget(button)
        palette.addStretch(1)
        body = QHBoxLayout()
        body.addLayout(palette)
        body.addWidget(self.view, 1)
        body.addWidget(self.properties_panel)
        root = QVBoxLayout(self)
        root.addLayout(self.top_bar)
        root.addLayout(body, 1)

        self._rebuild_scene()

    # --- mutations: every one goes through _commit ---

    def _commit(self, new_layout: dict) -> None:
        layout = normalise_layout(new_layout)  # raises before any state changes
        self._undo.append(json.dumps(self.layout))
        self.layout = layout
        self.dirty = True
        self._rebuild_scene()

    def add_element(self, type_: str) -> int:
        new = copy.deepcopy(self.layout)
        new["elements"].append(default_element(type_, self.layout["mode"]))
        self._commit(new)
        index = len(self.layout["elements"]) - 1
        self.select(index)
        return index

    def set_geometry(self, index: int, x: float, y: float, w: float, h: float) -> None:
        new = copy.deepcopy(self.layout)
        new["elements"][index].update(x_mm=max(0, x), y_mm=max(0, y), w_mm=w, h_mm=h)
        self._commit(new)

    def update_element(self, index: int, **props) -> None:
        new = copy.deepcopy(self.layout)
        new["elements"][index].update(props)
        self._commit(new)

    def move_selected(self, dx: float, dy: float) -> None:
        if self.selected is None:
            return
        el = self.layout["elements"][self.selected]
        self.set_geometry(
            self.selected,
            max(0, el["x_mm"] + dx),
            max(0, el["y_mm"] + dy),
            el["w_mm"],
            el["h_mm"],
        )

    def delete_selected(self) -> None:
        if self.selected is None:
            return
        new = copy.deepcopy(self.layout)
        del new["elements"][self.selected]
        self.selected = None
        self._commit(new)

    def set_label_size(self, w: float, h: float) -> None:
        new = copy.deepcopy(self.layout)
        new.update(width_mm=w, height_mm=h)
        self._commit(new)

    def undo(self) -> None:
        if not self._undo:
            return
        self.layout = json.loads(self._undo.pop())
        self._rebuild_scene()

    # --- selection and drawing ---

    def select(self, index: int | None) -> None:
        self.selected = index
        self._apply_selection()

    def _apply_selection(self) -> None:
        if self._handle is not None:
            self.scene.removeItem(self._handle)
            self._handle = None
        for item in self.items:
            item.update()
        if self.selected is not None:
            self._handle = _ResizeHandle(self.items[self.selected])

    def _rebuild_scene(self) -> None:
        if self.selected is not None and self.selected >= len(self.layout["elements"]):
            self.selected = None
        self.scene.clear()
        self.items = []
        self._handle = None
        w, h = self.layout["width_mm"], self.layout["height_mm"]
        self.scene.setSceneRect(
            QRectF(-MARGIN_MM, -MARGIN_MM, w + 2 * MARGIN_MM, h + 2 * MARGIN_MM)
        )
        paper = QGraphicsRectItem(QRectF(0, 0, w, h))
        paper.setBrush(QBrush(Qt.white))
        paper.setPen(QPen(Qt.NoPen))
        self.scene.addItem(paper)
        for x in range(int(w) + 1):
            self.scene.addLine(
                x, 0, x, h, QPen(GRID_10MM if x % 10 == 0 else GRID_1MM, 0)
            )
        for y in range(int(h) + 1):
            self.scene.addLine(
                0, y, w, y, QPen(GRID_10MM if y % 10 == 0 else GRID_1MM, 0)
            )
        self.scene.addRect(
            QRectF(1.25, 1.25, w - 2.5, h - 2.5), QPen(SAFE_MARGIN, 0, Qt.DashLine)
        )
        for i, el in enumerate(self.layout["elements"]):
            item = ElementItem(self, i, el)
            self.scene.addItem(item)
            self.items.append(item)
        self._apply_selection()
        self._fit()

    def _fit(self) -> None:
        w, h = self.layout["width_mm"], self.layout["height_mm"]
        self.view.fitInView(
            QRectF(-MARGIN_MM, -MARGIN_MM, w + 2 * MARGIN_MM, h + 2 * MARGIN_MM),
            Qt.KeepAspectRatio,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()
