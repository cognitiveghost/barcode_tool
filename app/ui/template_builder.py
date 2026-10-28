"""Template builder dialog: drag-on-canvas editor for one layout (1 scene unit = 1 mm).

Every change goes through ``_commit``, which pushes the previous layout as a JSON snapshot
so ``undo`` can restore it. Items are rebuilt from the layout after each commit.
"""

from __future__ import annotations

import copy
import functools
import json
from pathlib import Path

from barcode.errors import BarcodeError
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
    QTransform,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.layout_builder import (
    black_block_mm,
    check_save_target,
    default_element,
    mode_fields,
    normalise_layout,
    render_sample,
    sample_for,
    save_layout,
)

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
FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
SIZES = [(150, 100), (100, 150), (100, 100), (100, 50), (68, 38), (58, 40), (50, 30)]


def _spin(
    lo: float, hi: float, value: float, step: float = 0.5, decimals: int = 1
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(lo, hi)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setValue(value)
    return spin


def _display_rect(el: dict) -> QRectF:
    if el["type"] == "line":
        t = el["thickness_mm"]
        return (
            QRectF(0, 0, el["w_mm"], t)
            if el["orientation"] == "h"
            else QRectF(0, 0, t, el["h_mm"])
        )
    return QRectF(0, 0, el["w_mm"], el["h_mm"])


@functools.cache
def _register_fonts() -> None:
    """Load the bundled font once, so the canvas draws text like the printed label."""
    for ttf in FONTS.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(ttf))


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

    def boundingRect(self) -> QRectF:
        # A thin line gets a 1 mm grab margin each side, so it can be clicked.
        if self.element["type"] == "line":
            return self.rect().adjusted(-1, -1, 1, 1)
        return super().boundingRect()

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        if self.element["type"] == "box":
            # Only the frame is clickable (odd-even fill), so elements inside stay reachable.
            grab = max(self.element["thickness_mm"], 1)
            path.addRect(self.rect().adjusted(grab, grab, -grab, -grab))
        return path

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
            self.setPos(x, y)  # snap back onto the grid
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
        _register_fonts()
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
        self._preview_item: QGraphicsPixmapItem | None = None
        self._undo: list[str] = []

        self.scene = QGraphicsScene(self)
        self.view = _Canvas(self.scene, self)
        self.view.setBackgroundBrush(PAPER_SURROUND)
        self.view.setRenderHint(QPainter.Antialiasing)
        QShortcut(QKeySequence.Undo, self, self.undo)

        self.name_edit = QLineEdit(self.layout["name"])
        self.name_edit.editingFinished.connect(self._on_name_edited)
        self.mode_label = QLabel(f"Mode: {self.layout['mode']}")
        self.size_combo = QComboBox()
        self.size_combo.addItems([f"{w} × {h} mm" for w, h in SIZES] + ["Custom"])
        self.size_combo.currentIndexChanged.connect(self._on_size_picked)
        self.width_spin = _spin(10, 300, self.layout["width_mm"], step=1)
        self.height_spin = _spin(10, 300, self.layout["height_mm"], step=1)
        self.width_spin.editingFinished.connect(self._on_size_edited)
        self.height_spin.editingFinished.connect(self._on_size_edited)
        self.preview_button = QPushButton("Preview")
        self.preview_button.setCheckable(True)
        self.preview_button.clicked.connect(self.set_preview)
        self.undo_button = QPushButton("Undo")
        self.undo_button.clicked.connect(lambda _=False: self.undo())
        self.save_button = QPushButton("Save template")
        self.save_button.clicked.connect(lambda _=False: self.save())
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #d93025;")
        self.top_bar = QHBoxLayout()
        for widget in (
            QLabel("Name"),
            self.name_edit,
            self.mode_label,
            self.size_combo,
            QLabel("W"),
            self.width_spin,
            QLabel("H"),
            self.height_spin,
            self.preview_button,
            self.undo_button,
            self.save_button,
        ):
            self.top_bar.addWidget(widget)
        self.top_bar.addStretch(1)
        self.properties_panel = QWidget()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #d93025;")
        self.error_label.setVisible(False)
        self.prop_widgets: dict[str, QWidget] = {}
        self._props_body: QWidget | None = None
        self._props_column = QVBoxLayout(self.properties_panel)
        self._props_column.addWidget(self.error_label)
        self._props_column.addStretch(1)
        palette = QVBoxLayout()
        self.palette_buttons: list[QPushButton] = []
        for label, type_ in PALETTE:
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, t=type_: self.add_element(t))
            palette.addWidget(button)
            self.palette_buttons.append(button)
        palette.addStretch(1)
        body = QHBoxLayout()
        body.addLayout(palette)
        body.addWidget(self.view, 1)
        body.addWidget(self.properties_panel)
        root = QVBoxLayout(self)
        root.addLayout(self.top_bar)
        root.addLayout(body, 1)
        root.addWidget(self.status_label)

        self._rebuild_scene()

    # --- mutations: every one goes through _commit ---

    def _commit(self, new_layout: dict) -> None:
        if self.preview_button.isChecked():  # editing is locked while previewing
            return
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
        if not self._undo or self.preview_button.isChecked():
            return
        self.layout = json.loads(self._undo.pop())
        self.dirty = bool(self._undo)  # the stack starts at the layout the dialog opened with
        self._rebuild_scene()

    # --- preview and save ---

    def set_preview(self, on: bool) -> None:
        if self._preview_item is not None:
            self.scene.removeItem(self._preview_item)
            self._preview_item = None
        self.status_label.clear()
        shown = False
        if on:
            try:
                image = render_sample(self.layout, self.sample)
            except (ValueError, OSError, BarcodeError) as error:
                self.status_label.setText(f"Preview failed: {error}")
            else:
                item = QGraphicsPixmapItem(
                    QPixmap.fromImage(ImageQt(image.convert("L")))
                )
                item.setTransform(
                    QTransform.fromScale(
                        self.layout["width_mm"] / image.width,
                        self.layout["height_mm"] / image.height,
                    )
                )
                self.scene.addItem(item)
                self._preview_item = item
                shown = True
        self.preview_button.setChecked(shown)
        for item in self.items:
            item.setVisible(not shown)
        for widget in (
            *self.palette_buttons,
            self.name_edit,
            self.size_combo,
            self.width_spin,
            self.height_spin,
            self.undo_button,
            self.properties_panel,
        ):
            widget.setEnabled(not shown)

    def save(self) -> Path | None:
        self._on_name_edited()
        if not self.layout["name"].strip():
            QMessageBox.warning(
                self, "Can't save template", "Give the template a name first."
            )
            return None
        try:
            folder = check_save_target(
                self.shared_folder, self.layout, self.edit_folder
            )
            black = black_block_mm(self.layout, self.sample)
        except (ValueError, OSError, BarcodeError) as error:
            QMessageBox.warning(self, "Can't save template", str(error))
            return None
        if black is not None:
            x, y = black
            answer = QMessageBox.question(
                self,
                "Solid black area",
                f"The label has a solid black area at x={x} mm, y={y} mm. Large black "
                "areas leave residue on the thermal print head. Save anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return None
        try:
            save_layout(self.layout, folder)
        except OSError as error:
            QMessageBox.warning(self, "Can't save template", str(error))
            return None
        self.saved_name = self.layout["name"]
        self.dirty = False
        self.accept()
        return folder

    def reject(self) -> None:
        if (
            self.dirty
            and QMessageBox.question(
                self,
                "Discard changes",
                "Discard unsaved changes?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        super().reject()

    # --- selection and drawing ---

    def select(self, index: int | None) -> None:
        self.selected = index
        self._apply_selection()

    # --- top bar ---

    def _attempt(self, fn, *args, **kwargs) -> None:
        """Run a mutator; a validation error shows inline instead of raising."""
        try:
            fn(*args, **kwargs)
        except ValueError as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)

    # --- properties panel ---

    def _edit(self, index: int, **props) -> None:
        if index >= len(self.layout["elements"]):
            return
        current = self.layout["elements"][index]
        if all(current[key] == value for key, value in props.items()):
            return
        self._attempt(self.update_element, index, **props)

    def _set_orientation(self, index: int, orientation: str) -> None:
        el = self.layout["elements"][index]
        if orientation == el["orientation"]:
            return
        length = el["w_mm"] if el["orientation"] == "h" else el["h_mm"]
        new = copy.deepcopy(self.layout)
        new["elements"][index].update(
            orientation=orientation,
            w_mm=length if orientation == "h" else 0,
            h_mm=0 if orientation == "h" else length,
        )
        self._attempt(self._commit, new)

    def _refresh_properties(self) -> None:
        # Tabbing between fields commits and rebuilds the form; keep focus on the same field.
        focused = next((k for k, w in self.prop_widgets.items() if w.hasFocus()), None)
        if self._props_body is not None:
            self._props_body.deleteLater()
        self.error_label.setVisible(False)
        self.prop_widgets = {}
        body = QWidget()
        column = QVBoxLayout(body)
        if self.selected is None:
            column.addWidget(QLabel("Click an element, or add one from the left."))
        else:
            self._build_element_form(column, self.selected)
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda _=False: self.delete_selected())
            column.addWidget(delete)
        self._props_body = body
        self._props_column.insertWidget(0, body)
        if focused in self.prop_widgets:
            self.prop_widgets[focused].setFocus()

    def _build_element_form(self, column: QVBoxLayout, index: int) -> None:
        el = self.layout["elements"][index]
        kind = el["type"]
        form = QFormLayout()
        column.addLayout(form)

        def add(key: str, label: str, widget: QWidget) -> None:
            self.prop_widgets[key] = widget
            form.addRow(label, widget)

        def spin_row(key, label, lo, hi, step=0.5, decimals=1) -> None:
            spin = _spin(lo, hi, el[key], step, decimals)
            spin.editingFinished.connect(
                lambda: self._edit(index, **{key: spin.value()})
            )
            add(key, label, spin)

        def check_row(key: str, label: str) -> None:
            box = QCheckBox()
            box.setChecked(el[key])
            box.toggled.connect(lambda on: self._edit(index, **{key: on}))
            add(key, label, box)

        spin_row("x_mm", "X mm", 0, 300)
        spin_row("y_mm", "Y mm", 0, 300)
        if kind == "line":
            axis = "w_mm" if el["orientation"] == "h" else "h_mm"
            spin_row(axis, "Length mm", 1, 300)
        else:
            spin_row("w_mm", "W mm", 1, 300)
            spin_row("h_mm", "H mm", 1, 300)

        if kind == "text":
            content = QLineEdit(el["content"])
            content.editingFinished.connect(
                lambda: self._edit(index, content=content.text())
            )
            add("content", "Content", content)
            insert = QComboBox()
            insert.addItems(["Insert field", *mode_fields(self.layout["mode"])])

            def insert_field(i: int) -> None:
                if i > 0:
                    field = insert.itemText(i)
                    self._edit(index, content=f"{content.text()}{{{field}}}")

            add("insert_field", "Insert field", insert)
            insert.currentIndexChanged.connect(insert_field)
            spin_row("max_mm", "Max mm", 0.1, 300)
            spin_row("min_mm", "Min mm", 0.1, 300)
            check_row("wrap", "Wrap")
            check_row("bold", "Bold")
            check_row("uppercase", "Uppercase")
            align = QComboBox()
            for text, value in (("Left", "left"), ("Center", "center"), ("Right", "right")):
                align.addItem(text, value)
            align.setCurrentIndex(align.findData(el["align"]))
            align.currentIndexChanged.connect(
                lambda _i: self._edit(index, align=align.currentData())
            )
            add("align", "Align", align)
            spin_row("letter_spacing_mm", "Letter spacing mm", 0, 10, step=0.1)
        elif kind in ("barcode", "qr"):
            field = QComboBox()
            field.addItems(mode_fields(self.layout["mode"]))
            field.setCurrentText(el["field"])
            field.currentIndexChanged.connect(
                lambda _i: self._edit(index, field=field.currentText())
            )
            add("field", "Field", field)
        elif kind == "box":
            spin_row("thickness_mm", "Thickness mm", 0.3, 0.5, step=0.05, decimals=2)
        elif kind == "line":
            orientation = QComboBox()
            orientation.addItem("Horizontal", "h")
            orientation.addItem("Vertical", "v")
            orientation.setCurrentIndex(orientation.findData(el["orientation"]))
            orientation.currentIndexChanged.connect(
                lambda _i: self._set_orientation(index, orientation.currentData())
            )
            add("orientation", "Orientation", orientation)
            spin_row("thickness_mm", "Thickness mm", 0.3, 0.5, step=0.05, decimals=2)

    def _on_name_edited(self) -> None:
        name = self.name_edit.text()
        if name != self.layout["name"]:
            new = copy.deepcopy(self.layout)
            new["name"] = name
            self._attempt(self._commit, new)

    def _on_size_picked(self, index: int) -> None:
        if index < len(SIZES):
            self._set_size(*SIZES[index])

    def _on_size_edited(self) -> None:
        self._set_size(self.width_spin.value(), self.height_spin.value())

    def _set_size(self, w: float, h: float) -> None:
        if (w, h) != (self.layout["width_mm"], self.layout["height_mm"]):
            self._attempt(self.set_label_size, w, h)

    def _refresh_top_bar(self) -> None:
        self.name_edit.setText(self.layout["name"])
        self.width_spin.setValue(self.layout["width_mm"])
        self.height_spin.setValue(self.layout["height_mm"])
        size = (self.layout["width_mm"], self.layout["height_mm"])
        index = SIZES.index(size) if size in SIZES else len(SIZES)
        self.size_combo.blockSignals(True)
        self.size_combo.setCurrentIndex(index)
        self.size_combo.blockSignals(False)
        self.undo_button.setEnabled(bool(self._undo))

    def _apply_selection(self) -> None:
        if self._handle is not None:
            self.scene.removeItem(self._handle)
            self._handle = None
        for item in self.items:
            item.update()
        if self.selected is not None:
            self._handle = _ResizeHandle(self.items[self.selected])
        self._refresh_properties()

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
        self._refresh_top_bar()
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
