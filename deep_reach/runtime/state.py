"""~/.deep-reach/state.json: cooldowns, backend health, pacing timestamps.

Only failure codes and timestamps are stored. Never a query, a result body, a
cookie, or a key. Losing this file only loses the cooldown memory; every call
still works.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Callable, TypeVar

STATE_VERSION = 1
T = TypeVar("T")


def root() -> Path:
    override = os.environ.get("DEEP_REACH_STATE_FILE")
    if override:
        return Path(override).expanduser().resolve().parent
    return Path.home() / ".deep-reach"


def state_path() -> Path:
    override = os.environ.get("DEEP_REACH_STATE_FILE")
    if override:
        return Path(override).expanduser()
    return root() / "state.json"


def load() -> dict:
    try:
        text = state_path().read_text(encoding="utf-8")
        data = json.loads(text) if text else {}
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", STATE_VERSION)
    for key in ("cooldowns", "backend_health", "request_starts"):
        if not isinstance(data.get(key), dict):
            data[key] = {}
    return data


def save(data: dict) -> None:
    data["version"] = STATE_VERSION
    path = state_path()
    if path.parent == Path.home() / ".deep-reach":
        from .secure_paths import ensure_private_dir

        ensure_private_dir(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        suffix=".tmp",
        prefix="state-",
        dir=str(path.parent),
        delete=False,
        encoding="utf-8",
    )
    try:
        with handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except Exception:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def mutate(change: Callable[[dict], T]) -> T:
    """Read-modify-write under a cross-process lock."""
    from .limits import execution_lock
    from .result import BUSY, ReachError

    for _ in range(100):
        try:
            with execution_lock("state-write"):
                data = load()
                result = change(data)
                save(data)
                return result
        except ReachError as exc:
            if exc.code != BUSY:
                raise
            time.sleep(0.05)
    raise ReachError(BUSY, "state is being updated by another command")


def clear() -> None:
    from .limits import execution_lock

    with execution_lock("state-write"):
        try:
            state_path().unlink()
        except FileNotFoundError:
            pass


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_seconds(value) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, time.time() - float(value))
    try:
        then = _dt.datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc
        )
    except (TypeError, ValueError):
        return float("inf")
    return max(0.0, (_dt.datetime.now(_dt.timezone.utc) - then).total_seconds())
