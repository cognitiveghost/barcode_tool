Label templates
===============

The "default" folder in each mode is owned by the app. It is REWRITTEN on
every launch so that shipped template fixes reach this shared folder - any
edit you make there will be lost.

To customise a label, copy the whole "default" folder to a sibling with a
different name and edit the copy:

    positions/default/   <- app-owned, overwritten
    positions/my-aisle/  <- yours, never touched

Each preset folder needs three files:

    template.html   Jinja2 markup, rendered once per label
    style.css       @page size must match meta.json
    meta.json       {"name": "...", "width_mm": 150, "height_mm": 100}

The name from meta.json is what appears in the template dropdown. A preset
with a missing or malformed meta.json is skipped rather than breaking the
app for everyone else using this folder.
