from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.position_generator import SkippedRow


class SkippedRowsDialog(QDialog):
    def __init__(
        self,
        skipped_rows: list[SkippedRow],
        raw_rows: list[dict[str, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Skipped rows")

        self.table = QTableWidget(len(skipped_rows), 3)
        self.table.setHorizontalHeaderLabels(["Row", "Reason", "Raw values"])
        for table_row, skipped in enumerate(skipped_rows):
            raw = raw_rows[skipped.row_number - 1] if skipped.row_number - 1 < len(raw_rows) else {}
            raw_text = ", ".join(f"{key}={value}" for key, value in raw.items())
            self.table.setItem(table_row, 0, QTableWidgetItem(str(skipped.row_number)))
            self.table.setItem(table_row, 1, QTableWidgetItem(skipped.reason))
            self.table.setItem(table_row, 2, QTableWidgetItem(raw_text))

        copy_button = QPushButton("Copy to clipboard")
        copy_button.clicked.connect(self._copy_to_clipboard)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(copy_button)
        layout.addWidget(buttons)
        self.resize(700, 400)

    def _copy_to_clipboard(self) -> None:
        lines = ["Row\tReason\tRaw values"]
        for row in range(self.table.rowCount()):
            cells = [self.table.item(row, col).text() for col in range(3)]
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))
