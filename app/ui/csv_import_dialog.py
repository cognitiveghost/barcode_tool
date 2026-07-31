from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.csv_import import apply_mapping, read_csv

NONE_OPTION = "-- none --"
PREVIEW_ROW_LIMIT = 5


class CsvImportDialog(QDialog):
    def __init__(self, fields: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import CSV")
        self._fields = fields
        self._header: list[str] = []
        self._rows: list[list[str]] = []

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_clicked)

        self.field_combos: dict[str, QComboBox] = {}
        form = QFormLayout()
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

    def _on_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import CSV", filter="CSV files (*.csv)")
        if path:
            self.load_csv(Path(path))

    def load_csv(self, path: Path) -> None:
        self._header, self._rows = read_csv(path)
        for combo in self.field_combos.values():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(NONE_OPTION)
            combo.addItems(self._header)
            combo.blockSignals(False)
        self._refresh_preview()

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
