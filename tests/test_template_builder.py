from PySide6.QtCore import QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from app.core.layout_builder import mode_fields, new_layout
from app.ui.template_builder import SIZES, TemplateBuilderDialog, _ResizeHandle


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


def test_name_edit_sets_layout_name(tmp_path):
    dlg = _dialog(tmp_path)

    dlg.name_edit.setText("Shelf tag")
    dlg.name_edit.editingFinished.emit()

    assert dlg.layout["name"] == "Shelf tag"


def test_size_combo_preset_and_custom(tmp_path):
    dlg = _dialog(tmp_path)

    dlg.size_combo.setCurrentIndex(SIZES.index((68, 38)))

    assert (dlg.layout["width_mm"], dlg.layout["height_mm"]) == (68, 38)
    assert dlg.width_spin.value() == 68
    assert dlg.height_spin.value() == 38

    dlg.width_spin.setValue(70)
    dlg.width_spin.editingFinished.emit()

    assert dlg.size_combo.currentText() == "Custom"
    assert dlg.layout["width_mm"] == 70


def test_properties_show_only_the_selected_type(tmp_path):
    dlg = _dialog(tmp_path, mode="inventory")
    dlg.add_element("qr")

    assert "field" in dlg.prop_widgets
    assert "content" not in dlg.prop_widgets
    fields = [dlg.prop_widgets["field"].itemText(i) for i in range(dlg.prop_widgets["field"].count())]
    assert fields == mode_fields("inventory")


def test_property_edit_updates_layout_and_is_undoable(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("text")

    dlg.prop_widgets["bold"].setChecked(True)
    assert dlg.layout["elements"][0]["bold"] is True

    dlg.undo()
    assert dlg.layout["elements"][0]["bold"] is False


def test_insert_field_appends_placeholder(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("text")

    dlg.prop_widgets["insert_field"].setCurrentText("batch")

    assert dlg.layout["elements"][0]["content"].endswith("{batch}")


def test_unknown_placeholder_typed_in_content_is_not_committed(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("text")
    before = dlg.layout["elements"][0]["content"]

    dlg.prop_widgets["content"].setText("{nope}")
    dlg.prop_widgets["content"].editingFinished.emit()

    assert dlg.layout["elements"][0]["content"] == before
    assert "nope" in dlg.error_label.text()


def test_line_orientation_switch_keeps_length(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("line")

    dlg.prop_widgets["orientation"].setCurrentIndex(1)

    el = dlg.layout["elements"][0]
    assert el["orientation"] == "v"
    assert el["h_mm"] == 40
    assert el["w_mm"] == 0


def test_mode_is_shown_read_only(tmp_path):
    dlg = _dialog(tmp_path, mode="inventory")

    texts = [label.text() for label in dlg.findChildren(QLabel)]

    assert "Mode: inventory" in texts
