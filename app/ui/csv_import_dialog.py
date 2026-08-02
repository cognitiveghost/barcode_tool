from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.csv_import import apply_mapping, read_csv

NONE_OPTION = "-- none --"
PREVIEW_ROW_LIMIT = 5

DELIMITER_OPTIONS = [(",", "Comma (,)"), (";", "Semicolon (;)"), ("\t", "Tab"), ("|", "Pipe (|)")]
ENCODING_OPTIONS = ["utf-8-sig", "utf-16", "cp1251"]


class CsvImportDialog(QDialog):
    def __init__(self, fields: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import CSV")
        self._fields = fields
        self._header: list[str] = []
        self._rows: list[list[str]] = []
        self._path: Path | None = None

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

        layout = QVBoxLayout(self)
        layout.addWidget(browse_button)
        layout.addLayout(form)
        layout.addWidget(self.preview_table)
        layout.addWidget(buttons)

        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.resize(900, 600)

    def _on_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import CSV", filter="CSV files (*.csv)")
        if path:
            self.load_csv(Path(path))

    def load_csv(self, path: Path) -> None:
        self._path = path
        header, rows, delimiter, encoding = read_csv(path)
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

        for combo in self.field_combos.values():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(NONE_OPTION)
            combo.addItems(self._header)
            combo.blockSignals(False)
        self._refresh_preview()

    def _on_override_changed(self) -> None:
        if self._path is None:
            return
        header, rows, delimiter, encoding = read_csv(
            self._path,
            delimiter=self.delimiter_combo.currentData(),
            encoding=self.encoding_combo.currentData(),
        )
        self._apply_loaded_csv(header, rows, delimiter, encoding)

    def _current_mapping(self) -> dict[str, str | None]:
        mapping = {}
        for name, combo in self.field_combos.items():
            text = combo.currentText()
            mapping[name] = None if text == NONE_OPTION else text
        return mapping

    def get_mapped_rows(self) -> list[dict[str, str]]:
        return apply_mapping(self._header, self._rows, self._current_mapping())

    def _refresh_preview(self) -> None:
        mapped_rows = self.get_mapped_rows()[:PREVIEW_ROW_LIMIT]
        self.preview_table.setRowCount(len(mapped_rows))
        for row_index, mapped_row in enumerate(mapped_rows):
            for col_index, (name, _label) in enumerate(self._fields):
                self.preview_table.setItem(
                    row_index, col_index, QTableWidgetItem(mapped_row.get(name, ""))
                )
