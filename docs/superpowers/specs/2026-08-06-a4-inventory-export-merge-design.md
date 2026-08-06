# A4 Inventory Export: SKU/Position Merge + Quantity

Date: 2026-08-06

## Problem

The "Export table (PDF)" A4 report in Inventory mode currently prints one
row per imported CSV row, with no concept of quantity. A SKU stocked at the
same position across several rows (or the same SKU at multiple positions)
prints as repeated, unmerged rows with no total. The report needs to:

1. Merge rows into one line per unique SKU, with a QR code of the bare SKU.
2. Merge rows into one line per unique position under that SKU, with a QR
   code encoding the warehouse-prefixed position.
3. Show quantity both as a total per SKU and broken out per position.
4. Keep both QR codes comfortably scannable by a handheld/mobile scanner on
   a printed A4 sheet.

## Data model: add `quantity`

`InventoryItem` currently has no quantity field — one CSV row is one item,
implicitly one unit. This change adds a real, explicit quantity:

- `INVENTORY_CSV_FIELDS` gains `("quantity", "Quantity (optional, defaults to 1)")`.
- `InventoryItem` gains `quantity: int = 1`.
- `items_from_csv_rows`: blank/unmapped `quantity` defaults to `1`. A
  present-but-invalid value (non-numeric, zero, negative) skips the row via
  the existing `SkippedRow` mechanism, consistent with how a malformed
  `position_code` is handled today.
- `csv_mapping_memory._FIELD_SYNONYMS["quantity"]` gains `{"qty", "count", "units"}`
  so common WMS export headers auto-map without operator intervention.
- `mode_inventory_panel.TABLE_COLUMNS` gains a "Qty" column so the on-screen
  checklist shows it; `_record_for_item` exposes it to templates as
  `record["quantity"]`, stored as a string like every other record field
  (the shared record contract documented in
  `app/templates/examples/README.txt` stays "a dict of plain strings").

**Scope boundary**: quantity only feeds the A4 table export (and, if a
custom single-label template chooses to reference `{{ record.quantity }}`,
individual labels). The Print button's behavior is unchanged — one checked
row still renders and prints exactly one label. Quantity does not multiply
print copies. That's a distinct feature this change does not attempt.

## Report layout

All merging happens inside the shipped `app/templates/examples/
inventory-table/a4-table/template.html`, via Jinja's `groupby` filter —
not in Python. `render_table_pdf` keeps handing the template the flat list
of per-row records it already does; only the shipped a4-table preset
changes how it renders that list. This keeps the documented "flat list of
plain-string records" contract intact for any custom inventory-table
preset an operator has copied from this one.

Grouping: by `sku` (alphabetical, via Jinja's default `groupby` sort), then
within each SKU group by `position_code`.

Columns, in order:
1. `#` — SKU group sequence number
2. SKU (rowspan across the group)
3. Name (rowspan; first-seen value for that SKU — Name is a stable
   per-SKU attribute, unlike batch/expiry/client)
4. QR SKU — encodes the bare SKU (rowspan)
5. Total Qty — sum of `quantity` across every row for that SKU (rowspan)
6. Position — the human-readable position code, one row per unique position
   under this SKU
7. Qty — sum of `quantity` across every row sharing this SKU+position
8. QR Position — encodes `warehouse_prefix + position_code` (unchanged
   encoding from today, just deduplicated to one row per unique position)

Dropped from this report: Client, Batch, Expiry. Rationale: these are
per-lot/per-transaction attributes that can legitimately differ across the
rows being merged into one position line, and the request didn't ask for
them. They remain available on individual printed labels via the
per-record `inventory` template mode; only this consolidated table drops
them.

Mockup:

```
 #  SKU        Name              [QR SKU]   Total  Position   Qty  [QR Pos]
 1  SKU-100    Blue Widget       ▓▓▓▓▓▓▓      12    H-011-A     7   ▓▓▓▓▓▓
                                                     H-014-B     5   ▓▓▓▓▓▓
 2  SKU-200    Red Widget        ▓▓▓▓▓▓▓       4    H-020-C     4   ▓▓▓▓▓▓
```

## Pagination

Each SKU's rows are wrapped in their own `<tbody>` (HTML tables support
multiple `<tbody>` elements) with `page-break-inside: avoid`, instead of a
single `<tbody>` for the whole table. This asks WeasyPrint to avoid
splitting a SKU's rowspan block across a page boundary — a `rowspan` cell
split mid-page is a known WeasyPrint rough edge, and letting a page break
land inside one would visually break the merged cell. `<thead>` continues
to repeat on every page (existing behavior, unchanged).

Known limitation, accepted: a single SKU with enough distinct positions
that its own block exceeds one page will still overflow/split — native CSS
page-break avoidance is best-effort, not a hard guarantee. Not worth
solving for; warehouse SKUs realistically occupy a handful of positions.

## QR sizing

Both QR images grow from 12mm → 16mm. Merging collapses duplicate rows, so
there's more vertical room per page than before; a larger vector QR (no
resolution loss, SVG-based) gives more margin for a handheld/mobile scanner
reading a printed sheet at a normal working distance. Column widths in
`style.css` are resized to fit the new column set within the ~190mm usable
A4 width (210mm minus margins).

## Testing

- `tests/test_inventory_import.py`: quantity defaults to 1 when
  blank/unmapped; a valid explicit value is parsed; a non-numeric or
  non-positive value skips the row with a reason.
- `tests/test_mode_inventory_panel.py`: the new Qty column populates
  correctly in the on-screen table and in `_record_for_item`.
- `tests/test_template_renderer.py`: extend/replace
  `test_render_table_pdf_puts_every_record_on_one_native_pdf` to assert
  that duplicate SKU+position rows collapse into one decoded QR occurrence
  each (proving the merge actually happened, not just that the values are
  present), and that total/per-position quantity numbers appear in the
  extracted PDF text.
