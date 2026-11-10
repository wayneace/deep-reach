"""Environment passed to external CLIs.

Deep-Reach keys and credential-looking variables are never inherited by
OpenCLI, bsk, Chrome, npm, or helper processes. Callers add only the variables
the child actually needs.
"""

from __future__ import annotations

import os
import re
from typing import Optional

_CREDENTIAL_RE = re.compile(
    r"(token|secret|password|passwd|cookie|api[_-]?key|apikey|"
    r"access[_-]?key|private[_-]?key|credential)",
    re.IGNORECASE,
)


def child_env(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("DEEP_REACH_")
        and not _CREDENTIAL_RE.search(name)
    }
    if extra:
        env.update({str(name): str(value) for name, value in extra.items()})
    return env
