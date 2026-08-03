import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

import app.ui.theme as theme_module
from app.ui.theme import THEMES, apply_theme


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _reset_captured_defaults():
    # apply_theme() caches the process's original palette/style on first
    # call; without resetting it between tests, whichever test runs first
    # in the process decides every later test's "system" baseline.
    theme_module._default_palette = None
    theme_module._default_style_name = None
    yield
    theme_module._default_palette = None
    theme_module._default_style_name = None


def test_dark_theme_changes_the_window_text_color():
    app = _app()
    apply_theme(app, "light")
    light_color = app.palette().color(QPalette.ColorRole.WindowText)

    apply_theme(app, "dark")
    dark_color = app.palette().color(QPalette.ColorRole.WindowText)

    assert dark_color != light_color


def test_system_theme_restores_the_original_palette():
    app = _app()
    original = app.palette()

    apply_theme(app, "dark")
    apply_theme(app, "system")

    assert app.palette() == original


def test_unknown_theme_raises():
    app = _app()
    with pytest.raises(ValueError):
        apply_theme(app, "sepia")


def test_all_three_themes_apply_without_raising():
    app = _app()
    for theme in THEMES:
        apply_theme(app, theme)  # must not raise
