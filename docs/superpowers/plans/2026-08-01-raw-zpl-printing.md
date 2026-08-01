# Raw ZPL Printing + Label Layout Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in raw-ZPL print path (via `zebrafy`) for the Citizen CL-E300 alongside the existing `QPrinter`/OS-driver path, archive a PDF copy of every Mode 2.1 print to the shared folder, and de-duplicate the QR+caption positioning code in `label_renderer.py`.

**Architecture:** A new `app/core/zpl_print_service.py` converts a `PIL.Image` label to ZPL text (`zebrafy`) and writes it directly to the printer (`win32print` RAW job on Windows, a device-node write on Linux — both USB). `app/core/print_service.py` gains `send_to_printer()`, a single dispatcher both mode panels call, which routes to the existing `QPrinter` path, the new raw-ZPL path, or a forced PDF write, based on `settings["print_mode"]` and whether an explicit `output_pdf_path` was given. Mode 2.1 additionally calls `send_to_printer()` a second time after every print to archive a PDF under `shared_folder/printed_pdfs/`.

**Tech Stack:** Python 3.11, PySide6/Qt (`QPrinter`), Pillow, `zebrafy` (new), `pywin32` (new, Windows-only).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-01-raw-zpl-printing-design.md` (approved).
- All app code, comments, and UI text stay in English (existing project-wide rule from `Essential technical specifications.txt` §3.1 — the codebase is already 100% English; keep it that way).
- No new dependencies beyond `zebrafy` and `pywin32` (`; sys_platform == "win32"`). Do **not** add `python-escpos` or `blabel` — their patterns are adapted inline, not depended on (design §2).
- CI (`.github/workflows/ci.yml`) runs `pytest -v` and `ruff check .` on both `ubuntu-latest` and `windows-latest`. Every new/modified file must import cleanly and pass `ruff check` on both platforms — in particular, `app/core/zpl_print_service.py` must NOT do a module-level `import win32print` (it isn't installed on Linux); import it lazily inside `send_raw_windows()`.
- `QPrinter`/driver printing remains the default and unchanged behavior when `settings` has no `print_mode` key (existing callers/tests that build ad-hoc settings dicts without `print_mode` must keep working).
- Follow existing code conventions: `from __future__ import annotations` at the top of `core/` modules that already use it, `settings.get(key, default)` (never `settings[key]`) for reading optional settings, module-level constants in `SCREAMING_SNAKE_CASE`.

---

### Task 1: `zpl_print_service.py` — `image_to_zpl()`

**Files:**
- Create: `app/core/zpl_print_service.py`
- Modify: `requirements.txt`
- Test: `tests/test_zpl_print_service.py` (create)

**Interfaces:**
- Produces: `image_to_zpl(image: PIL.Image.Image) -> str` — a complete ZPL document (`^XA...^XZ`) encoding the image as a graphic field. Used by `print_labels_zpl()` (Task 4).

- [ ] **Step 1: Add the `zebrafy` dependency**

Add this line to `requirements.txt`, after `Pillow>=10.1.0`:

```
zebrafy>=1.2
```

Run: `pip install -r requirements.txt`
Expected: `zebrafy` installs successfully.

- [ ] **Step 2: Write the failing test**

Create `tests/test_zpl_print_service.py`:

```python
from PIL import Image

from app.core.zpl_print_service import image_to_zpl


def test_image_to_zpl_returns_a_complete_zpl_block():
    image = Image.new("RGB", (100, 100), "white")

    zpl = image_to_zpl(image)

    assert zpl.startswith("^XA")
    assert zpl.rstrip().endswith("^XZ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zpl_print_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.zpl_print_service'`

- [ ] **Step 3: Write minimal implementation**

Create `app/core/zpl_print_service.py`:

```python
from __future__ import annotations

from PIL import Image
from zebrafy import ZebrafyImage


def image_to_zpl(image: Image.Image) -> str:
    return ZebrafyImage(image).to_zpl()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zpl_print_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt app/core/zpl_print_service.py tests/test_zpl_print_service.py
git commit -m "Add image_to_zpl using zebrafy"
```

---

### Task 2: `zpl_print_service.py` — `send_raw_linux()`

**Files:**
- Modify: `app/core/zpl_print_service.py`
- Test: `tests/test_zpl_print_service.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `send_raw_linux(device_path: str, data: bytes) -> None` — writes `data` to the file at `device_path`. Used by `print_labels_zpl()` (Task 4).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_zpl_print_service.py`:

```python
from app.core.zpl_print_service import image_to_zpl, send_raw_linux


def test_send_raw_linux_writes_bytes_to_the_device_path(tmp_path):
    device_path = tmp_path / "lp0"

    send_raw_linux(str(device_path), b"^XA^XZ")

    assert device_path.read_bytes() == b"^XA^XZ"
```

(Replace the single-name import at the top of the file with the combined one above.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zpl_print_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'send_raw_linux'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/core/zpl_print_service.py` (add `from pathlib import Path` to the imports):

```python
from pathlib import Path


def send_raw_linux(device_path: str, data: bytes) -> None:
    Path(device_path).write_bytes(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zpl_print_service.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/zpl_print_service.py tests/test_zpl_print_service.py
git commit -m "Add send_raw_linux device-node writer"
```

---

### Task 3: `zpl_print_service.py` — `send_raw_windows()`

**Files:**
- Modify: `app/core/zpl_print_service.py`
- Modify: `requirements.txt`
- Test: `tests/test_zpl_print_service.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `send_raw_windows(printer_name: str, data: bytes) -> None` — opens a RAW print job on the named Windows printer and writes `data`. Used by `print_labels_zpl()` (Task 4).

- [ ] **Step 1: Add the `pywin32` dependency**

Add this line to `requirements.txt`, after `zebrafy>=1.2`:

```
pywin32>=306; sys_platform == "win32"
```

This is a marker-conditional dependency — `pip install -r requirements.txt` skips it entirely on Linux, so it never needs to be importable there.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_zpl_print_service.py` (add `import sys` and `import types` to the top of the file):

```python
import sys
import types

from app.core.zpl_print_service import image_to_zpl, send_raw_linux, send_raw_windows


def test_send_raw_windows_opens_a_raw_job_and_writes_bytes(monkeypatch):
    calls = []

    def _open_printer(name):
        calls.append(("OpenPrinter", name))
        return "HANDLE"

    def _start_doc_printer(handle, level, doc_info):
        calls.append(("StartDocPrinter", handle, level, doc_info))

    def _start_page_printer(handle):
        calls.append(("StartPagePrinter", handle))

    def _write_printer(handle, data):
        calls.append(("WritePrinter", handle, data))

    def _end_page_printer(handle):
        calls.append(("EndPagePrinter", handle))

    def _end_doc_printer(handle):
        calls.append(("EndDocPrinter", handle))

    def _close_printer(handle):
        calls.append(("ClosePrinter", handle))

    fake_win32print = types.ModuleType("win32print")
    fake_win32print.OpenPrinter = _open_printer
    fake_win32print.StartDocPrinter = _start_doc_printer
    fake_win32print.StartPagePrinter = _start_page_printer
    fake_win32print.WritePrinter = _write_printer
    fake_win32print.EndPagePrinter = _end_page_printer
    fake_win32print.EndDocPrinter = _end_doc_printer
    fake_win32print.ClosePrinter = _close_printer
    monkeypatch.setitem(sys.modules, "win32print", fake_win32print)

    send_raw_windows("ZPL-RAW-Printer", b"^XA^XZ")

    call_names = [call[0] for call in calls]
    assert call_names == [
        "OpenPrinter",
        "StartDocPrinter",
        "StartPagePrinter",
        "WritePrinter",
        "EndPagePrinter",
        "EndDocPrinter",
        "ClosePrinter",
    ]
    assert calls[0][1] == "ZPL-RAW-Printer"
    assert calls[1][3] == ("ZPL label", "", "RAW")
    assert calls[3][2] == b"^XA^XZ"
```

This injects a fake `win32print` module into `sys.modules` before calling `send_raw_windows()`, so the test runs identically on Linux and Windows CI without the real `pywin32` package.

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_zpl_print_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'send_raw_windows'`

- [ ] **Step 4: Write minimal implementation**

Add to `app/core/zpl_print_service.py`:

```python
def send_raw_windows(printer_name: str, data: bytes) -> None:
    import win32print

    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(handle, 1, ("ZPL label", "", "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)
```

The `import win32print` stays inside the function (not at module level) so `app/core/zpl_print_service.py` remains importable on Linux, where `pywin32` isn't installed.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_zpl_print_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt app/core/zpl_print_service.py tests/test_zpl_print_service.py
git commit -m "Add send_raw_windows RAW spooler writer"
```

---

### Task 4: `zpl_print_service.py` — `print_labels_zpl()` dispatcher

**Files:**
- Modify: `app/core/zpl_print_service.py`
- Test: `tests/test_zpl_print_service.py`

**Interfaces:**
- Consumes: `image_to_zpl` (Task 1), `send_raw_linux` (Task 2), `send_raw_windows` (Task 3) — all from the same module.
- Produces: `print_labels_zpl(images: list[PIL.Image.Image], target: str) -> None` — converts and sends each image in order. This is the function `app/core/print_service.py`'s `send_to_printer()` (Task 5) calls for `print_mode == "raw_zpl"`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_zpl_print_service.py` (add `from PIL import Image` already present; add `print_labels_zpl` to the import):

```python
from app.core.zpl_print_service import (
    image_to_zpl,
    print_labels_zpl,
    send_raw_linux,
    send_raw_windows,
)


def test_print_labels_zpl_dispatches_to_linux_transport(monkeypatch):
    monkeypatch.setattr("app.core.zpl_print_service.sys.platform", "linux")
    sent = []
    monkeypatch.setattr(
        "app.core.zpl_print_service.send_raw_linux",
        lambda target, data: sent.append((target, data)),
    )
    monkeypatch.setattr(
        "app.core.zpl_print_service.image_to_zpl", lambda image: "^XA^XZ"
    )
    images = [Image.new("RGB", (10, 10), "white"), Image.new("RGB", (10, 10), "white")]

    print_labels_zpl(images, "/dev/usb/lp0")

    assert sent == [("/dev/usb/lp0", b"^XA^XZ"), ("/dev/usb/lp0", b"^XA^XZ")]


def test_print_labels_zpl_dispatches_to_windows_transport(monkeypatch):
    monkeypatch.setattr("app.core.zpl_print_service.sys.platform", "win32")
    sent = []
    monkeypatch.setattr(
        "app.core.zpl_print_service.send_raw_windows",
        lambda target, data: sent.append((target, data)),
    )
    monkeypatch.setattr(
        "app.core.zpl_print_service.image_to_zpl", lambda image: "^XA^XZ"
    )
    images = [Image.new("RGB", (10, 10), "white")]

    print_labels_zpl(images, "ZPL-RAW-Printer")

    assert sent == [("ZPL-RAW-Printer", b"^XA^XZ")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_zpl_print_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'print_labels_zpl'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/core/zpl_print_service.py` (add `import sys` to the imports):

```python
import sys


def print_labels_zpl(images: list[Image.Image], target: str) -> None:
    for image in images:
        data = image_to_zpl(image).encode("ascii")
        if sys.platform == "win32":
            send_raw_windows(target, data)
        else:
            send_raw_linux(target, data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_zpl_print_service.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run ruff**

Run: `ruff check app/core/zpl_print_service.py tests/test_zpl_print_service.py`
Expected: no errors. Fix any import-order/unused-import issues before continuing.

- [ ] **Step 6: Commit**

```bash
git add app/core/zpl_print_service.py tests/test_zpl_print_service.py
git commit -m "Add print_labels_zpl platform dispatcher"
```

---

### Task 5: `print_service.py` — `send_to_printer()` dispatcher

**Files:**
- Modify: `app/core/print_service.py`
- Modify: `app/core/config.py`
- Test: `tests/test_print_service.py`

**Interfaces:**
- Consumes: `print_labels_zpl(images, target)` (Task 4); existing `print_labels(images, width_mm, height_mm, printer_name=None, output_pdf_path=None)`.
- Produces: `send_to_printer(images: list[PIL.Image.Image], width_mm: float, height_mm: float, settings: dict, output_pdf_path: Path | None = None) -> None` — the single print entry point both mode panels use from here on (Tasks 7-8). `settings` is the app's settings dict (same shape as `app.core.config.DEFAULT_SETTINGS`); only `settings.get("print_mode")` and `settings.get("raw_zpl_target")` are read.
- `DEFAULT_SETTINGS` (in `app/core/config.py`) gains two keys: `"print_mode": "driver"` and `"raw_zpl_target": ""`.

- [ ] **Step 1: Add the new settings keys**

In `app/core/config.py`, add two entries to `DEFAULT_SETTINGS` (after `"default_printer": ""`):

```python
DEFAULT_SETTINGS = {
    "shared_folder": "",
    "default_printer": "",
    "print_mode": "driver",
    "raw_zpl_target": "",
    "warehouses": [],
    "label_sizes": [
        {"name": "100x150mm", "width_mm": 100, "height_mm": 150},
        {"name": "150x100mm", "width_mm": 150, "height_mm": 100},
        {"name": "68x38mm", "width_mm": 68, "height_mm": 38},
        {"name": "80x80mm", "width_mm": 80, "height_mm": 80},
    ],
}
```

Run: `pytest tests/test_config.py -v`
Expected: PASS unchanged (both existing tests compare against `DEFAULT_SETTINGS` as a whole, so they stay in sync automatically).

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_print_service.py` (add `send_to_printer` to the import from `app.core.print_service`):

```python
from app.core.print_service import _page_orientation, print_labels, send_to_printer


def test_send_to_printer_uses_pdf_path_regardless_of_print_mode(tmp_path):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    output_path = tmp_path / "labels.pdf"
    settings = {"print_mode": "raw_zpl", "raw_zpl_target": "/dev/usb/lp0"}

    send_to_printer(images, width_mm=68, height_mm=38, settings=settings, output_pdf_path=output_path)

    assert output_path.exists()


def test_send_to_printer_dispatches_to_raw_zpl_when_configured(monkeypatch):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    calls = []
    monkeypatch.setattr(
        "app.core.print_service.print_labels_zpl",
        lambda imgs, target: calls.append((imgs, target)),
    )
    settings = {"print_mode": "raw_zpl", "raw_zpl_target": "/dev/usb/lp0"}

    send_to_printer(images, width_mm=68, height_mm=38, settings=settings)

    assert calls == [(images, "/dev/usb/lp0")]


def test_send_to_printer_defaults_to_driver_mode(monkeypatch):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    calls = []
    monkeypatch.setattr(
        "app.core.print_service.print_labels",
        lambda imgs, width_mm, height_mm, **kwargs: calls.append(kwargs),
    )
    settings = {"print_mode": "driver", "default_printer": "Citizen CL-E300"}

    send_to_printer(images, width_mm=68, height_mm=38, settings=settings)

    assert calls == [{"printer_name": "Citizen CL-E300"}]


def test_send_to_printer_treats_missing_print_mode_as_driver(monkeypatch):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    calls = []
    monkeypatch.setattr(
        "app.core.print_service.print_labels",
        lambda imgs, width_mm, height_mm, **kwargs: calls.append(kwargs),
    )

    send_to_printer(images, width_mm=68, height_mm=38, settings={})

    assert calls == [{"printer_name": None}]


def test_send_to_printer_does_not_fall_back_to_driver_when_raw_zpl_fails(monkeypatch):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    driver_calls = []
    monkeypatch.setattr(
        "app.core.print_service.print_labels",
        lambda *a, **k: driver_calls.append(True),
    )

    def _boom(imgs, target):
        raise OSError("device not found")

    monkeypatch.setattr("app.core.print_service.print_labels_zpl", _boom)
    settings = {"print_mode": "raw_zpl", "raw_zpl_target": "/dev/usb/lp0"}

    with pytest.raises(OSError):
        send_to_printer(images, width_mm=68, height_mm=38, settings=settings)

    assert driver_calls == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_print_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'send_to_printer'`

- [ ] **Step 4: Write minimal implementation**

Add to `app/core/print_service.py` (add `from app.core.zpl_print_service import print_labels_zpl` to the imports, at the end of the existing import block):

```python
from app.core.zpl_print_service import print_labels_zpl


def send_to_printer(
    images: list[Image.Image],
    width_mm: float,
    height_mm: float,
    settings: dict,
    output_pdf_path: Path | None = None,
) -> None:
    if output_pdf_path is not None:
        print_labels(images, width_mm, height_mm, output_pdf_path=output_pdf_path)
        return
    if settings.get("print_mode") == "raw_zpl":
        print_labels_zpl(images, settings.get("raw_zpl_target", ""))
        return
    print_labels(images, width_mm, height_mm, printer_name=settings.get("default_printer") or None)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_print_service.py -v`
Expected: PASS (all tests, including the 5 new ones)

- [ ] **Step 6: Run ruff**

Run: `ruff check app/core/print_service.py app/core/config.py tests/test_print_service.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add app/core/print_service.py app/core/config.py tests/test_print_service.py
git commit -m "Add send_to_printer dispatcher and print_mode/raw_zpl_target settings"
```

---

### Task 6: Settings UI for print mode

**Files:**
- Modify: `app/ui/settings_window.py`
- Test: `tests/test_settings_window.py`

**Interfaces:**
- Consumes: `DEFAULT_SETTINGS["print_mode"]` / `["raw_zpl_target"]` (Task 5).
- Produces: `SettingsWindow.print_mode_combo` (`QComboBox`, items store `"driver"`/`"raw_zpl"` as `itemData`), `SettingsWindow.raw_zpl_target_edit` (`QLineEdit`). `SettingsWindow.get_current_settings()`'s returned dict gains `"print_mode"` and `"raw_zpl_target"` keys.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_settings_window.py`:

```python
def test_settings_window_prefills_print_mode_and_raw_zpl_target():
    _app()
    settings = {**DEFAULT_SETTINGS, "print_mode": "raw_zpl", "raw_zpl_target": "/dev/usb/lp0"}
    window = SettingsWindow(settings, settings_path=None)
    assert window.print_mode_combo.currentData() == "raw_zpl"
    assert window.raw_zpl_target_edit.text() == "/dev/usb/lp0"


def test_settings_window_defaults_print_mode_to_driver():
    _app()
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=None)
    assert window.print_mode_combo.currentData() == "driver"


def test_save_writes_print_mode_and_raw_zpl_target_to_disk(tmp_path):
    _app()
    settings_path = tmp_path / "settings.json"
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=settings_path)
    window.print_mode_combo.setCurrentIndex(window.print_mode_combo.findData("raw_zpl"))
    window.raw_zpl_target_edit.setText("/dev/usb/lp0")
    window._save_and_close()

    saved = load_settings(settings_path)
    assert saved["print_mode"] == "raw_zpl"
    assert saved["raw_zpl_target"] == "/dev/usb/lp0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_settings_window.py -v`
Expected: FAIL with `AttributeError: 'SettingsWindow' object has no attribute 'print_mode_combo'`

- [ ] **Step 3: Write minimal implementation**

In `app/ui/settings_window.py`, add `import sys` at the top (after `from pathlib import Path`).

In `SettingsWindow.__init__`, after the `printer_combo` block and before `self.warehouse_table = ...`, add:

```python
self.print_mode_combo = QComboBox()
self.print_mode_combo.addItem("OS driver (QPrinter)", "driver")
self.print_mode_combo.addItem("Raw ZPL (direct)", "raw_zpl")
mode_index = self.print_mode_combo.findData(settings.get("print_mode", "driver"))
if mode_index >= 0:
    self.print_mode_combo.setCurrentIndex(mode_index)

self.raw_zpl_target_edit = QLineEdit(settings.get("raw_zpl_target", ""))
if sys.platform == "win32":
    self.raw_zpl_target_edit.setPlaceholderText("e.g. ZPL-RAW-Printer (raw print queue name)")
else:
    self.raw_zpl_target_edit.setPlaceholderText("e.g. /dev/usb/lp0")
```

In the `layout` assembly, after `layout.addWidget(self.printer_combo)`, add:

```python
layout.addWidget(self.print_mode_combo)
layout.addWidget(self.raw_zpl_target_edit)
```

In `get_current_settings`, add the two keys to the returned dict:

```python
return {
    "shared_folder": self.shared_folder_edit.text(),
    "default_printer": self.printer_combo.currentText(),
    "warehouses": warehouses,
    "print_mode": self.print_mode_combo.currentData(),
    "raw_zpl_target": self.raw_zpl_target_edit.text(),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_settings_window.py -v`
Expected: PASS (all tests, including the 3 new ones)

- [ ] **Step 5: Run ruff**

Run: `ruff check app/ui/settings_window.py tests/test_settings_window.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add app/ui/settings_window.py tests/test_settings_window.py
git commit -m "Add print mode and raw ZPL target fields to Settings"
```

---

### Task 7: Mode 2.1 — switch to `send_to_printer` and archive a PDF per print

**Files:**
- Modify: `app/ui/mode_positions_panel.py`
- Modify: `tests/test_mode_positions_panel.py`

**Interfaces:**
- Consumes: `send_to_printer(images, width_mm, height_mm, settings, output_pdf_path=None)` (Task 5).
- Produces: no new public interface — `print_current_labels()`'s signature is unchanged (`output_pdf_path: Path | None = None`), only its internals and side effects change (archives a PDF, uses `send_to_printer` instead of `print_labels`).

- [ ] **Step 1: Update the existing test that patches `print_labels` directly**

In `tests/test_mode_positions_panel.py`, `test_print_uses_label_size_from_generate_time_not_live_combo` currently patches `"app.ui.mode_positions_panel.print_labels"`. Since the panel will call `send_to_printer` instead, update it:

```python
def test_print_uses_label_size_from_generate_time_not_live_combo(monkeypatch, tmp_path):
    _app()
    settings = {
        "warehouses": SETTINGS["warehouses"],
        "label_sizes": [
            {"name": "68x38mm", "width_mm": 68, "height_mm": 38},
            {"name": "80x80mm", "width_mm": 80, "height_mm": 80},
        ],
        "default_printer": "",
        "shared_folder": str(tmp_path),
    }
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")
    panel.label_size_combo.setCurrentIndex(0)  # 68x38mm
    panel.generate()

    panel.label_size_combo.setCurrentIndex(1)  # user changes size after Generate

    calls = []
    monkeypatch.setattr(
        "app.ui.mode_positions_panel.send_to_printer",
        lambda *a, **k: calls.append(k),
    )
    panel.print_current_labels(output_pdf_path=tmp_path / "out.pdf")

    assert calls[0]["width_mm"] == 68
    assert calls[0]["height_mm"] == 38
```

(Only the monkeypatch target string changed, from `print_labels` to `send_to_printer`.)

- [ ] **Step 2: Write the new failing tests for PDF archiving**

Add to `tests/test_mode_positions_panel.py`:

```python
def test_print_current_labels_writes_archive_pdf_to_shared_folder(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")
    panel.generate()

    panel.print_current_labels(output_pdf_path=tmp_path / "out.pdf")

    archived = list((tmp_path / "printed_pdfs").glob("*.pdf"))
    assert len(archived) == 1
    assert archived[0].stat().st_size > 0
    assert "C001" in archived[0].name
    assert "H029..H030" in archived[0].name


def test_print_current_labels_skips_archive_when_send_to_printer_raises(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.generate()

    def _boom(*a, **k):
        raise OSError("printer offline")

    monkeypatch.setattr("app.ui.mode_positions_panel.send_to_printer", _boom)

    with pytest.raises(OSError):
        panel.print_current_labels()

    assert not (tmp_path / "printed_pdfs").exists()
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `pytest tests/test_mode_positions_panel.py -v`
Expected: `test_print_current_labels_writes_archive_pdf_to_shared_folder` FAILs (no `printed_pdfs` directory created yet). `test_print_current_labels_skips_archive_when_send_to_printer_raises` currently passes vacuously (nothing archives today either) — that's fine, it'll stay green through the change.

- [ ] **Step 4: Write the implementation**

In `app/ui/mode_positions_panel.py`:

Replace the import line:
```python
from app.core.print_service import print_labels
```
with:
```python
from app.core.print_service import send_to_printer
```

Add `import re` and `from datetime import datetime, timezone` to the top of the file (alongside the existing `from pathlib import Path`).

Add this module-level helper, near `_LETTER_VALIDATOR`:

```python
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def _safe_filename_component(value: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", value)
```

Replace the whole `print_current_labels` method with:

```python
def print_current_labels(self, output_pdf_path: Path | None = None) -> None:
    if not self.generated_labels:
        raise ValueError("Nothing to print - generate labels first")

    # Use the size the labels were actually rendered at, not whatever the
    # combo currently shows - the user may have changed it after Generate.
    label_size = self._generated_label_size

    send_to_printer(
        self.generated_labels,
        width_mm=label_size["width_mm"],
        height_mm=label_size["height_mm"],
        settings=self._settings,
        output_pdf_path=output_pdf_path,
    )

    warehouse_prefix = self.warehouse_combo.currentData() or ""
    shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
    if len(self.generated_codes) > 1:
        description = f"{self.generated_codes[0]}..{self.generated_codes[-1]}"
    else:
        description = self.generated_codes[0]

    archive_dir = Path(shared_folder) / "printed_pdfs"
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_name = (
        f"{timestamp}_{_safe_filename_component(warehouse_prefix)}"
        f"_{_safe_filename_component(description)}.pdf"
    )
    send_to_printer(
        self.generated_labels,
        width_mm=label_size["width_mm"],
        height_mm=label_size["height_mm"],
        settings=self._settings,
        output_pdf_path=archive_dir / archive_name,
    )

    log_path = Path(shared_folder) / "audit_log.csv"
    append_print_log(
        log_path,
        mode="positions",
        warehouse_prefix=warehouse_prefix,
        count=len(self.generated_codes),
        description=description,
    )
```

The archive write always runs after the primary `send_to_printer` call succeeds, regardless of whether the caller passed an explicit `output_pdf_path` — if the primary call raises, execution never reaches the archive block, so nothing is archived (covered by Step 2's second test).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_mode_positions_panel.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Run ruff**

Run: `ruff check app/ui/mode_positions_panel.py tests/test_mode_positions_panel.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add app/ui/mode_positions_panel.py tests/test_mode_positions_panel.py
git commit -m "Route Mode 2.1 printing through send_to_printer and archive a PDF per print"
```

---

### Task 8: Mode 2.2 — switch to `send_to_printer`

**Files:**
- Modify: `app/ui/mode_inventory_panel.py`
- Modify: `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes: `send_to_printer(images, width_mm, height_mm, settings, output_pdf_path=None)` (Task 5).
- Produces: no new public interface — `print_checked_items()`'s signature and behavior are unchanged except it now goes through `send_to_printer` instead of calling `print_labels` directly (per design §2, Mode 2.2 does NOT get PDF archiving in this plan — its existing debug-PDF-per-print behavior already covers a similar need and is left as-is).

- [ ] **Step 1: Update the implementation**

In `app/ui/mode_inventory_panel.py`, replace the import line:
```python
from app.core.print_service import print_labels
```
with:
```python
from app.core.print_service import send_to_printer
```

Replace both `print_labels(...)` calls inside `print_checked_items`:

```python
send_to_printer(
    images,
    width_mm=INVENTORY_LABEL_WIDTH_MM,
    height_mm=INVENTORY_LABEL_HEIGHT_MM,
    settings=self._settings,
    output_pdf_path=output_pdf_path,
)

shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
Path(shared_folder).mkdir(parents=True, exist_ok=True)
now = datetime.now(timezone.utc).astimezone()
debug_pdf_path = Path(shared_folder) / f"inventory_label_preview_{now:%Y%m%d_%H%M%S}.pdf"
send_to_printer(
    images,
    width_mm=INVENTORY_LABEL_WIDTH_MM,
    height_mm=INVENTORY_LABEL_HEIGHT_MM,
    settings=self._settings,
    output_pdf_path=debug_pdf_path,
)
```

(This replaces the two existing `print_labels(...)` calls in place — same order, same surrounding code. The first no longer takes `printer_name=...` directly; `send_to_printer` derives it from `settings`.)

- [ ] **Step 2: Update the four tests that patch `print_labels` directly**

In `tests/test_mode_inventory_panel.py`, four tests reference `"app.ui.mode_inventory_panel.print_labels"`. Change each occurrence to `"app.ui.mode_inventory_panel.send_to_printer"` (the patched callable's behavior/assertions are unchanged, only the target name):

- `test_print_checked_items_passes_generated_date_in_ddmmyyyy_format`:
  ```python
  monkeypatch.setattr("app.ui.mode_inventory_panel.send_to_printer", lambda *a, **k: None)
  ```
- `test_print_checked_items_passes_structured_fields_to_renderer`:
  ```python
  monkeypatch.setattr("app.ui.mode_inventory_panel.send_to_printer", lambda *a, **k: None)
  ```
- `test_print_failure_reports_print_failed_and_skips_audit_log`:
  ```python
  monkeypatch.setattr("app.ui.mode_inventory_panel.send_to_printer", _boom)
  ```
- `test_audit_log_failure_reports_distinct_warning_after_successful_print`:
  ```python
  monkeypatch.setattr(
      "app.ui.mode_inventory_panel.send_to_printer",
      lambda *a, **k: print_calls.append(True),
  )
  ```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: PASS (all tests). Before Step 1/2's edits this suite would FAIL (the four tests above patch a name — `print_labels` — that the panel no longer calls, so their assertions on call counts/behavior would silently observe the real `print_labels` never being invoked or, worse, the real `send_to_printer` running unmocked); running it now confirms the rename closed that gap.

- [ ] **Step 4: Run ruff**

Run: `ruff check app/ui/mode_inventory_panel.py tests/test_mode_inventory_panel.py`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_inventory_panel.py tests/test_mode_inventory_panel.py
git commit -m "Route Mode 2.2 printing through send_to_printer"
```

---

### Task 9: `label_renderer.py` — extract QR+caption layout helpers

**Files:**
- Modify: `app/core/label_renderer.py`
- Modify: `tests/test_label_renderer.py`

**Interfaces:**
- Consumes: `_fit_text`, `generate_qr_image` (both already in the module).
- Produces: `_place_qr_top(...)` / `_place_qr_bottom(...)` (module-private helpers, no external consumers). `render_inventory_label`'s public signature and pixel output are unchanged.

- [ ] **Step 1: Write the failing (well, currently-passing) characterization test first**

This task is a pure refactor — no behavior change — so the safety net is a golden-hash regression test capturing the *current* pixel output, added before touching the implementation.

Add to `tests/test_label_renderer.py` (add `import hashlib` at the top):

```python
import hashlib


def test_render_inventory_label_pixel_output_is_stable():
    img = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100, dpi=203,
    )
    assert hashlib.sha256(img.tobytes()).hexdigest() == (
        "a99810c2440008dca358dd0e16ba4e5b30c5e6745864f105c522372e5bcfc4ce"
    )
```

- [ ] **Step 2: Run test to confirm it passes against the current implementation**

Run: `pytest tests/test_label_renderer.py::test_render_inventory_label_pixel_output_is_stable -v`
Expected: PASS (this hash was computed from the current, pre-refactor code — it's the baseline the refactor must not disturb).

- [ ] **Step 3: Extract the two layout helpers**

In `app/core/label_renderer.py`, add these two functions right after `_fit_text` and before `render_inventory_label`:

```python
def _place_qr_top(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    data: str,
    caption_text: str,
    qr_x: int,
    caption_x: int,
    top_y: int,
    qr_size: int,
    font,
    caption_max_width: int,
    gap: int,
) -> None:
    qr_image = generate_qr_image(data).resize((qr_size, qr_size))
    canvas.paste(qr_image, (qr_x, top_y))
    caption = _fit_text(draw, caption_text, font, caption_max_width)
    draw.text((caption_x, top_y + qr_size + gap), caption, fill="black", font=font)


def _place_qr_bottom(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    data: str,
    caption_text: str,
    qr_x: int,
    caption_x: int,
    bottom_y: int,
    qr_size: int,
    font,
    caption_max_width: int,
    gap: int,
) -> None:
    qr_y = bottom_y - qr_size
    caption = _fit_text(draw, caption_text, font, caption_max_width)
    caption_bbox = draw.textbbox((0, 0), caption, font=font)
    caption_height = caption_bbox[3] - caption_bbox[1]
    draw.text((caption_x, qr_y - caption_height - gap), caption, fill="black", font=font)
    qr_image = generate_qr_image(data).resize((qr_size, qr_size))
    canvas.paste(qr_image, (qr_x, qr_y))
```

- [ ] **Step 4: Replace the four duplicated blocks in `render_inventory_label`**

Replace this block (SKU, Position, Expiry, Batch placement — everything between computing `right_caption_max_width` and the divider-line drawing) in `render_inventory_label`:

```python
    # SKU: top of the left column, bold caption below it.
    sku_qr = generate_qr_image(sku).resize((primary_size, primary_size))
    canvas.paste(sku_qr, (left_x, content_y0))
    sku_caption = _fit_text(draw, sku, bold_font, left_caption_max_width)
    draw.text((left_x, content_y0 + primary_size + gap), sku_caption, fill="black", font=bold_font)

    # Position: bottom of the left column, bold caption above it.
    position_qr_y = content_y0 + content_height - primary_size
    position_caption = _fit_text(draw, position_code, bold_font, left_caption_max_width)
    position_bbox = draw.textbbox((0, 0), position_caption, font=bold_font)
    position_caption_height = position_bbox[3] - position_bbox[1]
    draw.text(
        (left_x, position_qr_y - position_caption_height - gap),
        position_caption,
        fill="black",
        font=bold_font,
    )
    position_qr = generate_qr_image(position_data).resize((primary_size, primary_size))
    canvas.paste(position_qr, (left_x, position_qr_y))

    right_caption_max_width = secondary_size - gap

    # Expiry: top of the right column, caption below it. Omitted if blank.
    if expiry:
        expiry_qr = generate_qr_image(expiry).resize((secondary_size, secondary_size))
        canvas.paste(expiry_qr, (right_x, content_y0))
        expiry_caption = _fit_text(draw, expiry, caption_font, right_caption_max_width)
        draw.text(
            (right_x + gap, content_y0 + secondary_size + gap),
            expiry_caption,
            fill="black",
            font=caption_font,
        )

    # Batch: bottom of the right column, caption above it. Omitted if blank.
    if batch:
        batch_qr_y = content_y0 + content_height - secondary_size
        batch_caption = _fit_text(draw, batch, caption_font, right_caption_max_width)
        batch_bbox = draw.textbbox((0, 0), batch_caption, font=caption_font)
        batch_caption_height = batch_bbox[3] - batch_bbox[1]
        draw.text(
            (right_x + gap, batch_qr_y - batch_caption_height - gap),
            batch_caption,
            fill="black",
            font=caption_font,
        )
        batch_qr = generate_qr_image(batch).resize((secondary_size, secondary_size))
        canvas.paste(batch_qr, (right_x, batch_qr_y))
```

with:

```python
    # SKU: top of the left column, bold caption below it.
    _place_qr_top(
        canvas, draw, sku, sku, left_x, left_x, content_y0,
        primary_size, bold_font, left_caption_max_width, gap,
    )

    # Position: bottom of the left column, bold caption above it.
    _place_qr_bottom(
        canvas, draw, position_data, position_code, left_x, left_x,
        content_y0 + content_height, primary_size, bold_font, left_caption_max_width, gap,
    )

    right_caption_max_width = secondary_size - gap

    # Expiry: top of the right column, caption below it. Omitted if blank.
    if expiry:
        _place_qr_top(
            canvas, draw, expiry, expiry, right_x, right_x + gap, content_y0,
            secondary_size, caption_font, right_caption_max_width, gap,
        )

    # Batch: bottom of the right column, caption above it. Omitted if blank.
    if batch:
        _place_qr_bottom(
            canvas, draw, batch, batch, right_x, right_x + gap,
            content_y0 + content_height, secondary_size, caption_font, right_caption_max_width, gap,
        )
```

- [ ] **Step 5: Run tests to verify nothing changed**

Run: `pytest tests/test_label_renderer.py -v`
Expected: PASS, all tests including `test_render_inventory_label_pixel_output_is_stable` — the hash from Step 2 must still match. If it doesn't, the refactor introduced a pixel difference; compare the replaced block against the helper calls argument-by-argument (this is the exact bug class this test exists to catch).

- [ ] **Step 6: Run the full test suite and ruff**

Run: `pytest -v && ruff check .`
Expected: all tests PASS, no ruff errors. This is the last task in the plan — this step confirms the whole feature (Tasks 1-9) is consistent end to end.

- [ ] **Step 7: Commit**

```bash
git add app/core/label_renderer.py tests/test_label_renderer.py
git commit -m "Extract QR+caption placement helpers in render_inventory_label"
```
