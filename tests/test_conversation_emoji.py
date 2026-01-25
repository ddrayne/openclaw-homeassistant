"""Tests for emoji stripping functionality."""
import re

import pytest

# Try to import from conversation module, but if HA is unavailable (Windows
# standalone mode), extract the pure functions directly from the source file.
try:
    from custom_components.clawd.conversation import EMOJI_PATTERN, strip_emojis
except ImportError:
    # Standalone mode: define the same pattern and function locally.
    # This is copied from custom_components/clawd/conversation.py lines 23-38.
    # The pattern and function are pure Python with no HA dependencies.
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )

    def strip_emojis(text: str) -> str:
        """Remove emojis from text for TTS."""
        return EMOJI_PATTERN.sub("", text).strip()


class TestEmojiStripping:
    def test_removes_common_emoji(self) -> None:
        assert strip_emojis("Hello \U0001F600") == "Hello"

    def test_preserves_text_emoticon(self) -> None:
        assert strip_emojis("Hi :)") == "Hi :)"

    def test_plain_text_unchanged(self) -> None:
        assert strip_emojis("Plain text") == "Plain text"
