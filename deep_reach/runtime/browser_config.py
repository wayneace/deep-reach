"""Browser profile configuration shared by CLI, doctor, and availability."""

from __future__ import annotations

import re

_CONTEXT_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
_INVALID_VALUES = {"", "auto", "none", "unset"}


def normalize_opencli_profile(value: object) -> str:
    """Return a valid dedicated contextId, or an empty string.

    `auto`, `none`, `unset`, empty, and malformed values all mean "not
    configured". Deep-Reach never falls back to the first connected profile.
    """
    text = str(value or "").strip()
    if text.lower() in _INVALID_VALUES:
        return ""
    return text if _CONTEXT_RE.fullmatch(text) else ""
