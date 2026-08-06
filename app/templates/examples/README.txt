Label templates
===============

Folders that match a name shipped with the app (e.g. "default") are owned by
the app. They are REWRITTEN on every launch so that shipped template fixes
reach this shared folder - any edit you make there will be lost.

To customise a label, copy the whole folder to a sibling with a different
name and edit the copy:

    positions/default/   <- app-owned, overwritten
    positions/my-aisle/  <- yours, never touched

Each preset folder needs three files:

    template.html   Jinja2 markup, rendered once per label
    style.css       @page size must match meta.json
    meta.json       {"name": "...", "width_mm": 150, "height_mm": 100}

The name from meta.json is what appears in the template dropdown. A preset
with a missing or malformed meta.json is skipped rather than breaking the
app for everyone else using this folder.


Record fields available in a template
======================================

Each label is rendered once per record. A record is a dict of plain
strings - what fields are available depends on which mode generated it.

Positions mode:

    code             The bare position code, e.g. "H029A" (uppercase).
    barcode_data     What the barcode/QR actually encodes: the warehouse
                     prefix + code, e.g. "C001H029A". Never shown as text -
                     the label prints its own human-readable caption instead.
    visible_text     Human-readable caption for the code, e.g. "H-029-A".
    warehouse_prefix The selected warehouse's prefix, e.g. "C001".
    user_text        Free-text the operator typed for this batch (may be
                      empty).

Inventory mode:

    sku              The item's SKU/article code.
    name             The item's description.
    client           Client name (may be empty).
    batch            Lot/batch number (may be empty).
    expiry           Expiry date, as imported (may be empty).
    position_code    Human-readable position, e.g. "H-029-A".
    position_data    What the position QR actually encodes: the warehouse
                     prefix + position code, e.g. "C001H029A".
    generated_date   The date this label was generated, e.g. "2026/08/03".

A field a template doesn't reference is simply unused - Jinja2 does not
require every record key to be consumed. A field a template references
that a record doesn't have renders as empty/falsy rather than raising, so a
typo in a variable name fails silently (a blank spot on the label) rather
than with an error - double-check spelling against the lists above when
copying a preset.


Inventory table reports (A4)
=============================

The "inventory-table" folder next to "positions" and "inventory" holds a
different kind of preset, used by the "Export table (PDF)" button in
Inventory mode rather than the Template dropdown or the Print button. It is
rendered ONCE per export, not once per record: the template gets the whole
list as `records` (each with the same fields as Inventory mode, above) and
is expected to build its own HTML `<table>` - see the shipped "a4-table"
preset. The output is a native multi-page PDF, not a rasterised bitmap, so
it stays sharp on a regular office printer regardless of page count.

label_tools helpers
====================

Templates can call anything on `label_tools`:

    label_tools.qr_code(data, border=2, **qrcode_options)
        Vector QR code as an <img> data URI. `border` is in QR "modules" -
        the shipped presets use 2 (below the 4-module spec minimum,
        verified reliable on the scanner these labels are used with -
        raise it if a future scanner misreads).

    label_tools.barcode(data, **python_barcode_options)
        Vector linear barcode (Code128 by default) as an <img> data URI,
        human-readable text hidden by default - the payload is meant to be
        invisible when it carries a warehouse prefix.

    label_tools.fit_font(text, box_width_mm, max_mm, min_mm=2.0, letter_spacing_mm=0.0)
        Largest font size (mm) that keeps `text` on one line inside a box
        of `box_width_mm`. Pass the CSS rule's own letter-spacing here too.

    label_tools.fit_font_block(text, box_width_mm, box_height_mm, max_mm, min_mm=2.0, line_height=1.25)
        Largest font size (mm) at which wrapped `text` still fits a box of
        `box_width_mm` x `box_height_mm`.

    label_tools.datamatrix, .hiro_square, .now, .pil_to_html_imgdata, .wrap
        Re-exported from blabel's own label_tools - see blabel's own
        documentation/source for these.
