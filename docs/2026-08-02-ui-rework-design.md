# UI Rework — Design — 2026-08-02

Amends [the stabilization patch plan](docs/2026-08-02-stabilization-patch-plan.md) at
`ce31dcf` (branch `GUI-Impruvment`). Four operator-facing requests, one of which
turned out to be a data-integrity bug rather than a UI convenience.

## Decisions

| Question | Choice |
|---|---|
| "Use height" checkbox | **Delete it.** Height applies iff a height letter is entered. |
| Where uppercasing happens | **Core and UI.** Core normalizes so CSV imports are covered too. |
| Saved CSV mapping | **Auto-recall by header signature.** No named profiles. |
| Extent of the UI pass | **Both tables plus main window and Settings** — one coherent phase. |

## 1. Barcode/text case mismatch (new §0.7, Phase 0)

### Problem

The operator's "letters should go to caps" request is a symptom. The cause is
that only the *display* is uppercased:

- [position_generator.py:108](app/core/position_generator.py#L108) —
  `display_position_code` ends in `.upper()`.
- [mode_positions_panel.py:194-195](app/ui/mode_positions_panel.py#L194-L195) —
  `barcode_data` is `f"{warehouse_prefix}{code}"`, the raw code.

Confirmed on the audited tree:

```
generate_position_codes("h","1","1","a","a")  ->  ["h001a"]
barcode payload:  "Ch001a"
printed text:     "H-001-A"
```

The label reads `H-001-A` and scans as `Ch001a`. Same defect class as §0.1–§0.5:
a wrong label prints with no warning. Inventory mode has it too —
[mode_inventory_panel.py:197-198](app/ui/mode_inventory_panel.py#L197-L198)
uppercases `position_code` for display and leaves `position_data` raw.

### Fix

Normalize in core, at the two functions every entry path already routes through:

- `format_position_code` — uppercase `corridor` and `height` before composing.
- `parse_position_code` — uppercase before matching; return uppercase parts.

`codes_from_csv_rows`, `items_from_csv_rows`, both panels and `display_position_code`
inherit the normalization without changes of their own. The UI mask (§2) is then
an affordance, not the correctness boundary.

### Interaction with §0.3 and §0.4

Fold these together rather than fixing three times:

- §0.3 (corridor must be exactly one ASCII letter) — the check lands in the same
  edit to `format_position_code`.
- §0.4 (height ranges span punctuation) — with both ends uppercased first, the
  planned "both ends must be letters of the same case" rule reduces to "both ends
  must be `A`–`Z`". Iterate over letters only, no `chr(ord(...))` walk through
  `[`, `\`, `]`, `^`, `_`, `` ` ``.

### Tests

- Lowercase input round-trip: the letters in the barcode payload equal the letters
  in `display_position_code` output, for typed input and for CSV rows.
- `parse_position_code("h001a")` returns `("H", "001", "A")`.
- `generate_position_codes("H","1","1","A","z")` raises rather than emitting
  punctuation codes (the §0.4 repro case).

### Migration note

This changes printed payloads for anyone who has been typing lowercase:
`Ch001a` becomes `CH001A`. Labels already on shelves with lowercase payloads will
not match newly printed ones. Uppercase is what the spec requires (`C001H029A`),
so the change is correct — but it is a real-world reprint, not a silent fix.
Call it out in the release note.

## 2. Letter fields auto-uppercase (new §4.6)

[mode_positions_panel.py:36](app/ui/mode_positions_panel.py#L36),
[:66-67](app/ui/mode_positions_panel.py#L66-L67),
[:76-80](app/ui/mode_positions_panel.py#L76-L80)

Replace the validator-plus-length pair on `corridor_edit`, `height_from_edit` and
`height_to_edit` with Qt's own input mask:

```python
edit.setInputMask(">a")     # one optional ASCII letter, forced uppercase
```

Verified against PySide6 in this venv: empty `text()` is `""` (so the existing
`text() or None` logic is unaffected), typing `h` yields `"H"`, `setText("a")`
yields `"A"`.

Deletes `_LETTER_VALIDATOR`, three `setValidator` calls, three `setMaxLength(1)`
calls, and the `QRegularExpression` / `QRegularExpressionValidator` imports.

**Test:** typing lowercase into each of the three fields leaves uppercase in
`text()`.

## 3. Delete the "Use height" checkbox (new §4.7)

[mode_positions_panel.py:74](app/ui/mode_positions_panel.py#L74),
[:102](app/ui/mode_positions_panel.py#L102),
[:149-150](app/ui/mode_positions_panel.py#L149-L150)

The checkbox is derivable state: with the requested behaviour ("typing a height
letter enables height"), it can only ever disagree with the fields. Remove it and
the branch in `generate()`; height applies iff `height_from_edit.text()` is
non-empty. `height_to` already defaults to `height_from` in core.

Nothing in `tests/` references `height_enabled_check` — verified by grep.

**Test:** empty height fields produce codes with no height suffix; a height
letter alone produces the single-height range.

## 4. Table and window sizing (new §4.8, extends §4.4, absorbs §4.1/§4.5)

### 4a. CSV import dialog

[csv_import_dialog.py:44-58](app/ui/csv_import_dialog.py#L44-L58)

Two defects visible in the operator's screenshot:

- Nine mapping combos stacked in a `QVBoxLayout` above the preview push the table
  into the remaining space; the preview is clipped at the bottom of the dialog.
- `QHeaderView.ResizeMode.Stretch` divides 900 px across nine columns, so every
  header truncates — `SKU (required)` renders as `KU (required`, and
  `Expiry (optional)` as `xpiry (optiona`.

Fix:

- Header mode `ResizeToContents` with `setStretchLastSection(False)` and
  horizontal scrolling, so a column is never narrower than its header.
- Mapping form and preview table in a `QSplitter(Qt.Vertical)` — the operator can
  give the preview the space, and the split position persists with the geometry.
- Persist dialog geometry (see 4d).

### 4b. Inventory items table

[mode_inventory_panel.py:70-71](app/ui/mode_inventory_panel.py#L70-L71),
[:143-149](app/ui/mode_inventory_panel.py#L143-L149)

As already planned in §4.4, unchanged in intent: filter box over SKU/name/position,
stretched header, live "N of M selected", sorting enabled.

**Ordering constraint, not optional:** `checked_items()` maps table row →
`self.items[row]`. Enabling sorting before storing the item on the row
(`Qt.ItemDataRole.UserRole`) prints the wrong items. The `UserRole` change lands
in the same commit as `setSortingEnabled(True)`, never before it, with a test that
sorts and then asserts `checked_items()` still returns the checked items.

### 4c. Settings window

[settings_window.py:78-85](app/ui/settings_window.py#L78-L85) — §4.1 as written:
`QFormLayout` with labels, `QGroupBox`es for Storage / Printing / Warehouses, help
text under the ZPL target, and save-time validation.

### 4d. Main window

From §4.5: persist window geometry and the last-used template per mode; `Ctrl+P`
print, `Ctrl+O` import, `Ctrl+,` settings; status bar for non-error messages.

Geometry and the dialog geometry from 4a share one helper — `QSettings` rather
than `settings.json`, since geometry is per-machine and must not travel through
the shared folder.

**Out of this phase:** the light/dark theme toggle stays last and optional, as in
the existing plan.

## 5. CSV mapping auto-recall (promotes §3.5)

### Behaviour

On `load_csv`, compute a signature from the header row. If a mapping is stored for
that signature under the current mode, apply it to the combos. On accept, store the
current mapping under the signature.

An unrecognised layout leaves the combos at `-- none --`, as today. §3.5's other
bullet — auto-mapping an unseen header by synonym — is separate parent-plan work
and is **not** part of this rework; recall helps from the second import onward.

No save button, no profile dropdown: importing the same export tomorrow costs zero
clicks, and the operator never manages a list of profiles they did not ask for.

### Storage

New `DEFAULT_SETTINGS` key:

```python
"csv_mappings": {}   # {mode: {header_signature: {field: column_index}}}
```

- **Signature:** the ordered header row, each cell stripped and lowercased, joined
  with `\x1f`. Ordered, so a reordered export is correctly treated as a different
  format — which is what makes storing column *indexes* safe.
- **Value:** field name → column index, matching the index-based mapping from §3.3.
- **Cap:** 20 signatures per mode, oldest dropped first (dict insertion order).
  Prevents unbounded growth in a file the operator never sees.

### Dependencies

Both are hard, and both are already in the plan:

- **§3.3 first.** The stored value is a column index; mapping by index is §3.3's
  change. Storing header *names* instead would re-introduce the duplicate-header
  bug on every recalled mapping.
- **§1.1 first.** A new `DEFAULT_SETTINGS` key needs the merge-over-defaults load
  from §1.1, or a `settings.json` written by an older build has no `csv_mappings`
  key and the recall path raises on first import.

### Tests

- Same header row twice: second `load_csv` pre-selects the first import's columns.
- Different header row: combos stay at the auto-mapped/none state.
- Duplicate header names (`['code','name','code']`): the recalled mapping resolves
  to the originally chosen column, not the first match by name.
- 21st distinct signature evicts the oldest, not the newest.
- A `settings.json` with no `csv_mappings` key loads and imports without error.

## Execution order

Position within the existing plan's phases:

| Item | Phase | Depends on |
|---|---|---|
| §0.7 case normalization (with §0.3, §0.4 folded in) | 0 | — |
| §4.6 input masks | 4 | §0.7 (core is the correctness boundary) |
| §4.7 delete height checkbox | 4 | — |
| §3.5 mapping auto-recall | 3 | §3.3, §1.1 |
| §4.8 dialog sizing | 4 | — |
| §4.4 inventory table | 4 | `UserRole` fix in the same commit |
| §4.1 Settings, §4.5 main window | 4 | — |

§0.7 is Phase 0 work and lands with the other data-integrity fixes. Everything
else sits in its existing phase; the UI items are the largest phase and stay last.

## Out of scope

- Named CSV mapping profiles — auto-recall first, per decision. Revisit only if one
  mapping per header layout proves insufficient.
- Light/dark theme toggle — remains the last cosmetic item in §4.5.
- Modes 2.3 and 2.4 — unchanged non-goal.
