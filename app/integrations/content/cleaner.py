"""Deterministic text cleaning. No semantic rewrite."""

from __future__ import annotations

import html
import re
import unicodedata


def clean_text(value: str) -> str:
    text = html.unescape(value)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
