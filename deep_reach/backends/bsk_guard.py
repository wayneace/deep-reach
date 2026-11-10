"""Thin policy guard for the bsk UI fallback.

bsk may use all of its own capabilities, including writes. The only hard
policy is: do not call a site's internal APIs directly. This guard blocks
`debug replay` and `evaluate` scripts that contain network primitives, and
passes every other command through unchanged.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Optional

from ..runtime.result import (
    BAD_INPUT,
    NEED_SETUP,
    POLICY_BLOCKED,
    ReachError,
    dump,
    envelope,
)

#: Network primitives that would turn evaluate into a direct internal-API call.
NETWORK_PATTERNS = (
    re.compile(r"\bfetch\s*\("),
    re.compile(r"\bXMLHttpRequest\b"),
    re.compile(r"\bsendBeacon\b"),
    re.compile(r"\bWebSocket\b"),
    re.compile(r"\bEventSource\b"),
    re.compile(r"\baxios\s*\("),
    re.compile(r"\$\.ajax\b"),
)

#: Tokens that usually mean a write. They only trigger a warning; writes are allowed.
WRITE_TOKENS = frozenset(
    {
        "post",
        "comment",
        "reply",
        "delete",
        "like",
        "follow",
        "unfollow",
        "upload",
        "submit",
        "purchase",
        "buy",
    }
)

DEFAULT_WARNING = (
    "deep-reach bsk: using the main browser profile; "
    "the platform may treat automation as abuse."
)

BSK_INSTALL_HINT = (
    "https://raw.githubusercontent.com/Tencent/BrowserSkill/main/AGENT_INSTALL.md"
)


def bsk_available() -> bool:
    return bool(os.environ.get("DEEP_REACH_BSK_BIN") or shutil.which("bsk"))


def policy_violation(args: list[str]) -> Optional[str]:
    """Return a human-readable policy violation, or None when the call is allowed."""
    lowered = [arg.lower() for arg in args]

    if "debug" in lowered:
        index = lowered.index("debug")
        if index + 1 < len(lowered) and lowered[index + 1] == "replay":
            return "debug replay re-issues site API requests; use passive debug reads instead"

    if "evaluate" in lowered:
        index = lowered.index("evaluate")
        script = " ".join(args[index + 1 :])
        for pattern in NETWORK_PATTERNS:
            if pattern.search(script):
                return (
                    "evaluate must not call site internal APIs directly; "
                    "use DOM reads, observe, click, extract, or passive network reads"
                )
    return None


def warnings_for(args: list[str]) -> list[str]:
    """Warnings printed to stderr before a bsk call; they never block it."""
    warnings = [DEFAULT_WARNING]
    lowered = [arg.lower() for arg in args]

    if "debug" in lowered and "rule_add" in lowered:
        warnings.append(
            "deep-reach bsk: debug rule_add may change page requests; "
            "use it for debugging only."
        )
    if any(token in WRITE_TOKENS for token in lowered):
        warnings.append(
            "deep-reach bsk: write operation may change site state; "
            "confirm the user's intent."
        )
    return warnings


def _print_error(code: str, message: str, hint: Optional[str] = None) -> None:
    tier = "p3" if code == POLICY_BLOCKED else None
    payload = envelope(
        channel=None,
        action="bsk",
        tier=tier,
        error=ReachError(code, message, hint=hint),
    )
    print(dump(payload))


def run_bsk(
    args: list[str], *, bin_path: Optional[str] = None, guard: bool = True
) -> int:
    """Run `bsk` with a thin policy check; return the child exit code."""
    if not args:
        _print_error(
            BAD_INPUT,
            "usage: deep-reach bsk <bsk-args...>",
            "Example: deep-reach bsk session start --json",
        )
        return 2

    violation = policy_violation(args) if guard else None
    if violation:
        _print_error(
            POLICY_BLOCKED,
            violation,
            "bsk may use all of its capabilities; only direct internal-API calls "
            "and debug replay are blocked.",
        )
        return 1

    for warning in warnings_for(args):
        print(warning, file=sys.stderr)

    binary = (
        bin_path
        or os.environ.get("DEEP_REACH_BSK_BIN")
        or shutil.which("bsk")
        or "bsk"
    )
    try:
        proc = subprocess.run([binary, *args])
    except FileNotFoundError:
        _print_error(
            NEED_SETUP,
            "bsk is not installed",
            f"Install BrowserSkill: {BSK_INSTALL_HINT}",
        )
        return 1
    return int(proc.returncode)
