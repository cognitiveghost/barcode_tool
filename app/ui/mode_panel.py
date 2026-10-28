from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QToolButton,
    QWidget,
)

from app.core.config import qsettings, shared_folder
from app.core.layout_builder import is_app_owned, load_layout, new_layout
from app.core.template_renderer import TemplatePreset, list_presets, render_records
from app.ui.template_builder import TemplateBuilderDialog

MAX_LABELS_PER_RENDER = 2000
CONFIRM_LABELS_ABOVE = 300
_RENDER_CHUNK_SIZE = 50
_ESTIMATED_SECONDS_PER_LABEL = 0.02


def check_label_count(count: int) -> None:
    if count > MAX_LABELS_PER_RENDER:
        raise ValueError(
            f"{count} labels is more than the {MAX_LABELS_PER_RENDER} allowed in one batch - "
            "split it into smaller batches."
        )


class ModePanel(QWidget):
    """Shared render, confirm and template-list code for the label panels.

    Subclasses set the class attributes below and build their own widgets
    before calling refresh_from_settings(), which expects warehouse_combo and
    preset_combo to exist.
    """

    MODE: str
    LARGE_BATCH_TITLE: str
    LARGE_BATCH_VERB: str
    CANCELLED: type[Exception]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template_button = QToolButton()
        self.template_button.setText("Template")
        self.template_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.new_action = QAction("New…", self)
        self.new_action.triggered.connect(lambda _=False: self.open_builder("new"))
        self.edit_action = QAction("Edit…", self)
        self.edit_action.triggered.connect(lambda _=False: self.open_builder("edit"))
        self.duplicate_action = QAction("Duplicate…", self)
        self.duplicate_action.triggered.connect(lambda _=False: self.open_builder("duplicate"))
        menu = QMenu(self.template_button)
        for action in (self.new_action, self.edit_action, self.duplicate_action):
            menu.addAction(action)
        menu.aboutToShow.connect(self._update_template_actions)
        self.template_button.setMenu(menu)

    def _template_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.preset_combo, 1)
        layout.addWidget(self.template_button)
        self.preset_combo.currentIndexChanged.connect(
            lambda _index=0: self._update_template_actions()
        )
        self._update_template_actions()
        return row

    def _selected_folder(self) -> Path | None:
        preset: TemplatePreset | None = self.preset_combo.currentData()
        return preset.template_path.parent if preset is not None else None

    def _update_template_actions(self) -> None:
        folder = self._selected_folder()
        has_builder = folder is not None and (folder / "layout.json").exists()
        self.edit_action.setEnabled(has_builder and not is_app_owned(self.MODE, folder.name))
        self.duplicate_action.setEnabled(has_builder)

    def open_builder(self, kind: str) -> None:
        """Open the template builder for "new", "edit" or "duplicate" of the selected preset."""
        if kind == "new":
            layout, edit_folder = new_layout(self.MODE), None
        else:
            folder = self._selected_folder()
            try:
                layout = load_layout(folder)
            except ValueError as error:
                QMessageBox.warning(self, "Can't open template", str(error))
                return
            if kind == "duplicate":
                layout["name"] = f"Copy of {layout['name']}"
            edit_folder = folder if kind == "edit" else None

        dialog = TemplateBuilderDialog(
            layout,
            shared_folder(self._settings),
            edit_folder=edit_folder,
            sample=self.sample_record(),
            parent=self,
        )
        if dialog.exec() and dialog.saved_name:
            qsettings().setValue(f"{self.MODE}/last_template", dialog.saved_name)
            self.refresh_from_settings(self._settings)

    def refresh_from_settings(self, settings: dict) -> None:
        self._settings = settings

        self.warehouse_combo.clear()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])

        folder = shared_folder(settings)
        self.preset_combo.clear()
        for preset in list_presets(folder, self.MODE):
            self.preset_combo.addItem(preset.name, preset)
        remembered_name = qsettings().value(f"{self.MODE}/last_template")
        if remembered_name is not None:
            index = self.preset_combo.findText(remembered_name)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)

        if self.preset_combo.count() == 0:
            self._warn_no_presets(folder)

    def _warn_no_presets(self, folder) -> None:
        window = self.window()
        if not hasattr(window, "statusBar"):
            return  # not embedded in a QMainWindow (e.g. a standalone test)
        window.statusBar().showMessage(
            f"No label templates found in '{folder}' - check the "
            "shared folder's templates directory or your permissions."
        )

    def _show_status(self, message: str) -> None:
        window = self.window()
        if not hasattr(window, "statusBar"):
            return  # not embedded in a QMainWindow (e.g. a standalone test)
        window.statusBar().showMessage(message, 5000)

    def _on_preset_selected(self, index: int) -> None:
        qsettings().setValue(f"{self.MODE}/last_template", self.preset_combo.itemText(index))

    def render_labels(self, preset: TemplatePreset, records: list[dict]) -> list[Image.Image]:
        check_label_count(len(records))
        if len(records) > CONFIRM_LABELS_ABOVE:
            return self._render_with_progress(preset, records)
        return render_records(preset, records)

    def _render_with_progress(
        self, preset: TemplatePreset, records: list[dict]
    ) -> list[Image.Image]:
        estimated_minutes = max(1, round(len(records) * _ESTIMATED_SECONDS_PER_LABEL / 60))
        answer = QMessageBox.question(
            self,
            self.LARGE_BATCH_TITLE,
            f"{self.LARGE_BATCH_VERB} {len(records)} labels? This will take about "
            f"{estimated_minutes} minute{'s' if estimated_minutes != 1 else ''}.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            raise self.CANCELLED()

        progress = QProgressDialog("Rendering labels...", "Cancel", 0, len(records), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        images: list[Image.Image] = []
        try:
            for start in range(0, len(records), _RENDER_CHUNK_SIZE):
                if progress.wasCanceled():
                    raise self.CANCELLED()
                chunk = records[start : start + _RENDER_CHUNK_SIZE]
                images.extend(render_records(preset, chunk))
                progress.setValue(min(start + _RENDER_CHUNK_SIZE, len(records)))
        finally:
            progress.close()
        return images
