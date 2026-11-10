"""Run a channel action: validate, apply limits, try backends, build the envelope.

Reliability follows Agent-Reach's model:

* one Clock per action; queue waiting pauses it;
* a confirmed rate limit cools the whole channel for an hour;
* a failed backend is paused for 60-120 seconds and skipped by the next call;
* browser backends share 2 slots per site and 4 overall through OS file locks;
* browser searches keep a 10 second gap per channel;
* every backend call is bounded by the action deadline.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from typing import Callable, Optional

from ..channels.base import Action, Channel
from . import health
from .clock import Clock
from .keys import Keys, default_keys_path, template_path
from .limits import acquire_request, is_browser_backend, pace, query_slot
from .result import (
    BAD_INPUT,
    BSK_UI_POLICY,
    BUSY,
    ERROR_PRIORITY,
    FINAL_CODES,
    KEY_MISSING,
    NEED_LOGIN,
    NEED_SETUP,
    NEED_UI,
    POLICY_BLOCKED,
    RATE_LIMITED,
    SOURCE_DISABLED,
    TIMEOUT,
    UPSTREAM_BROKEN,
    ReachError,
    envelope,
)

BackendFunc = Callable[..., list[dict]]


class BackendRegistry:
    """A tiny registry so backends can be plugged in without touching dispatch."""

    def __init__(self) -> None:
        self._backends: dict[str, BackendFunc] = {}

    def register(self, label: str, func: BackendFunc) -> BackendFunc:
        self._backends[label] = func
        return func

    def get(self, label: str) -> Optional[BackendFunc]:
        return self._backends.get(label)

    def clear(self) -> None:
        self._backends.clear()

    def labels(self) -> list[str]:
        return sorted(self._backends)


BACKENDS = BackendRegistry()


class _PreCallError(ReachError):
    """A limit stopped the call before the backend ran; do not blame the backend."""


def validate(action: Action, params: dict) -> dict:
    clean: dict = {}
    for p in action.params:
        value = params.get(p.name)
        if isinstance(value, str):
            value = value.strip()
        if value is None or value == "":
            if p.required:
                raise ReachError(BAD_INPUT, f"missing required argument: {p.name}")
            value = p.default
        else:
            if p.type is int and isinstance(value, bool):
                raise ReachError(BAD_INPUT, f"{p.name} must be int")
            try:
                value = p.type(value)
            except (TypeError, ValueError):
                raise ReachError(BAD_INPUT, f"{p.name} must be {p.type.__name__}") from None
        if p.type is int and p.name in {"limit", "page"}:
            if not isinstance(value, int) or value < 1:
                raise ReachError(BAD_INPUT, f"{p.name} must be a positive integer")
        clean[p.name] = value

    unknown = set(params) - {p.name for p in action.params}
    if unknown:
        raise ReachError(BAD_INPUT, f"unknown argument(s): {', '.join(sorted(unknown))}")
    return clean


def _keys_hint(keys: Optional[Keys]) -> str:
    path = keys.path if keys is not None and keys.path else default_keys_path()
    return f"Add the key to {path} (template: {template_path()})."


def _pick_error(
    errors: list[ReachError], keys: Optional[Keys] = None
) -> ReachError:
    """Report the most actionable failure across tiers."""
    if not errors:
        return ReachError(SOURCE_DISABLED, "no backend is available")
    rank = {code: index for index, code in enumerate(ERROR_PRIORITY)}
    chosen = min(errors, key=lambda err: rank.get(err.code, len(rank)))
    if chosen.code == KEY_MISSING and not chosen.hint and keys is not None:
        return ReachError(chosen.code, chosen.message, hint=_keys_hint(keys))
    return chosen


def _terminal_error(errors: list[ReachError]) -> Optional[ReachError]:
    """The highest-priority terminal error, if any backend already decided the outcome."""
    terminal = [err for err in errors if err.code in FINAL_CODES]
    if not terminal:
        return None
    rank = {code: index for index, code in enumerate(ERROR_PRIORITY)}
    return min(terminal, key=lambda err: rank.get(err.code, len(rank)))


def _call_with_deadline(func: BackendFunc, kwargs: dict, clock: Clock) -> list[dict]:
    """Bound an in-process HTTP call that cannot be interrupted."""
    box: dict = {}
    budget = max(0.1, clock.remaining())

    def target() -> None:
        try:
            box["items"] = func(**kwargs, timeout=budget)
        except BaseException as exc:  # noqa: BLE001 - forwarded to the caller
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    while True:
        left = clock.remaining() + 1.0
        if left <= 0:
            break
        worker.join(max(left, 0.1))
        if not worker.is_alive():
            break
    if worker.is_alive():
        raise ReachError(TIMEOUT, f"backend did not answer within {budget:.0f}s")
    if "error" in box:
        raise box["error"]
    return list(box.get("items") or [])


def _attempt(spec, result: str, **extra) -> dict:
    row = {"backend": spec.label, "tier": spec.tier, "result": result}
    row.update(extra)
    return row


def _need_ui(
    channel: Channel,
    action: Action,
    attempts: list[dict],
    elapsed_ms: int,
    keys: Optional[Keys],
) -> dict:
    """Return the bsk UI handoff instead of pretending P3 is an automatic backend."""
    profile = "main"
    if keys is not None:
        profile = str(keys.get("browser.bsk_profile") or "main")
    risk = action.risk or ("high" if action.requires == "login" else "medium")
    hint = (
        "使用 `deep-reach bsk ...`（守卫版）回退："
        "`deep-reach bsk session start --json` → `navigate` → `observe` → "
        "`click` → `session stop`。bsk 全能力可用（含写操作）；"
        "不要直接 fetch 站点内部接口；写操作有副作用，请确认用户意图。"
    )
    if not (os.environ.get("DEEP_REACH_BSK_BIN") or shutil.which("bsk")):
        hint += (
            " bsk 未安装；安装："
            "https://raw.githubusercontent.com/Tencent/BrowserSkill/main/AGENT_INSTALL.md"
        )
    return envelope(
        channel=channel.name,
        action=action.name,
        tier="p3",
        elapsed_ms=elapsed_ms,
        attempts=attempts,
        error=ReachError(
            NEED_UI,
            "没有自动后端能完成这个动作，请用 bsk UI 回退。",
            hint=hint,
        ),
        extra_meta={
            "fallback": "bsk-ui",
            "profile": profile,
            "risk": risk,
            "policy": BSK_UI_POLICY,
        },
    )


def run_action(
    channel: Channel,
    action_name: str,
    params: Optional[dict] = None,
    *,
    keys: Optional[Keys] = None,
    timeout: Optional[float] = None,
) -> dict:
    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    action = channel.action(action_name)
    if action is None:
        valid = ", ".join(a.name for a in channel.actions) or "none"
        return envelope(
            channel=channel.name,
            action=action_name,
            elapsed_ms=elapsed(),
            error=ReachError(
                BAD_INPUT,
                f"unknown action '{action_name}' for {channel.name}; valid: {valid}",
            ),
        )

    try:
        clean = validate(action, params or {})
    except ReachError as exc:
        return envelope(
            channel=channel.name, action=action_name, elapsed_ms=elapsed(), error=exc
        )

    keys = keys or Keys({})
    allow_high = keys.get("risk.allow_high", True)
    if isinstance(allow_high, str):
        allow_high = allow_high.strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
            "",
        }
    if action.risk == "high" and not allow_high:
        return envelope(
            channel=channel.name,
            action=action_name,
            elapsed_ms=elapsed(),
            error=ReachError(
                POLICY_BLOCKED,
                "high-risk action disabled by risk.allow_high=false",
                hint="Set risk.allow_high: true in keys.yaml to enable it.",
            ),
        )

    if action.risk == "high":
        print(
            f"warning: {channel.name}/{action_name} is high risk; "
            "using the real browser profile may trigger platform risk controls.",
            file=sys.stderr,
        )

    if action.requires == "login" and not any(
        spec.supports_login for spec in action.backends
    ):
        if action.ui_fallback:
            return _need_ui(channel, action, [], elapsed(), keys)
        return envelope(
            channel=channel.name,
            action=action_name,
            elapsed_ms=elapsed(),
            error=ReachError(
                NEED_LOGIN,
                "login is required but no backend supports a login session",
            ),
        )

    clock = Clock(timeout or action.timeout)
    attempts: list[dict] = []
    errors: list[ReachError] = []
    fingerprint = health.fingerprint(channel)
    paced = False

    try:
        limited = health.cooldown(channel.name)
        if limited:
            raise ReachError(
                RATE_LIMITED,
                limited["message"],
                hint=f"Wait {limited['retry_after_seconds']} seconds before retrying this channel.",
            )

        for spec in action.backends:
            if action.requires == "login" and not spec.supports_login:
                attempts.append(
                    _attempt(
                        spec,
                        NEED_LOGIN,
                        skipped=True,
                        message="backend does not support login",
                    )
                )
                errors.append(
                    ReachError(
                        NEED_LOGIN,
                        f"{spec.label} does not support login",
                    )
                )
                continue

            if spec.requires_key:
                key_paths = spec.required_keys(channel)
                if any(not path for path in key_paths):
                    attempts.append(_attempt(spec, NEED_SETUP))
                    errors.append(
                        ReachError(
                            NEED_SETUP,
                            f"{spec.label} requires a key but no key path is configured",
                        )
                    )
                    continue
                missing = [
                    path for path in key_paths if path and not keys.has(path)
                ]
                if missing:
                    target = keys.path or default_keys_path()
                    message = (
                        f"{', '.join(missing)} missing; add the key to {target}; "
                        f"skipping {spec.label}"
                    )
                    attempts.append(
                        _attempt(spec, KEY_MISSING, message=message)
                    )
                    errors.append(
                        ReachError(KEY_MISSING, message, hint=_keys_hint(keys))
                    )
                    continue

            paused = health.backend_pause(
                channel.name, action_name, spec.label, fingerprint
            )
            if paused:
                attempts.append(
                    _attempt(
                        spec,
                        paused["code"],
                        skipped=True,
                        retry_after_seconds=paused["retry_after_seconds"],
                        message=paused["message"],
                    )
                )
                errors.append(ReachError(paused["code"], paused["message"]))
                continue

            if clock.remaining() <= 0:
                attempts.append(_attempt(spec, TIMEOUT))
                errors.append(ReachError(TIMEOUT, "no time left for this backend"))
                break

            func = BACKENDS.get(spec.label)
            if func is None:
                attempts.append(_attempt(spec, NEED_SETUP))
                errors.append(
                    ReachError(NEED_SETUP, f"backend is not registered: {spec.label}")
                )
                continue

            kwargs = {
                "action": action_name,
                "params": clean,
                "spec": spec,
                "channel": channel,
            }

            if is_browser_backend(spec.label):
                try:
                    with query_slot(channel.name, clock):
                        limited = health.cooldown(channel.name)
                        if limited:
                            raise _PreCallError(RATE_LIMITED, limited["message"])
                        if not paced:
                            try:
                                pace(channel.name, action_name, clock)
                            except ReachError as exc:
                                raise _PreCallError(exc.code, exc.message) from exc
                            paced = True
                        acquire_request(channel.name, clock)
                        items = func(
                            **kwargs, timeout=max(0.1, clock.remaining())
                        )
                except _PreCallError as exc:
                    attempts.append(_attempt(spec, exc.code, message=exc.message))
                    errors.append(ReachError(exc.code, exc.message))
                    if exc.code in FINAL_CODES:
                        break
                    continue
                except ReachError as exc:
                    if exc.code == BUSY:
                        attempts.append(
                            _attempt(spec, BUSY, skipped=True, message=exc.message)
                        )
                        errors.append(exc)
                        if exc.code in FINAL_CODES:
                            break
                        continue
                    attempts.append(
                        _attempt(spec, exc.code, message=exc.message[:200])
                    )
                    errors.append(exc)
                    health.remember(
                        channel.name, action_name, spec.label, exc, fingerprint
                    )
                    if exc.code in FINAL_CODES:
                        break
                    continue
                except Exception as exc:  # noqa: BLE001 - classify unknown failures
                    err = ReachError(UPSTREAM_BROKEN, str(exc))
                    attempts.append(
                        _attempt(spec, UPSTREAM_BROKEN, message=err.message[:200])
                    )
                    errors.append(err)
                    health.remember(
                        channel.name, action_name, spec.label, err, fingerprint
                    )
                    continue
            else:
                try:
                    acquire_request(channel.name, clock)
                    items = _call_with_deadline(func, kwargs, clock)
                except ReachError as exc:
                    attempts.append(
                        _attempt(spec, exc.code, message=exc.message[:200])
                    )
                    errors.append(exc)
                    health.remember(
                        channel.name, action_name, spec.label, exc, fingerprint
                    )
                    if exc.code in FINAL_CODES:
                        break
                    continue
                except Exception as exc:  # noqa: BLE001 - classify unknown failures
                    err = ReachError(UPSTREAM_BROKEN, str(exc))
                    attempts.append(
                        _attempt(spec, UPSTREAM_BROKEN, message=err.message[:200])
                    )
                    errors.append(err)
                    health.remember(
                        channel.name, action_name, spec.label, err, fingerprint
                    )
                    continue

            attempts.append(_attempt(spec, "ok"))
            health.clear_backend(channel.name, action_name, spec.label)
            return envelope(
                channel=channel.name,
                action=action_name,
                backend=spec.label,
                tier=spec.tier,
                items=items,
                elapsed_ms=elapsed(),
                attempts=attempts,
            )
    except ReachError as exc:
        errors.append(exc)

    terminal = _terminal_error(errors)
    if terminal is not None:
        return envelope(
            channel=channel.name,
            action=action_name,
            elapsed_ms=elapsed(),
            attempts=attempts,
            error=terminal,
        )

    if action.ui_fallback:
        return _need_ui(channel, action, attempts, elapsed(), keys)

    return envelope(
        channel=channel.name,
        action=action_name,
        elapsed_ms=elapsed(),
        attempts=attempts,
        error=_pick_error(errors, keys),
    )
