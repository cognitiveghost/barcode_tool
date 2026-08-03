from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

THEMES = ("system", "light", "dark")
DEFAULT_THEME = "system"

# Captured once, on the first apply_theme() call, so "system" can always
# revert to whatever this platform's native look actually was - including
# on the very first call, before any override has happened yet.
_default_palette: QPalette | None = None
_default_style_name: str | None = None


def _dark_palette() -> QPalette:
    # ponytail: a hand-rolled Fusion dark palette, not a theming library.
    # Upgrade path if visual polish becomes a priority: qdarkstyle/qt-material.
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(35, 35, 35))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127)
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127)
    )
    return palette


def apply_theme(app: QApplication, theme: str) -> None:
    global _default_palette, _default_style_name
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}, expected one of {THEMES}")

    if _default_palette is None:
        _default_palette = app.palette()
        _default_style_name = app.style().objectName()

    if theme == "dark":
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(_dark_palette())
    elif theme == "light":
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(app.style().standardPalette())
    else:
        app.setStyle(QStyleFactory.create(_default_style_name))
        app.setPalette(_default_palette)
