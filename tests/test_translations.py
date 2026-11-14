"""Keep the UI text files in sync.

Home Assistant only builds ``translations/en.json`` from ``strings.json`` for
core integrations. A custom integration loads ``translations/en.json``
directly, so a label added only to ``strings.json`` shows up as a raw key in
the config and options forms.
"""

import json
import re
from pathlib import Path

import pytest

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


_TRANSLATIONS = _BASE / "translations"
_LANGUAGES = sorted(
    path.stem for path in _TRANSLATIONS.glob("*.json") if path.stem != "en"
)
# Names, identifiers and literals that must survive translation unchanged.
_KEEP = (
    "OpenClaw",
    "Home Assistant",
    "mTLS",
    "SSL",
    "wss://",
    "assist_satellite",
    "announce",
    "start_conversation",
    "main",
    "localhost",
    "Control UI",
)
# Words that are legitimately the same in some languages.
_SAME_AS_ENGLISH_OK = {"Host", "Port"}


def test_translated_languages_exist() -> None:
    assert len(_LANGUAGES) >= 12


@pytest.mark.parametrize("language", _LANGUAGES)
def test_translation_is_complete(language: str) -> None:
    """Every language has exactly the English keys, all with text."""
    english = _flatten(_load(_TRANSLATIONS / "en.json"))
    translated = _flatten(_load(_TRANSLATIONS / f"{language}.json"))

    assert sorted(english.keys() - translated.keys()) == [], "missing keys"
    assert sorted(translated.keys() - english.keys()) == [], "unknown keys"
    assert [k for k, v in translated.items() if not str(v).strip()] == []


@pytest.mark.parametrize("language", _LANGUAGES)
def test_translation_keeps_names_and_identifiers(language: str) -> None:
    english = _flatten(_load(_TRANSLATIONS / "en.json"))
    translated = _flatten(_load(_TRANSLATIONS / f"{language}.json"))

    for key, text in english.items():
        for token in _KEEP:
            # Whole words only: "announce" must not match "announcements".
            if re.search(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", text):
                assert token in translated[key], (key, token)
        # Paragraph breaks and digits (the "0" in "0 = no limit") carry meaning.
        assert translated[key].count("\n\n") == text.count("\n\n"), key
        for digit in set(filter(str.isdigit, text)):
            assert digit in translated[key], (key, digit)


@pytest.mark.parametrize("language", _LANGUAGES)
def test_translation_is_actually_translated(language: str) -> None:
    """Catches strings copied from English and never translated."""
    english = _flatten(_load(_TRANSLATIONS / "en.json"))
    translated = _flatten(_load(_TRANSLATIONS / f"{language}.json"))

    untranslated = [
        key
        for key, text in english.items()
        if translated[key] == text and text not in _SAME_AS_ENGLISH_OK
    ]
    assert untranslated == []
