"""Best-effort HTML metadata extraction. No official/marketing judgment."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import dateparser
from bs4 import BeautifulSoup, Tag

from app.core.time import ensure_utc


def _meta_content(soup: BeautifulSoup, *, property: str | None = None, name: str | None = None) -> str | None:
    attrs: dict[str, str] = {}
    if property:
        attrs["property"] = property
    if name:
        attrs["name"] = name
    tag = soup.find("meta", attrs=attrs)
    if not isinstance(tag, Tag):
        return None
    content = tag.get("content")
    if not content:
        return None
    text = str(content).strip()
    return text or None


def _itemprop(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find(attrs={"itemprop": name})
    if not isinstance(tag, Tag):
        return None
    content = tag.get("content") or tag.get_text(" ", strip=True)
    text = str(content).strip() if content else ""
    return text or None


def _json_ld_items(soup: BeautifulSoup) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates: list[Any]
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict) and isinstance(data.get("@graph"), list):
            candidates = data["@graph"]
        else:
            candidates = [data]
        for item in candidates:
            if isinstance(item, dict):
                items.append(item)
    return items


def _json_ld_value(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def parse_published_at(value: str | None) -> datetime | None:
    """Parse a date string to UTC.

    Naive timestamps are treated as UTC. Relative phrases without digits
    are rejected rather than guessed.
    """
    if not value or not any(char.isdigit() for char in value):
        return None
    parsed = dateparser.parse(
        value,
        settings={
            "RETURN_AS_TIMEZONE_AWARE": True,
            "TIMEZONE": "UTC",
            "TO_TIMEZONE": "UTC",
        },
    )
    if parsed is None:
        return None
    return ensure_utc(parsed)


def extract_metadata(html: str) -> dict[str, str | datetime | None]:
    soup = BeautifulSoup(html, "html.parser")
    json_ld = _json_ld_items(soup)

    title = (
        _meta_content(soup, property="og:title")
        or _meta_content(soup, name="twitter:title")
        or next((item for item in (_json_ld_value(row, "headline") for row in json_ld) if item), None)
        or (soup.title.get_text(strip=True) if soup.title else None)
    )
    publisher = (
        _meta_content(soup, property="article:publisher")
        or _meta_content(soup, property="og:site_name")
        or _meta_content(soup, name="publisher")
        or _meta_content(soup, name="author")
        or next((item for item in (_json_ld_value(row, "publisher") for row in json_ld) if item), None)
    )
    published_raw = (
        _meta_content(soup, property="article:published_time")
        or _itemprop(soup, "datePublished")
        or _meta_content(soup, name="date")
        or next((item for item in (_json_ld_value(row, "datePublished") for row in json_ld) if item), None)
    )
    return {
        "title": title or None,
        "publisher": publisher or None,
        "published_at": parse_published_at(published_raw),
    }
