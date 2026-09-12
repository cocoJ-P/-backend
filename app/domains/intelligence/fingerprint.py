"""Stable hashes for Intelligence analysis reuse."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from app.core.time import to_iso8601


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def compute_input_hash(
    *,
    title: str | None,
    publisher: str | None,
    source_url: str | None,
    published_at: datetime | None,
    normalized_text: str,
) -> str:
    payload = {
        "title": title or "",
        "publisher": publisher or "",
        "source_url": source_url or "",
        "published_at": to_iso8601(published_at) if published_at is not None else "",
        "normalized_text": normalized_text,
    }
    return sha256_text(_canonical_json(payload))


def compute_analysis_fingerprint(
    *,
    input_hash: str,
    rule_version: str,
    prompt_version: str,
    provider: str,
    model: str,
) -> str:
    payload = {
        "input_hash": input_hash,
        "rule_version": rule_version,
        "prompt_version": prompt_version,
        "provider": provider.strip().lower(),
        "model": model,
    }
    return sha256_text(_canonical_json(payload))
