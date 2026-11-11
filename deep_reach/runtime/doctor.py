"""Product-level doctor: what works, what doesn't, and what to do next."""

from __future__ import annotations

import os
import stat
from typing import Optional

from ..backends.bsk_guard import BSK_INSTALL_HINT
from ..backends.opencli import RECOMMENDED_VERSION, OpenCLIClient, version_status
from ..channels.base import TIERS
from ..channels.registry import Registry
from . import health, quota
from .availability import (
    OPENCLI_CLIENT_HINT,
    _opencli_hint,
    action_risk,
    channel_availability,
    channel_risk,
    environment_from_profile,
    next_action_for,
)
from .browser_config import normalize_opencli_profile
from .keys import Keys, template_path
from .result import NEED_SETUP, ReachError, redact_text

LEVEL_ORDER = ("default", "optional", "experimental")


def _as_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def build_doctor_report(
    registry: Registry,
    keys: Keys,
    client: Optional[OpenCLIClient] = None,
) -> dict:
    client = client or OpenCLIClient(
        profile=normalize_opencli_profile(keys.get("browser.opencli_profile"))
    )
    try:
        installed = client.version()
        opencli_version = version_status(installed)
    except ReachError as exc:
        missing = exc.code == NEED_SETUP
        opencli_version = {
            "installed": "not installed" if missing else "unavailable",
            "missing": missing,
            "recommended": RECOMMENDED_VERSION,
            "up_to_date": False,
            "action": (
                f"OpenCLI is not installed; {OPENCLI_CLIENT_HINT}"
                if missing
                else exc.message
            ),
        }

    profile = client.profile_status()
    env = environment_from_profile(keys, profile)
    bsk_guard = _as_bool(keys.get("browser.bsk_guard"), True)
    allow_high = _as_bool(keys.get("risk.allow_high"), True)
    rows = []
    for channel in registry.visible.values():
        availability = channel_availability(channel, env)
        status = availability.status
        rows.append(
            {
                "name": channel.name,
                "level": channel.level,
                "status": status,
                "declared_status": channel.status,
                "runnable": availability.runnable,
                "available_actions": list(availability.available_actions),
                "unavailable_actions": availability.unavailable_actions,
                "category": channel.category,
                "description": channel.description,
                "key": channel.key_path,
                "key_status": keys.status(channel.key_path) if channel.key_path else "n/a",
                "risk": channel_risk(channel),
                "tiers": list(channel.tiers),
                "ui_fallback_actions": list(availability.ui_fallback_actions),
                "actions": [a.name for a in channel.actions],
                "requires": {
                    a.name: {
                        "requires": a.requires,
                        "tiers": list(a.tiers),
                        "risk": action_risk(a),
                        "ui_fallback": a.ui_fallback,
                    }
                    for a in channel.actions
                },
                "limits": channel.limits,
                "not_supported": list(channel.not_supported),
                "next_action": next_action_for(channel, availability, env),
            }
        )

    tier_counts = {
        tier: sum(1 for row in rows if tier in row["tiers"])
        for tier in TIERS
        if tier != "p3"
    }
    tier_counts["p3"] = sum(1 for row in rows if row["ui_fallback_actions"])
    summary = {
        "visible": len(rows),
        "ready": sum(1 for r in rows if r["status"] == "ready"),
        "degraded": sum(1 for r in rows if r["status"] == "degraded"),
        "fallback": sum(1 for r in rows if r["status"] == "fallback"),
        "needs_setup": sum(1 for r in rows if r["status"] == "needs_setup"),
        "needs_login": sum(1 for r in rows if r["status"] == "needs_login"),
        "needs_key": sum(1 for r in rows if r["status"] == "needs_key"),
        "experimental": sum(1 for r in rows if r["status"] == "experimental"),
        "runnable": sum(1 for r in rows if r["runnable"]),
        "tiers": tier_counts,
    }
    template = template_path()
    keys_exists = bool(keys.path and keys.path.exists())
    keys_mode = None
    keys_secure = True
    if keys_exists and os.name != "nt" and keys.path is not None:
        try:
            raw_mode = stat.S_IMODE(keys.path.stat().st_mode)
            keys_mode = f"{raw_mode:03o}"
            keys_secure = not (raw_mode & 0o077)
        except OSError:
            keys_secure = False
    profile = dict(profile)
    profile.setdefault("setting", normalize_opencli_profile(
        keys.get("browser.opencli_profile")
    ))
    profile.setdefault("configured", bool(profile["setting"]))
    profile.setdefault("connected", False)
    profile.setdefault("context_id", profile["setting"] or None)
    profile.setdefault("profile_ids", [])
    profile.setdefault("profiles", [])
    profile["window"] = "background"
    profile["next"] = (
        _opencli_hint(env)
        if not profile["connected"] or not profile["configured"]
        else ""
    )
    return {
        "keys_file": str(keys.path),
        "keys_file_exists": keys_exists,
        "keys_file_mode": keys_mode,
        "keys_file_secure": keys_secure,
        "keys_file_note": keys.permission_note,
        "keys_template": str(template),
        "keys_hint": (
            ""
            if keys_exists
            else f"Create it from {template} (all keys optional)."
        ),
        "opencli": opencli_version,
        "profile": profile,
        "bsk": {
            "installed": env.bsk_installed,
            "profile": "current",
            "guard": bsk_guard,
            "allow_high_risk": allow_high,
            "install": BSK_INSTALL_HINT,
            "warning": (
                "P3 bsk uses the real browser profile; writes are allowed; "
                "confirm user intent before destructive actions."
            ),
        },
        "state": health.report(),
        "quota": quota.report(),
        "channels": rows,
        "summary": summary,
    }


def format_doctor_text(report: dict) -> str:
    lines = []
    opencli = report.get("opencli", {})
    profile = report.get("profile", {})
    lines.append("deep-reach doctor")
    lines.append(f"keys:     {report.get('keys_file')} ({'found' if report.get('keys_file_exists') else 'missing'})")
    if not report.get("keys_file_exists") and report.get("keys_hint"):
        lines.append(f"          → {report['keys_hint']}")
    if report.get("keys_file_exists") and not report.get("keys_file_secure", True):
        lines.append(
            f"          warning: keys file mode {report.get('keys_file_mode')}; "
            "expected 600"
        )
    if report.get("keys_file_note"):
        lines.append(f"          note: {report['keys_file_note']}")
    if opencli.get("missing"):
        lines.append(
            f"opencli:  not installed "
            f"(recommended {opencli.get('recommended', '?')})"
        )
    else:
        lines.append(
            f"opencli:  {opencli.get('installed', 'not installed')} "
            f"(recommended {opencli.get('recommended', '?')})"
        )
    if opencli.get("up_to_date") is not True and opencli.get("action"):
        lines.append(f"          → {opencli['action']}")
    if profile.get("connected"):
        lines.append(
            f"browser:  dedicated {profile.get('context_id')} (connected, "
            f"extension {profile.get('extension_version')})"
        )
        if profile.get("extension_outdated"):
            lines.append(
                f"          → Browser Bridge extension "
                f"{profile.get('extension_version')} → "
                f"{profile.get('latest_extension_version')}: "
                f"https://github.com/jackwener/opencli/releases"
            )
    else:
        detail = (
            "OpenCLI is not installed"
            if opencli.get("missing")
            else profile.get("error", "install the Browser Bridge extension")
        )
        state = "not configured" if not profile.get("configured") else "not connected"
        lines.append(f"browser:  {state} ({detail})")
        if profile.get("next"):
            lines.append(f"          → {profile['next']}")
    lines.append(
        "browser:  window background "
        "(OpenCLI Browser Bridge has no true headless mode)"
    )
    bsk = report.get("bsk") or {}
    bsk_state = "installed" if bsk.get("installed") else "not installed"
    lines.append(
        f"bsk:      profile {bsk.get('profile', 'current')}; "
        f"guard {'on' if bsk.get('guard', True) else 'off'}; {bsk_state}"
    )
    if not bsk.get("installed"):
        lines.append(f"          → install: {bsk.get('install')}")
    if bsk.get("warning"):
        lines.append(f"          warning: {bsk['warning']}")
    lines.append("")

    by_level: dict[str, list] = {level: [] for level in LEVEL_ORDER}
    for row in report.get("channels", []):
        by_level.setdefault(row["level"], []).append(row)

    for level in LEVEL_ORDER:
        rows = by_level.get(level) or []
        if not rows:
            continue
        lines.append(level.upper())
        for row in rows:
            ui_fallback = set(row.get("ui_fallback_actions") or ())
            actions = (
                ", ".join(
                    f"{name}(bsk)" if name in ui_fallback else name
                    for name in row["actions"]
                )
                or "-"
            )
            tiers = ",".join(row.get("tiers") or [])
            lines.append(
                f"  {row['name']:<14} {row['status']:<13} {tiers:<7} "
                f"risk={row.get('risk', 'low'):<6} {actions}"
            )
            if row["status"] not in {"ready", "experimental"} or row.get("next_action") not in {"-", ""}:
                lines.append(f"      → {row['next_action']}")
        lines.append("")

    summary = report.get("summary", {})
    tiers = summary.get("tiers") or {}
    lines.append(
        f"{summary.get('visible', 0)} visible; "
        f"{summary.get('ready', 0)} ready; "
        f"{summary.get('degraded', 0)} degraded; "
        f"{summary.get('fallback', 0)} fallback; "
        f"{summary.get('needs_setup', 0)} need setup; "
        f"{summary.get('needs_login', 0)} need login; "
        f"{summary.get('needs_key', 0)} need key; "
        f"{summary.get('experimental', 0)} experimental; "
        f"{summary.get('runnable', 0)} runnable now"
    )
    lines.append(
        f"tiers:    p0 {tiers.get('p0', 0)} / p1 {tiers.get('p1', 0)} / "
        f"p2 {tiers.get('p2', 0)} channels / "
        f"p3 {tiers.get('p3', 0)} fallback channels"
    )
    saved = report.get("state") or {}
    cooldowns = saved.get("cooldowns") or []
    paused = saved.get("paused_backends") or []
    lines.append(
        f"state:    {saved.get('path', '-')} "
        f"({len(cooldowns)} cooldown, {len(paused)} paused)"
    )
    for item in cooldowns:
        lines.append(
            f"          cooldown {item['channel']}: "
            f"{item['retry_after_seconds']}s left"
        )
    for item in paused:
        lines.append(
            f"          paused {item['channel']}/{item['action']}/{item['backend']}: "
            f"{item['retry_after_seconds']}s left"
        )
    quota_rows = (report.get("quota") or {}).get("backends") or []
    used = [row for row in quota_rows if row["used"]]
    if used:
        lines.append(
            "quota:    "
            + ", ".join(
                f"{row['backend']} {row['used']}/{row['limit']}" for row in used
            )
        )
    else:
        lines.append("quota:    0 used today")
    return redact_text("\n".join(lines))
