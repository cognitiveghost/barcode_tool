from __future__ import annotations

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QWidget

from app.core.config import qsettings, shared_folder
from app.core.template_renderer import TemplatePreset, list_presets, render_records

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

    def _warn_no_presets(self, shared_folder) -> None:
        window = self.window()
        if not hasattr(window, "statusBar"):
            return  # not embedded in a QMainWindow (e.g. a standalone test)
        window.statusBar().showMessage(
            f"No label templates found in '{shared_folder}' - check the "
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
