# Raw ZPL Printing + Label Layout Cleanup — Design

Status: Approved (brainstorming stage). No code written yet.
Supersedes the deferred "raw ZPL printing backend" item in
`docs/superpowers/specs/2026-07-30-barcode-label-generator-design.md` (§12),
which gated this on OS-driver printing proving unreliable. It has: printing
through `QPrinter`/OS driver to the Citizen CL-E300 sometimes produces
distorted/incorrect output ("криві формати") that's difficult to fix at the
driver layer.

## 1. Problem

Two related pain points, both confirmed by the user in practice (not
speculative):

1. Driver-based printing (`app/core/print_service.py`, `QPrinter`) to the
   Citizen CL-E300 (203 DPI, USB) intermittently produces wrong-looking
   output, and the driver layer is hard to debug/adjust.
2. Manual PIL positioning math in `label_renderer.py`
   (`render_inventory_label` especially) is verbose and repetitive — the
   same "QR + caption, top or bottom of a column" arithmetic is written out
   four times — making layout changes error-prone.

## 2. Scope decisions (from brainstorming)

- **Printer connection**: USB (confirmed). Design targets USB delivery on
  both Windows and Ubuntu; network/other connections are out of scope.
- **Raw ZPL is additive, not a replacement.** `QPrinter`/OS-driver printing
  stays as-is and remains the default. Raw ZPL is a second, user-selectable
  print mode in Settings. PDF export/preview always uses the `QPrinter`
  path regardless of mode — raw ZPL has no PDF concept.
- **`zebrafy` is added as a real dependency** for PIL Image → ZPL encoding.
  It consumes the same `PIL.Image` that `label_renderer.py` already
  produces, so no rendering changes are needed to use it. Its value (correct
  `^GFA` graphic-field encoding, incl. compression) is fiddly, focused,
  low-risk to depend on, and already builds on Pillow (already a
  dependency).
- **`python-escpos` and `blabel` are explicitly NOT added as dependencies.**
  - `python-escpos`'s actual command layer (ESC/POS) doesn't apply — the
    CL-E300 speaks ZPL-II/DPL/EPL2 (confirmed via Citizen's Cross-Emulation
    spec), not ESC/POS. Only its connection-transport pattern is useful
    (`Win32Raw`: RAW-datatype spooler bypass on Windows; `File`: writing
    straight to a `/dev/usb/lp*` device node on Linux) — cheap enough
    (~15-20 lines, one of them stdlib-only) to reimplement directly rather
    than pull in a library whose main purpose goes unused.
  - `blabel`'s value (HTML/CSS + Jinja2 label templates) would fix the
    layout-maintainability pain point, but its `WeasyPrint` dependency pulls
    in system-level Cairo/Pango/GDK-PixBuf libraries — exactly the kind of
    fragile cross-platform install this change is trying to get away from
    on a Win10/11 + Ubuntu app. Its underlying idea (declarative,
    non-duplicated box positioning) is adapted directly into small PIL-based
    helpers instead.
- **`label_renderer.py` gets a light internal refactor**, not a rendering
  engine swap: extract the repeated QR+caption placement logic into 1-2
  helper functions. Visual output is unchanged.

## 3. Components

- **`app/core/zpl_print_service.py`** (new):
  - `image_to_zpl(image: Image.Image) -> bytes` — wraps
    `zebrafy.ZebrafyImage(image, ...).to_zpl()`.
  - `send_raw_windows(printer_name: str, data: bytes) -> None` — `win32print`
    RAW-datatype job (`StartDocPrinter`/`WritePrinter`/...), bypasses the
    driver's rendering pipeline.
  - `send_raw_linux(device_path: str, data: bytes) -> None` —
    `Path(device_path).write_bytes(data)`.
  - `print_labels_zpl(images, width_mm, height_mm, target: str) -> None` —
    converts each label and sends it, dispatching by `sys.platform`.

- **`app/core/print_service.py`**: add `send_to_printer(images, width_mm,
  height_mm, settings, output_pdf_path=None)` as the single entry point
  both mode panels call:
  - `output_pdf_path` given → always the existing `QPrinter`/PDF path,
    unchanged.
  - else `settings["print_mode"] == "raw_zpl"` → `print_labels_zpl(...)`.
  - else → existing `print_labels(...)` (QPrinter/driver, default,
    unchanged behavior).
  - `mode_positions_panel.py:206` and `mode_inventory_panel.py:194,206`
    switch their `print_labels(...)` call to `send_to_printer(...,
    settings=self._settings, ...)` — one choke point instead of duplicating
    the mode branch in both panels.

- **`app/core/config.py`**: `DEFAULT_SETTINGS` gains `"print_mode": "driver"`
  and `"raw_zpl_target": ""`.

- **`app/ui/settings_window.py`**: a `QComboBox` (Driver / Raw ZPL) and a
  `QLineEdit` for the raw target, following the existing
  `printer_combo`/`shared_folder_edit` pattern. Placeholder text is
  platform-aware (`/dev/usb/lp0` example on Linux, raw-printer-name example
  on Windows). No auto-discovery UI for v1 — the user fills in the target
  once.

- **`app/core/label_renderer.py`**: extract the duplicated "QR image +
  caption, anchored top or bottom of a column" positioning logic out of
  `render_inventory_label` into a small helper (e.g.
  `_place_qr_with_caption(...)`), collapsing ~4x near-identical blocks.
  No visual/behavioral change.

## 4. Data flow

Unchanged (driver mode, default):
`PIL Image (label_renderer) → QPrinter → OS driver → CL-E300`

New (raw ZPL mode, opt-in via Settings):
`PIL Image (label_renderer, unchanged) → image_to_zpl (zebrafy) → ZPL bytes → send_raw_windows/linux → CL-E300 (USB)`

PDF export/preview: always `PIL Image → QPrinter → PDF`, regardless of
`print_mode`.

## 5. Error handling

No silent fallback between print modes — a raw-ZPL failure surfaces as an
error, it does not quietly retry through the driver path (unexpected
behavior swap would be worse than a clear failure). Failures are caught at
the same layer that already catches `ValueError` from
`print_current_labels()` in the mode panels, and shown via the existing
`QMessageBox.warning` pattern:

- `zebrafy` conversion failure (bad image) → `ValueError`/library exception.
- `OSError` writing to the Linux device node (missing device, permissions).
- `pywintypes.error` from `win32print` (invalid/offline printer name).

## 6. Testing

CI already runs `ubuntu-latest` + `windows-latest`, so both raw-transport
branches get real (non-mocked-OS) coverage without physical hardware:

- `image_to_zpl()`: dummy `PIL.Image` in, assert output is a well-formed ZPL
  block (starts `^XA`, ends `^XZ`).
- `send_raw_linux()`: write target is a `tmp_path` file; assert written
  bytes match.
- `send_raw_windows()`: `win32print` calls monkeypatched; assert
  `StartDocPrinter` is called with `datatype="RAW"` and the right bytes
  reach `WritePrinter`.
- `send_to_printer()`: monkeypatch both branches, assert correct dispatch
  for `output_pdf_path` set / `print_mode == "raw_zpl"` / default.
- `label_renderer.py` refactor: existing rendering tests
  (`tests/test_label_renderer.py`) must keep passing unchanged — the
  refactor must not alter pixel output.

## 7. Explicitly deferred

- `python-escpos` and `blabel` as dependencies (patterns adapted instead,
  see §2).
- Auto-fallback from raw ZPL to driver mode on failure.
- CUPS raw-queue-based delivery on Linux (direct device-node write chosen
  instead — simpler, no CUPS queue reconfiguration required).
- Printer/device auto-discovery UI (manual target entry for v1).
- Network or Bluetooth printer connections (USB only, per confirmed
  hardware setup).

## 8. Dependencies

- `zebrafy` (new, cross-platform).
- `pywin32` (new, Windows-only — `pywin32; sys_platform == "win32"` in
  `requirements.txt`).
