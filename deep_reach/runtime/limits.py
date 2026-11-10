"""Cross-process limits for the shared browser and search pacing.

The CLI is one process per call, so in-process semaphores would not coordinate
two agent commands. Slots are OS file locks instead: N lock files per site and
N overall, with no daemon and no stale-lock cleanup (closing the handle or the
process releases the lock).

Same shape as Agent-Reach: 2 queries per site, 4 browser queries overall, a
10 second gap between searches on one site, and queue waiting that does not
count against the action timeout.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .result import BUSY, TIMEOUT, ReachError

SITE_SLOTS = 2
BROWSER_SLOTS = 4
QUEUE_WAIT = 120.0
POLL = 0.2
BROWSER_SEARCH_INTERVAL = 10.0
PACED_ACTIONS = {"search", "jobs"}
#: Hard local cap for every backend call on one channel, sliding window.
#: Shared by every Deep-Reach process using the same state file.
SITE_REQUEST_LIMIT = 40
SITE_REQUEST_WINDOW = 60.0


def root() -> Path:
    override = os.environ.get("DEEP_REACH_STATE_FILE")
    if override:
        return Path(override).expanduser().resolve().parent
    return Path.home() / ".deep-reach"


def _lock_path(name: str) -> Path:
    base = root()
    if base == Path.home() / ".deep-reach":
        from .secure_paths import ensure_private_dir

        ensure_private_dir(base)
    folder = base / "locks"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]
    return folder / f"{digest}.lock"


def _acquire(handle) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _release(handle) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def execution_lock(name: str) -> Iterator[None]:
    """Non-blocking exclusive lock; raises BUSY when another process holds it."""
    path = _lock_path(name)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if not _acquire(handle):
            raise ReachError(BUSY, f"another Deep-Reach command holds {name}")
        try:
            yield
        finally:
            _release(handle)


def _try_any(names: list[str]) -> Optional[ExitStack]:
    for name in names:
        stack = ExitStack()
        try:
            stack.enter_context(execution_lock(name))
            return stack
        except ReachError as exc:
            stack.close()
            if exc.code != BUSY:
                raise
    return None


def _wait_any(names: list[str], wait: float, message: str) -> ExitStack:
    deadline = time.monotonic() + max(0.0, wait)
    while True:
        held = _try_any(names)
        if held is not None:
            return held
        if time.monotonic() >= deadline:
            raise ReachError(BUSY, message)
        time.sleep(POLL)


@contextmanager
def wait_lock(name: str, wait: Optional[float] = None) -> Iterator[None]:
    with _wait_any([name], QUEUE_WAIT if wait is None else wait, f"waited too long for {name}"):
        yield


@contextmanager
def query_slot(site: str, clock=None) -> Iterator[None]:
    """At most SITE_SLOTS per site and BROWSER_SLOTS overall, waiting in line."""
    with ExitStack() as stack:
        if clock is not None:
            clock.pause()
        try:
            stack.enter_context(
                _wait_any(
                    [f"site:{site}:{index}" for index in range(SITE_SLOTS)],
                    QUEUE_WAIT,
                    f"{site} already has {SITE_SLOTS} queries running",
                )
            )
            stack.enter_context(
                _wait_any(
                    [f"browser:slot:{index}" for index in range(BROWSER_SLOTS)],
                    QUEUE_WAIT,
                    "the shared browser is full",
                )
            )
        finally:
            if clock is not None:
                clock.resume()
        yield


def pace(channel: str, action: str, clock) -> None:
    """Keep 10 seconds between browser searches on the same site."""
    if action not in PACED_ACTIONS:
        return
    from . import state

    with wait_lock(f"pace:{channel}", wait=max(0.0, clock.remaining())):
        last = state.load().get("request_starts", {}).get(channel)
        age = (
            time.time() - last
            if isinstance(last, (int, float))
            else state.age_seconds(last)
        )
        wait = BROWSER_SEARCH_INTERVAL - age
        if wait > 0:
            if wait >= clock.remaining():
                raise ReachError(
                    TIMEOUT,
                    "search pacing exceeds the remaining timeout; retry later",
                )
            time.sleep(wait)
        state.mutate(
            lambda data: data.setdefault("request_starts", {}).__setitem__(
                channel, time.time()
            )
        )


def acquire_request(channel: str, clock) -> None:
    """At most SITE_REQUEST_LIMIT backend calls per channel in a sliding minute.

    This is a local safety cap, not a platform signal: it never triggers a
    channel cooldown or a backend pause. When the window is full and the wait
    does not fit the action budget, the action stops with BUSY.
    """
    from . import state

    with wait_lock(f"rate:{channel}", wait=max(0.0, clock.remaining())):
        while True:
            now = time.time()

            def change(data: dict) -> float:
                log = [
                    float(stamp)
                    for stamp in data.get("request_log", {}).get(channel, [])
                    if now - float(stamp) < SITE_REQUEST_WINDOW
                ]
                data.setdefault("request_log", {})[channel] = log
                if len(log) >= SITE_REQUEST_LIMIT:
                    return log[0] + SITE_REQUEST_WINDOW - now
                log.append(now)
                return 0.0

            wait_for = state.mutate(change)
            if wait_for <= 0:
                return
            if wait_for >= clock.remaining():
                raise ReachError(
                    BUSY,
                    f"{channel}: local request budget is full "
                    f"({SITE_REQUEST_LIMIT}/{int(SITE_REQUEST_WINDOW)}s)",
                    hint=(
                        f"Retry in about {max(1, int(wait_for))} seconds; "
                        "this is a local cap, not a platform rate limit."
                    ),
                )
            time.sleep(min(wait_for, max(0.0, clock.remaining())))


def is_browser_backend(label: str) -> bool:
    return label.startswith("opencli-")
