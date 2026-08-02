from __future__ import annotations

import re

# One CSV layout per header row. Twenty covers every export format an
# operator realistically feeds this app; the cap only exists so
# settings.json cannot grow without bound.
MAX_REMEMBERED_LAYOUTS = 20

_SEPARATOR = "\x1f"  # ASCII unit separator - cannot occur in a CSV header cell

_UNSAFE_NORMALIZE_CHARS = re.compile(r"[\s_]+")

# Header names that mean the same field as the internal field key, beyond
# an exact (normalized) name match. Only fields ambiguous enough in the wild
# to need this are listed - most fields (name, client, corridor, number,
# height) rely on exact normalized matching alone.
_FIELD_SYNONYMS: dict[str, set[str]] = {
    "sku": {"article", "code"},
    "position_code": {"position", "pos", "location"},
    "expiry": {"exp", "best_before"},
    "batch": {"lot"},
}


def _normalize(value: str) -> str:
    return _UNSAFE_NORMALIZE_CHARS.sub("", value.strip().lower())


def header_signature(header: list[str]) -> str:
    return _SEPARATOR.join(cell.strip().lower() for cell in header)


def recall_mapping(settings: dict, mode: str, header: list[str]) -> dict[str, int] | None:
    by_mode = settings.get("csv_mappings", {}).get(mode, {})
    return by_mode.get(header_signature(header))


def remember_mapping(
    settings: dict,
    mode: str,
    header: list[str],
    mapping: dict[str, int | None],
) -> None:
    by_mode = settings.setdefault("csv_mappings", {}).setdefault(mode, {})
    signature = header_signature(header)
    # Re-inserting moves the layout to the end, so eviction is least-recently-saved.
    by_mode.pop(signature, None)
    by_mode[signature] = {
        field: index for field, index in mapping.items() if index is not None
    }
    while len(by_mode) > MAX_REMEMBERED_LAYOUTS:
        by_mode.pop(next(iter(by_mode)))


def auto_map_fields(header: list[str], field_names: list[str]) -> dict[str, int | None]:
    """Guess an initial mapping from normalized header names, plus a small
    synonym table for the handful of fields ambiguous enough to need it
    (see _FIELD_SYNONYMS). Returns None for any field with no match - never
    guesses wrong on purpose, only fills in the unambiguous cases."""
    normalized_header = [_normalize(cell) for cell in header]
    mapping: dict[str, int | None] = {}
    for field in field_names:
        candidates = {_normalize(field)} | {_normalize(s) for s in _FIELD_SYNONYMS.get(field, set())}
        mapping[field] = next(
            (index for index, name in enumerate(normalized_header) if name in candidates),
            None,
        )
    return mapping
