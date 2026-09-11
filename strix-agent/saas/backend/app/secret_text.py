"""Refuse credential-shaped text so notes never become a secrets dump.

Live tokens pasted into New Pentest notes, Chat, or custom_instructions
used to land in the database and in ``run.json``'s instruction field.
This module is the gate: detect obvious secret shapes, reject them at
the API, and redact anything that still reaches the engine.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bauthorization\s*:\s*\S+(?:\s+\S+)*"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)\b(cookie|set-cookie)\s*:\s*\S+"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|password|passwd|private[_-]?key)\s*[:=]\s*\S+"
    ),
)


def contains_secret_shaped_text(value: str | None) -> bool:
    if not value:
        return False
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def redact_secret_shaped_text(value: str | None) -> str:
    if not value:
        return ""
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def reject_secret_shaped_text(value: str | None) -> str | None:
    """Return stripped text, or raise if it looks like live credentials."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if contains_secret_shaped_text(stripped):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="credentials_not_allowed",
        )
    return stripped
