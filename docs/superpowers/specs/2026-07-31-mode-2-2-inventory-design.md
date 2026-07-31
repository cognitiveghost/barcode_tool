# Mode 2.2 — Inventory Labels — Design

Status: Approved (brainstorming stage). No code written yet.
Parent design: `docs/superpowers/specs/2026-07-30-barcode-label-generator-design.md`
(this spec supersedes that doc's §6 "Mode 2.2" — see §2 below).
Todoist: Roadmap Phase 3, task "Mode 2.2: Inventory from CSV (mode_inventory_panel.py)".

## 1. Purpose

User imports a stock/inventory CSV. Each row is one SKU at one warehouse
position. The app renders one label per row containing a SKU code, product
text, and a position code, and lets the user pick exactly which rows to
print before sending the batch to the printer.

## 2. Deviations from the parent design

The parent design doc's §6 described Code128 for the SKU and didn't address
multi-position SKUs. Resolved during this brainstorm:

- **SKU code is QR, not Code128.** This pulls the QR-code work (parent
  design §13 Phase 5, Todoist task "QR code support in barcode_engine")
  forward into this phase, scoped to `generate_qr_image` only — the rest of
  Phase 5 (theme toggle, custom label size UI, packaging) is unaffected and
  stays deferred.
- **Position code is also QR** (on this label only — Mode 2.1's own position
  barcode stays Code128, unchanged).
- **A SKU can have more than one position.** The real stock export has one
  row per SKU-position pair (the same SKU repeated across rows), not a
  delimited list in one cell. The panel needs a review/selection step so the
  user can choose which SKU+position combinations actually get printed,
  which the parent design didn't anticipate (Mode 2.1 has no such step).

## 3. Data flow

1. User picks a warehouse (single combo, same as Mode 2.1) and a label size.
2. User clicks "Import CSV...", the existing `CsvImportDialog` opens
   unmodified, maps columns to `sku / name / batch / expiry / position_code`
   (or `corridor / number / height`, same fallback Mode 2.1 already has).
3. On accept, rows are validated and turned into inventory items (§6). Rows
   that fail validation are skipped and counted, same philosophy as Mode
   2.1's CSV path.
4. Valid items populate a checkable table in the panel, one row per
   SKU-position pair, **all checked by default**. Two small buttons,
   "Select all" / "Select none", sit above the table for bulk toggling.
5. User unchecks anything they don't want, then clicks Print.
6. Print renders a label per checked row, sends the batch through the
   existing `print_service`, and appends one audit log entry (§8).

Unlike Mode 2.1, there is no separate "Generate" step — Mode 2.2 is
CSV-only (no manual single-item entry form), so the checkable table doubles
as the review step and Print does render + send in one action.

## 4. Label layout

Confirmed via mockup: SKU QR and product text share the top of the label
side by side; a divider line separates a smaller, visually subordinate
strip below holding the position QR and a small caption.

```
 ┌──────────────────────────────┐
 │ [SKU QR]   Widget XL-200      │
 │            Batch 4471          │
 │            Exp 2027-03         │
 │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
 │      [pos QR]  shelf position  │
 └──────────────────────────────┘
```

Product identity is the primary use case (picking/receiving), so it gets
the larger, top-of-label treatment; position is secondary reference
information. Text omits the batch/expiry lines when those fields are empty.

## 5. Barcode content

- SKU QR encodes the raw SKU string — no warehouse prefix. SKUs are already
  globally unique, unlike position codes.
- Position QR keeps Mode 2.1's hidden-warehouse-prefix rule: encoded data is
  `{warehouse_prefix}{position_code}`, visible text/caption never includes
  the prefix.

## 6. Validation / skip-and-continue

A row is skipped (and counted in the result summary) if:

- `sku` is empty, or
- the position code — whether taken directly from a `position_code` column
  or built from `corridor`/`number`/`height` — is empty or doesn't match
  the shape `<corridor letter><digits><optional height letter>` (e.g.
  `H011A`).

This adds a new strict-format check used only by Mode 2.2. Mode 2.1's
existing `codes_from_csv_rows` stays exactly as-is — it deliberately accepts
any ASCII string as a pre-formed position code, and changing that would be
an unrelated behavior change to a shipped feature.

`name`, `batch`, `expiry` are optional and default to `""`; they never cause
a row to be skipped.

## 7. Selection UI

Inline in the Inventory panel (not a separate dialog) — consistent with
Mode 2.1's pattern of keeping results/print controls in the panel itself.
Table columns: checkbox, SKU, Name, Position, Batch, Expiry. All rows start
checked. "Select all" / "Select none" buttons above the table handle bulk
toggling (a native Qt header checkbox would need a custom delegate for
marginal benefit over two buttons).

## 8. Audit log

Same `append_print_log` call Mode 2.1 uses, with `mode="inventory"`, the
selected warehouse prefix, `count` = number of checked rows printed, and a
description in the same "first..last" style Mode 2.1 uses, built from the
printed SKUs.

## 9. Module breakdown (additions/changes to parent design §4)

```
core/
  barcode_engine.py     — + generate_qr_image(data) -> Image.Image (new `qrcode` dependency)
  position_generator.py — + parse_position_code(code) -> (corridor, number, height); validates
                           shape only, does not rebuild/reformat the string. Mode 2.1 unaffected.
  inventory_import.py   — NEW. InventoryItem (sku, name, batch, expiry, position_code);
                           items_from_csv_rows(rows) -> (items, skipped_row_numbers);
                           INVENTORY_CSV_FIELDS for the CsvImportDialog field list.
  label_renderer.py     — + render_inventory_label(sku_data, text, position_data, width_mm,
                           height_mm, dpi) implementing the §4 layout.
ui/
  mode_inventory_panel.py — NEW. Warehouse combo, label size combo, Import CSV button,
                             checkable results table, Select all/none, Print button.
  main_window.py           — central widget becomes a QTabWidget ("Positions" / "Inventory")
                             instead of a single panel — first second-panel addition, sets
                             the pattern Modes 2.3/2.4 will reuse.
```

`requirements.txt` gains the `qrcode` dependency.

## 10. Testing approach

Mirrors the existing per-module test files:

- `tests/test_barcode_engine.py` — `generate_qr_image` produces a valid image.
- `tests/test_position_generator.py` — `parse_position_code` accepts valid
  shapes, rejects malformed ones, doesn't touch existing Mode 2.1 tests.
- `tests/test_inventory_import.py` — new; row-to-item mapping, skip-and-continue
  for missing SKU / malformed position, multiple rows per SKU preserved as
  separate items.
- `tests/test_label_renderer.py` — `render_inventory_label` composes both
  codes and text without error at each of the three built-in label sizes.
- `tests/test_mode_inventory_panel.py` — new; table population from import,
  select all/none, Print sends only checked rows, skipped-row count in the
  result summary.

## 11. Explicitly out of scope for this phase

- Named/reusable CSV column-mapping presets (already deferred at the parent
  design level, §12).
- Collapsing/grouping same-SKU rows visually in the table (each SKU-position
  pair stays its own row — grouping is a possible later UX polish, not
  needed for the core "choose what to print" requirement).
- Editing item text (name/batch/expiry) from within the app before print —
  the CSV is the source of truth.
- QR error-correction level or box-size configuration — `qrcode` defaults,
  revisit only if a real scanning-reliability problem shows up on hardware.
