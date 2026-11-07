"""Keep the UI text files in sync.

Home Assistant only builds ``translations/en.json`` from ``strings.json`` for
core integrations. A custom integration loads ``translations/en.json``
directly, so a label added only to ``strings.json`` shows up as a raw key in
the config and options forms.
"""

import json
from pathlib import Path

_BASE = Path(__file__).parent.parent / "custom_components" / "openclaw"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def test_strings_and_english_translation_match() -> None:
    strings = _flatten(_load(_BASE / "strings.json"))
    english = _flatten(_load(_BASE / "translations" / "en.json"))

    missing = sorted(strings.keys() - english.keys())
    extra = sorted(english.keys() - strings.keys())
    changed = sorted(k for k in strings.keys() & english.keys() if strings[k] != english[k])

    assert not missing, f"only in strings.json: {missing}"
    assert not extra, f"only in translations/en.json: {extra}"
    assert not changed, f"text differs: {changed}"
