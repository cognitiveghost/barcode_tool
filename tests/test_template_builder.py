from PySide6.QtCore import QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.layout_builder import new_layout
from app.ui.template_builder import TemplateBuilderDialog, _ResizeHandle


def _app():
    return QApplication.instance() or QApplication([])


def _dialog(tmp_path, mode="inventory"):
    _app()
    return TemplateBuilderDialog(new_layout(mode), tmp_path)


def _handle(dlg):
    return next(c for c in dlg.items[0].childItems() if isinstance(c, _ResizeHandle))


def test_add_element_appends_default_and_selects(tmp_path):
    dlg = _dialog(tmp_path)

    index = dlg.add_element("qr")

    assert index == 0
    assert dlg.layout["elements"][0]["field"] == "sku"
    assert dlg.selected == 0
    assert dlg.dirty


def test_drag_snaps_to_1mm(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("text")

    dlg.items[0].setPos(10.4, 5.6)
    dlg.items[0].commit_drag()

    assert dlg.layout["elements"][0]["x_mm"] == 10
    assert dlg.layout["elements"][0]["y_mm"] == 6


def test_resize_handle_snaps_and_keeps_min_1mm(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("text")
    _handle(dlg).drag_to(12.7, 0.2)

    _handle(dlg).commit_resize()

    el = dlg.layout["elements"][0]
    assert el["w_mm"] == 13
    assert el["h_mm"] == 1


def test_resize_on_horizontal_line_changes_only_length(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("line")
    before_h = dlg.layout["elements"][0]["h_mm"]

    _handle(dlg).drag_to(12.7, 0.2)
    _handle(dlg).commit_resize()

    el = dlg.layout["elements"][0]
    assert el["w_mm"] == 13
    assert el["h_mm"] == before_h


def test_nudge_moves_half_a_mm_and_clamps_at_0(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("text")
    dlg.set_geometry(0, 2, 2, 40, 8)

    dlg.move_selected(0.5, -5)

    el = dlg.layout["elements"][0]
    assert (el["x_mm"], el["y_mm"]) == (2.5, 0)


def test_arrow_and_delete_keys_on_canvas(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.show()
    dlg.add_element("text")
    dlg.set_geometry(0, 2, 2, 40, 8)

    QTest.keyClick(dlg.view, Qt.Key_Right)
    assert dlg.layout["elements"][0]["x_mm"] == 2.5

    QTest.keyClick(dlg.view, Qt.Key_Delete)
    assert dlg.layout["elements"] == []
    assert dlg.selected is None


def test_undo_restores_each_previous_state(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("text")
    dlg.move_selected(1, 1)
    dlg.delete_selected()

    dlg.undo()
    assert len(dlg.layout["elements"]) == 1
    dlg.undo()
    assert dlg.layout["elements"][0]["x_mm"] == 2
    dlg.undo()
    assert dlg.layout["elements"] == []
    dlg.undo()
    assert dlg.layout["elements"] == []


def test_scene_is_in_mm(tmp_path):
    dlg = _dialog(tmp_path)

    dlg.set_label_size(68, 38)

    assert dlg.scene.sceneRect().contains(QRectF(0, 0, 68, 38))
