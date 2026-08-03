import os
import sys
from pathlib import Path


def configure_frozen_weasyprint_env() -> None:
    if getattr(sys, "frozen", False) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(Path(sys.executable).parent / "gtk-dlls"))


configure_frozen_weasyprint_env()

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
