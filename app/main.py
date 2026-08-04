import os
import sys
from pathlib import Path


# WeasyPrint (via blabel) needs GTK3's bundled Pango/Cairo/fontconfig on
# Windows. A frozen build ships its own GTK3 copy in gtk-dlls/ next to the
# exe; Windows won't find those DLLs (or, separately, fontconfig's own
# fonts.conf) unless we point at them explicitly first.
def configure_frozen_weasyprint_env() -> None:
    if getattr(sys, "frozen", False) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(Path(sys.executable).parent / "gtk-dlls"))


# When GTK3 isn't on PATH - or another tool's older fontconfig.dll shadows
# it - fontconfig can't find its fonts.conf and prints "Cannot load default
# config file" at startup. Labels still render (this app's templates use a
# bundled @font-face TTF, not system font lookup), but pointing
# FONTCONFIG_PATH at a real fonts.conf when one is findable avoids the
# noise. Best-effort only: never overrides an already-set env var, and
# never sets a path that doesn't actually contain a fonts.conf.
_WINDOWS_GTK3_FONTCONFIG_CANDIDATES = (
    r"C:\Program Files\GTK3-Runtime Win64\etc\fonts",
    r"C:\msys64\mingw64\etc\fonts",
)


def configure_windows_fontconfig_env() -> None:
    if sys.platform != "win32" or os.environ.get("FONTCONFIG_PATH"):
        return
    candidates = list(_WINDOWS_GTK3_FONTCONFIG_CANDIDATES)
    if getattr(sys, "frozen", False):
        candidates.insert(0, str(Path(sys.executable).parent / "gtk-dlls" / "etc" / "fonts"))
    for candidate in candidates:
        if (Path(candidate) / "fonts.conf").is_file():
            os.environ["FONTCONFIG_PATH"] = candidate
            return


configure_frozen_weasyprint_env()
configure_windows_fontconfig_env()

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
