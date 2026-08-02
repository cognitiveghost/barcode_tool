from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.config import default_settings_path, save_settings
from app.core.csv_import import apply_mapping, read_csv
from app.core.csv_mapping_memory import auto_map_fields, recall_mapping, remember_mapping

NONE_OPTION = "-- none --"
PREVIEW_ROW_LIMIT = 5

DELIMITER_OPTIONS = [(",", "Comma (,)"), (";", "Semicolon (;)"), ("\t", "Tab"), ("|", "Pipe (|)")]
ENCODING_OPTIONS = ["utf-8-sig", "utf-16", "cp1251"]


class CsvImportDialog(QDialog):
    def __init__(
        self,
        fields: list[tuple[str, str]],
        parent=None,
        *,
        settings: dict | None = None,
        mode: str | None = None,
        validate_mapping: Callable[[dict[str, int | None]], str | None] | None = None,
        row_would_be_skipped: Callable[[dict[str, str]], bool] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Import CSV")
        self._fields = fields
        self._header: list[str] = []
        self._rows: list[list[str]] = []
        self._path: Path | None = None
        self._settings = settings
        self._mode = mode
        self._validate_mapping = validate_mapping
        self._row_would_be_skipped = row_would_be_skipped

        self.delimiter_combo = QComboBox()
        for value, label in DELIMITER_OPTIONS:
            self.delimiter_combo.addItem(label, value)
        self.delimiter_combo.currentIndexChanged.connect(self._on_override_changed)

        self.encoding_combo = QComboBox()
        for value in ENCODING_OPTIONS:
            self.encoding_combo.addItem(value, value)
        self.encoding_combo.currentIndexChanged.connect(self._on_override_changed)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_clicked)

        self.field_combos: dict[str, QComboBox] = {}
        form = QFormLayout()
        form.addRow("Delimiter", self.delimiter_combo)
        form.addRow("Encoding", self.encoding_combo)
        for name, label in fields:
            combo = QComboBox()
            combo.addItem(NONE_OPTION)
            combo.currentIndexChanged.connect(self._refresh_preview)
            self.field_combos[name] = combo
            form.addRow(label, combo)

        self.preview_table = QTableWidget(0, len(fields))
        self.preview_table.setHorizontalHeaderLabels([label for _, label in fields])

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.Ok)
        self._reason_label = QLabel()
        self._reason_label.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addWidget(browse_button)
        layout.addLayout(form)
        layout.addWidget(self.preview_table)
        layout.addWidget(self._reason_label)
        layout.addWidget(buttons)

        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.resize(900, 600)

    def _on_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import CSV", filter="CSV files (*.csv)")
        if path:
            self.load_csv(Path(path))

    def load_csv(self, path: Path) -> None:
        try:
            header, rows, delimiter, encoding = read_csv(path)
        except ValueError as error:
            QMessageBox.warning(self, "Could not read CSV", str(error))
            return
        self._path = path
        self._apply_loaded_csv(header, rows, delimiter, encoding)

    def _apply_loaded_csv(
        self, header: list[str], rows: list[list[str]], delimiter: str, encoding: str
    ) -> None:
        self._header, self._rows = header, rows

        self.delimiter_combo.blockSignals(True)
        index = self.delimiter_combo.findData(delimiter)
        if index >= 0:
            self.delimiter_combo.setCurrentIndex(index)
        self.delimiter_combo.blockSignals(False)

        self.encoding_combo.blockSignals(True)
        index = self.encoding_combo.findData(encoding)
        if index >= 0:
            self.encoding_combo.setCurrentIndex(index)
        self.encoding_combo.blockSignals(False)

        seen: dict[str, int] = {}
        for name in self._header:
            seen[name] = seen.get(name, 0) + 1

        for combo in self.field_combos.values():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(NONE_OPTION, None)
            for index, name in enumerate(self._header):
                combo.addItem(name, index)
            # Repeated header names are indistinguishable in the dropdown,
            # so show the column number on the duplicates only.
            for index, name in enumerate(self._header):
                if seen[name] > 1:
                    combo.setItemText(index + 1, f"{name} (col {index + 1})")
            combo.blockSignals(False)

        initial_mapping = auto_map_fields(self._header, list(self.field_combos.keys()))
        if self._settings is not None and self._mode is not None:
            remembered = recall_mapping(self._settings, self._mode, self._header)
            if remembered:
                initial_mapping.update(remembered)

        for name, combo in self.field_combos.items():
            index = combo.findData(initial_mapping.get(name))
            if index >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)

        self._refresh_preview()

    def _on_override_changed(self) -> None:
        if self._path is None:
            return
        try:
            header, rows, delimiter, encoding = read_csv(
                self._path,
                delimiter=self.delimiter_combo.currentData(),
                encoding=self.encoding_combo.currentData(),
            )
        except ValueError as error:
            # Leave _header/_rows/combos exactly as they were before this
            # override attempt - a bad override shouldn't wipe out a
            # previously-successful parse.
            QMessageBox.warning(self, "Could not read CSV", str(error))
            return
        self._apply_loaded_csv(header, rows, delimiter, encoding)

    def _current_mapping(self) -> dict[str, int | None]:
        return {name: combo.currentData() for name, combo in self.field_combos.items()}

    def get_mapped_rows(self) -> list[dict[str, str]]:
        return apply_mapping(self._rows, self._current_mapping())

    def _refresh_preview(self) -> None:
        mapped_rows = self.get_mapped_rows()[:PREVIEW_ROW_LIMIT]
        self.preview_table.setRowCount(len(mapped_rows))
        for row_index, mapped_row in enumerate(mapped_rows):
            would_skip = (
                self._row_would_be_skipped is not None
                and self._row_would_be_skipped(mapped_row)
            )
            for col_index, (name, _label) in enumerate(self._fields):
                item = QTableWidgetItem(mapped_row.get(name, ""))
                if would_skip:
                    item.setBackground(QColor(255, 210, 210))
                self.preview_table.setItem(row_index, col_index, item)
        self._update_ok_state()

    def _update_ok_state(self) -> None:
        if self._validate_mapping is None:
            return
        reason = self._validate_mapping(self._current_mapping())
        self._ok_button.setEnabled(reason is None)
        self._reason_label.setText(reason or "")
        self._reason_label.setVisible(reason is not None)

    def accept(self) -> None:
        if self._settings is not None and self._mode is not None and self._header:
            remember_mapping(self._settings, self._mode, self._header, self._current_mapping())
            try:
                save_settings(default_settings_path(), self._settings)
            except OSError:
                # A remembered mapping is a convenience; failing to persist
                # it must never block an import the operator already
                # confirmed by clicking OK.
                pass
        super().accept()
