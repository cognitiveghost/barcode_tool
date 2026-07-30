# Barcode Label Generator — Design

Status: Approved (brainstorming stage). No code written yet.
Source spec: `Essential technical specifications.txt` (original, Ukrainian).

## 1. Purpose

A desktop application to generate and print barcode/text labels for a
warehouse: storage-position labels, product/inventory labels driven by CSV
import, single product barcode+text labels, and plain text labels (with or
without sequence numbering). Runs locally on Windows 10/11 and Ubuntu 25+,
usable by multiple people who share label templates, warehouse config, and
an audit log through a shared network folder.

## 2. Scope decisions (from brainstorming)

These were open questions in the original spec, resolved during
brainstorming:

- **App architecture**: native desktop GUI (not a client-server web app).
  Each user runs their own copy of the app locally.
- **Multi-user sharing**: no application server. Users point the app (via
  Settings) at a shared network folder (SMB share / mapped drive) that holds
  warehouse config, label templates, and the audit log. Concurrency is
  handled at the filesystem level (plain files), not a database.
- **Label layout**: fixed templates per label size/mode for v1. No
  WYSIWYG drag-and-drop editor (may be added later as a separate feature).
- **CSV import**: interactive column mapping (user maps CSV columns to
  fields like SKU/Name/Position/Batch/Expiry at import time), not a fixed
  required header format. One shared import component is reused by every
  mode that accepts CSV.
- **Printing target**: thermal label printers, confirmed hardware is a
  Citizen CL-E300 (203 DPI). Printing goes through the OS-installed printer
  driver via Qt's `QPrinter`, not raw ZPL/command-language generation. If
  driver-based printing proves unreliable at 203 DPI, raw ZPL is a fallback
  to revisit later — not built now.
- **Distribution**: standalone executable per OS (PyInstaller), no Python
  installation required by end users.
- **Audit log**: a plain log file (CSV/text) in the shared folder, one entry
  per **print** action (not per generation/preview): timestamp, OS
  username, mode, warehouse prefix, count, short range description. No
  database.
- **MVP priority**: Mode 2.1 (warehouse position labels) ships first. It
  establishes the full generate → render → preview → print → log pipeline
  that every other mode reuses.
- **GUI toolkit**: PySide6 (Qt). Chosen over Tkinter for built-in QSS
  theming and `QPrinter`/`QPrintPreviewDialog` for OS-driver printing
  without hand-rolling print plumbing.

## 3. Tech stack

| Concern | Choice | Why |
|---|---|---|
| GUI | PySide6 (Qt) | QSS themes, `QPrinter`/`QPrintPreviewDialog`, mature widget set |
| Barcode | `python-barcode` (Code128) | standard, maintained, sufficient for alphanumeric position/SKU codes |
| QR code | `qrcode` (Phase 5, not MVP) | added later behind the same barcode-engine interface |
| Image composition | `Pillow` | compose barcode + text into one label image/canvas |
| Config & data | JSON files (settings, warehouses, templates) + CSV/text audit log | no database — data volume doesn't justify one; lives in the shared folder |
| Packaging | PyInstaller (onefile) | one `.exe` on Windows, one binary on Ubuntu, no Python required |

## 4. Module breakdown

```
core/
  barcode_engine.py     — text -> barcode/QR image
  label_renderer.py     — compose barcode + text into a label for a given size/template
  position_generator.py — corridor/number-range/height-range -> list of position codes
  csv_import.py         — CSV parsing + interactive column mapping
  print_service.py      — send a rendered label batch to QPrinter
  audit_log.py          — append print events to the shared log file
  config.py             — read/write JSON settings (shared folder path, warehouses, default printer, label sizes)
ui/
  main_window.py
  settings_window.py
  mode_positions_panel.py   (2.1)
  mode_inventory_panel.py   (2.2)
  mode_product_panel.py     (2.3)
  mode_text_panel.py        (2.4)
```

Each `core/` module has a single responsibility and no dependency on `ui/`,
so the generation/rendering/printing logic is testable without a GUI.

## 5. Mode 2.1 — Warehouse position labels (MVP)

**Inputs (UI form):**
- Warehouse prefix (e.g. `C001`) — picked from warehouses configured in Settings
- Corridor letter (e.g. `H`)
- Position number range: from / to (e.g. `029`–`090`). Zero-padding width
  is inferred from the digit count of the typed value (`029` → 3 digits).
- Height: **disabled** / single letter / letter range (e.g. `A`–`F`)
- Custom user text (separate, optional field) — prefix or suffix appended
  to the *visible* text only

**Generation rule:** for each number in the range, for each height letter
in the range (or no iteration if height is disabled), emit one code
`{corridor}{padded_number}{height?}`.

Example (corridor H, 029–030, height A–C):
`H029A, H029B, H029C, H030A, H030B, H030C`

**Barcode content vs visible text** (clarifies the ambiguous spec line "the
barcode must have its own trait so a scanner can actually read the
position" — interpreted as: the warehouse prefix must be embedded in the
scanned data so identical position codes from different warehouses don't
collide in a shared WMS/scanner, while staying invisible to a human reading
the label):
- Barcode (Code128) encodes `{warehouse_prefix}{corridor}{padded_number}{height}`
  → `C001H029A`.
- Visible text below the barcode shows `{corridor}{padded_number}{height}`
  plus the optional custom user text → e.g. `H029A — Promo zone`. The
  warehouse prefix is never rendered as text.

**Alternate input — CSV:** instead of a manual range, the user imports a
CSV of ready-made positions through the same interactive column-mapping
component used by Mode 2.2 (columns can map to corridor/number/height, or
to a single already-formed position code).

**Validation:** `from ≤ to` on the number range; height range must respect
alphabet order (A→F); an empty result set (0 positions) is blocked with a
message before it reaches rendering/printing.

## 6. Mode 2.2 — Inventory from CSV

User imports a CSV (columns typically SKU, Name, Position, optionally
Batch and Expiry) via the shared interactive column-mapping component. Each
row becomes one label containing:
- Barcode of the SKU (Code128)
- Text: product name, batch/expiry when present
- Barcode of the position, using the same hidden-warehouse-prefix rule as
  Mode 2.1 (the warehouse is selected once for the whole import, same as
  2.1's warehouse picker)

## 7. Mode 2.3 — Product barcode + text

One code (e.g. SKU or arbitrary string) rendered as a barcode, with
arbitrary text below it. Supports both a manual single-item form and bulk
CSV import (reusing the same import component as 2.1/2.2).

## 8. Mode 2.4 — Text-only / multi-up labels

Two sub-cases:
- Free text label with no barcode.
- Sequence labels ("1-4, 2-4, 3-4, 4-4"): user enters a total count N, the
  app generates N labels with text `{i}-{N}` (separator is configurable)
  plus optional free text.

## 9. Settings

- Warehouses: list of (name, prefix) pairs
- Shared network folder path (config, templates, audit log location)
- Default printer
- Label sizes: 3 built-in presets (100x150mm, 68x38mm, 80x80mm) + custom
  size (width/height in mm)
- Theme: light/dark toggle (QSS)

## 10. Printing

`QPrintPreviewDialog` (built-in Qt widget) is shown before committing a
print job. On confirm, a `QPrinter` is configured with page size equal to
the label size in mm and sends the job through the OS driver. A batch of N
labels is a single print job with N pages.

## 11. Audit log

One line appended to a CSV file in the shared folder **at print time**
(not at generation/preview time): timestamp, OS username, mode, warehouse
prefix, count, short description of the range/items printed.

## 12. Explicitly deferred (not in this design's implementation scope)

- QR codes and other symbologies beyond Code128 (the `barcode_engine.py`
  interface is designed so this is additive later, not a rewrite)
- WYSIWYG label layout editor
- Theming beyond a light/dark toggle
- Named/reusable CSV column-mapping presets
- CI/CD for packaging
- A raw ZPL printing backend (fallback only if OS-driver printing proves
  insufficient on the Citizen CL-E300)

## 13. Roadmap (phases → future implementation plans / Todoist)

| Phase | Content |
|---|---|
| 0. Project scaffolding | Repo structure, PySide6 app shell, `config.py`, dependency setup |
| 1. MVP — Mode 2.1 | position_generator → barcode_engine → label_renderer → print preview/print → audit log; Settings v1 (warehouses, shared folder, printer, label sizes) |
| 2. CSV infrastructure | Interactive column-mapping UI + CSV parser, wired as 2.1's alternate input |
| 3. Mode 2.2 — Inventory | CSV → SKU barcode + text + position barcode per row |
| 4. Modes 2.3 and 2.4 | Product barcode+text; text-only / multi-up sequence labels |
| 5. Enhancements | QR codes, light/dark theme, custom label size UI, PyInstaller packaging (Win + Ubuntu), UX polish |
| 6. Backlog (not scheduled) | Named CSV-mapping presets, additional symbologies, WYSIWYG layout editor |

Phases 0–5 are the basis for the implementation plan and Todoist task
breakdown that follow this design.
