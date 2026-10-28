from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.core.config import qsettings
from app.core.review_sheet import SHEET_COLUMNS, VIEW_KEY, VIEWS, pickable_columns
from app.core.template_renderer import TemplatePreset

SHIPPED_TABLE_PRESET = "A4 review sheet"
_MODE = "inventory-table"


def _stored_columns(view: str) -> set[str]:
    raw = qsettings().value(f"{_MODE}/columns/{view}")
    allowed = pickable_columns(view)
    picked = {
        key
        for key in (raw.split(",") if isinstance(raw, str) else [])
        if key in allowed
    }
    # ponytail: garbage or empty settings fall back to all pickable columns
    return picked or set(allowed)


class ExportSheetDialog(QDialog):
    def __init__(self, presets: list[TemplatePreset], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export A4 review sheet")
        settings = qsettings()

        self.template_combo = QComboBox()
        for preset in presets:
            self.template_combo.addItem(preset.name, preset)
        remembered = settings.value(f"{_MODE}/last_template")
        index = (
            self.template_combo.findText(remembered)
            if isinstance(remembered, str)
            else -1
        )
        if index < 0:
            index = self.template_combo.findText(SHIPPED_TABLE_PRESET)
        if index >= 0:
            self.template_combo.setCurrentIndex(index)

        stored_view = settings.value(f"{_MODE}/view")
        self._view = stored_view if stored_view in VIEWS else "position"
        self._checked = {view: _stored_columns(view) for view in VIEWS}

        self.view_buttons: dict[str, QRadioButton] = {}
        view_row = QHBoxLayout()
        group = QButtonGroup(self)
        for view, label in VIEWS.items():
            button = QRadioButton(label)
            self.view_buttons[view] = button
            group.addButton(button)
            view_row.addWidget(button)
        self.view_buttons[self._view].setChecked(True)

        self.column_boxes: dict[str, QCheckBox] = {}
        columns_grid = QGridLayout()
        for index, key in enumerate(SHEET_COLUMNS):
            box = QCheckBox(SHEET_COLUMNS[key])
            self.column_boxes[key] = box
            columns_grid.addWidget(box, index // 2, index % 2)
        self._load_view_columns()

        form = QFormLayout()
        form.addRow("Template", self.template_combo)
        view_widget = QWidget()
        view_widget.setLayout(view_row)
        form.addRow("View", view_widget)
        columns_widget = QWidget()
        columns_widget.setLayout(columns_grid)
        form.addRow("Columns", columns_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        for box in self.column_boxes.values():
            box.toggled.connect(self._update_ok)
        for view, button in self.view_buttons.items():
            button.toggled.connect(
                lambda checked, view=view: checked and self._switch_view(view)
            )
        self._update_ok()

    def _load_view_columns(self) -> None:
        # Hides the key this view groups by, so the sheet never lists it twice.
        hidden = VIEW_KEY[self._view]
        for key, box in self.column_boxes.items():
            box.setChecked(key in self._checked[self._view])
            box.setHidden(key == hidden)

    def _switch_view(self, view: str) -> None:
        self._remember_visible()
        self._view = view
        self._load_view_columns()
        self._update_ok()

    def _remember_visible(self) -> None:
        self._checked[self._view] = {
            key
            for key in pickable_columns(self._view)
            if self.column_boxes[key].isChecked()
        }

    def _update_ok(self) -> None:
        self.ok_button.setEnabled(bool(self._visible_columns()))

    def _visible_columns(self) -> list[str]:
        return [
            key
            for key in pickable_columns(self._view)
            if self.column_boxes[key].isChecked()
        ]

    def options(self) -> tuple[TemplatePreset, str, list[str]]:
        return self.template_combo.currentData(), self._view, self._visible_columns()

    def accept(self) -> None:
        self._remember_visible()
        settings = qsettings()
        settings.setValue(f"{_MODE}/last_template", self.template_combo.currentText())
        settings.setValue(f"{_MODE}/view", self._view)
        for view in VIEWS:
            columns = [key for key in SHEET_COLUMNS if key in self._checked[view]]
            settings.setValue(f"{_MODE}/columns/{view}", ",".join(columns))
        super().accept()


def ask_export_options(
    parent, presets: list[TemplatePreset]
) -> tuple[TemplatePreset, str, list[str]] | None:
    dialog = ExportSheetDialog(presets, parent)
    if dialog.exec():
        return dialog.options()
    return None
