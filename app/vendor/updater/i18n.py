"""Identity stand-in for Fulfilment's shared/i18n.py: English only, no catalogue."""


def N_(text: str) -> str:
    return text


def _(text: str, **values) -> str:
    return text.format(**values) if values else text
