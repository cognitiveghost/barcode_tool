from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsPixmapItem,
    QLabel,
    QMessageBox,
)

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


def test_drag_that_rounds_to_the_same_mm_snaps_back(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("text")
    x, y = dlg.layout["elements"][0]["x_mm"], dlg.layout["elements"][0]["y_mm"]

    dlg.items[0].setPos(x + 0.4, y - 0.3)
    dlg.items[0].commit_drag()

    assert (dlg.items[0].pos().x(), dlg.items[0].pos().y()) == (x, y)
    assert len(dlg._undo) == 1  # only the add


def test_box_interior_does_not_cover_elements_under_it(tmp_path):
    dlg = _dialog(tmp_path)
    text = dlg.add_element("text")
    box = dlg.add_element("box")
    dlg.set_geometry(box, 0, 0, 100, 80)
    text_item = dlg.items[text]
    inside = text_item.mapToScene(text_item.rect().center())

    assert dlg.scene.items(inside)[0] is text_item
    assert dlg.scene.items(QPointF(0.5, 40))[0] is dlg.items[box]


def test_thin_line_has_a_grab_margin(tmp_path):
    dlg = _dialog(tmp_path)
    line = dlg.add_element("line")
    el = dlg.layout["elements"][line]

    near = QPointF(el["x_mm"] + 2, el["y_mm"] + el["thickness_mm"] + 0.7)

    assert dlg.scene.items(near)[0] is dlg.items[line]


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


def test_undo_back_to_the_start_is_clean(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("text")

    dlg.undo()

    assert not dlg.dirty


def test_tabbing_between_property_fields_keeps_focus(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.show()
    QTest.qWaitForWindowActive(dlg)
    dlg.add_element("text")
    dlg.prop_widgets["x_mm"].setFocus()
    QApplication.processEvents()
    dlg.prop_widgets["x_mm"].setValue(7)

    dlg.prop_widgets["y_mm"].setFocus()  # focus-out commits x and rebuilds the form
    QApplication.processEvents()

    assert dlg.layout["elements"][0]["x_mm"] == 7
    assert dlg.prop_widgets["y_mm"].hasFocus()


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


def _modals(monkeypatch, answer=QMessageBox.No):
    """Record QMessageBox calls instead of opening a modal; ``answer`` is the question reply."""
    seen = {"warning": [], "question": []}

    def warning(parent, title, text, *args, **kwargs):
        seen["warning"].append(text)
        return QMessageBox.Ok

    def question(parent, title, text, *args, **kwargs):
        seen["question"].append(text)
        return answer

    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QMessageBox, "question", question)
    return seen


def test_preview_shows_the_rendered_bitmap_and_locks_editing(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("qr")

    dlg.set_preview(True)

    pixmaps = [i for i in dlg.scene.items() if isinstance(i, QGraphicsPixmapItem)]
    assert len(pixmaps) == 1
    rect = pixmaps[0].sceneBoundingRect()
    assert abs(rect.width() - dlg.layout["width_mm"]) < 0.2
    assert abs(rect.height() - dlg.layout["height_mm"]) < 0.2
    assert not dlg.items[0].isVisible()
    assert all(not button.isEnabled() for button in dlg.palette_buttons)

    dlg.set_preview(False)

    assert not [i for i in dlg.scene.items() if isinstance(i, QGraphicsPixmapItem)]
    assert dlg.items[0].isVisible()
    assert all(button.isEnabled() for button in dlg.palette_buttons)


def test_edits_are_ignored_while_previewing(tmp_path):
    dlg = _dialog(tmp_path)
    dlg.add_element("qr")
    dlg.set_preview(True)

    dlg.delete_selected()

    assert len(dlg.layout["elements"]) == 1


def test_preview_error_goes_to_status_line(tmp_path):
    dlg = TemplateBuilderDialog(
        new_layout("inventory"), tmp_path, sample={"name": "Гвинт"}
    )
    dlg.add_element("barcode")
    dlg.update_element(0, field="name")

    dlg.set_preview(True)

    assert dlg.status_label.text()
    assert not dlg.preview_button.isChecked()


def test_save_writes_folder_and_accepts(tmp_path, monkeypatch):
    seen = _modals(monkeypatch)
    dlg = _dialog(tmp_path)
    dlg.name_edit.setText("My label")
    dlg.name_edit.editingFinished.emit()
    dlg.add_element("qr")

    folder = dlg.save()

    assert folder == tmp_path / "templates" / "inventory" / "my-label"
    for name in ("layout.json", "template.html", "style.css", "meta.json"):
        assert (folder / name).is_file()
    assert dlg.saved_name == "My label"
    assert dlg.result() == QDialog.Accepted
    assert seen == {"warning": [], "question": []}


def test_save_refuses_app_owned_name(tmp_path, monkeypatch):
    seen = _modals(monkeypatch)
    dlg = _dialog(tmp_path)
    dlg.name_edit.setText("Default")
    dlg.name_edit.editingFinished.emit()
    dlg.add_element("qr")

    assert dlg.save() is None
    assert len(seen["warning"]) == 1
    assert "built-in" in seen["warning"][0]


def test_save_with_empty_name_is_refused(tmp_path, monkeypatch):
    seen = _modals(monkeypatch)
    dlg = _dialog(tmp_path)
    dlg.name_edit.setText("")
    dlg.add_element("qr")

    assert dlg.save() is None
    assert seen["warning"] == ["Give the template a name first."]
    assert not (tmp_path / "templates").exists()


def test_save_warns_on_black_block_and_respects_cancel(tmp_path, monkeypatch):
    seen = _modals(monkeypatch, answer=QMessageBox.No)
    dlg = _dialog(tmp_path)
    dlg.name_edit.setText("Heavy")
    dlg.name_edit.editingFinished.emit()
    for i in range(8):
        dlg.add_element("line")
        dlg.update_element(i, x_mm=5, y_mm=5 + i * 0.5, w_mm=20, thickness_mm=0.5)

    assert dlg.save() is None
    assert len(seen["question"]) == 1
    assert not (tmp_path / "templates" / "inventory" / "heavy").exists()

    seen_yes = _modals(monkeypatch, answer=QMessageBox.Yes)
    folder = dlg.save()

    assert folder is not None and (folder / "layout.json").is_file()
    assert len(seen_yes["question"]) == 1


def test_close_with_unsaved_changes_asks_and_can_stay(tmp_path, monkeypatch):
    seen = _modals(monkeypatch, answer=QMessageBox.No)
    dlg = _dialog(tmp_path)
    dlg.show()
    dlg.add_element("qr")

    dlg.reject()

    assert len(seen["question"]) == 1
    assert dlg.isVisible()


def test_clean_dialog_closes_without_asking(tmp_path, monkeypatch):
    seen = _modals(monkeypatch)
    dlg = _dialog(tmp_path)
    dlg.show()

    dlg.reject()

    assert seen["question"] == []
    assert not dlg.isVisible()
