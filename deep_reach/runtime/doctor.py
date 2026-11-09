"""Product-level doctor: what works, what doesn't, and what to do next."""

from __future__ import annotations

from typing import Optional

from ..backends.opencli import RECOMMENDED_VERSION, OpenCLIClient, version_status
from ..channels.base import TIERS
from ..channels.registry import Registry
from . import health, quota
from .availability import ChannelAvailability, channel_availability, environment_from_profile
from .keys import Keys
from .result import ReachError

LEVEL_ORDER = ("default", "optional", "experimental")


def _next_action(
    channel, status: str, availability: ChannelAvailability
) -> str:
    if status == "needs_setup":
        base = "安装/启用 OpenCLI Browser Bridge，然后运行 `deep-reach doctor`"
        return f"{base}；或 {channel.next_action}" if channel.next_action else base
    if status == "degraded":
        names = ", ".join(availability.unavailable_actions)
        return f"部分动作当前不可用（{names}）；运行 `deep-reach doctor` 查看原因"
    if channel.next_action:
        return channel.next_action
    if status == "needs_login":
        return f"在 Deep-Reach 专用 Chrome profile 登录 {channel.name} 后重试"
    if status == "needs_key":
        return f"填写 {channel.key_path}，或使用 fallback"
    if status == "experimental":
        return "该渠道可能不稳定；失败时稍后重试"
    return "-"


def build_doctor_report(
    registry: Registry,
    keys: Keys,
    client: Optional[OpenCLIClient] = None,
) -> dict:
    client = client or OpenCLIClient(profile=keys.get("browser.opencli_profile") or "auto")
    try:
        installed = client.version()
        opencli_version = version_status(installed)
    except ReachError as exc:
        opencli_version = {
            "installed": f"error: {exc.message}",
            "recommended": RECOMMENDED_VERSION,
            "up_to_date": False,
            "action": exc.message,
        }

    profile = client.profile_status()
    env = environment_from_profile(keys, profile)
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
                "tiers": list(channel.tiers),
                "actions": [a.name for a in channel.actions],
                "requires": {
                    a.name: {
                        "requires": a.requires,
                        "tiers": list(a.tiers),
                    }
                    for a in channel.actions
                },
                "limits": channel.limits,
                "not_supported": list(channel.not_supported),
                "next_action": _next_action(channel, status, availability),
            }
        )

    planned = [
        {"name": c.name, "description": c.description, "next_action": c.next_action}
        for c in registry.planned.values()
    ]
    summary = {
        "visible": len(rows),
        "ready": sum(1 for r in rows if r["status"] == "ready"),
        "degraded": sum(1 for r in rows if r["status"] == "degraded"),
        "needs_setup": sum(1 for r in rows if r["status"] == "needs_setup"),
        "needs_login": sum(1 for r in rows if r["status"] == "needs_login"),
        "needs_key": sum(1 for r in rows if r["status"] == "needs_key"),
        "experimental": sum(1 for r in rows if r["status"] == "experimental"),
        "planned": len(planned),
        "runnable": sum(1 for r in rows if r["runnable"]),
        "tiers": {
            tier: sum(1 for row in rows if tier in row["tiers"]) for tier in TIERS
        },
    }
    return {
        "keys_file": str(keys.path),
        "keys_file_exists": bool(keys.path and keys.path.exists()),
        "opencli": opencli_version,
        "profile": profile,
        "state": health.report(),
        "quota": quota.report(),
        "channels": rows,
        "planned": planned,
        "summary": summary,
    }


def format_doctor_text(report: dict) -> str:
    lines = []
    opencli = report.get("opencli", {})
    profile = report.get("profile", {})
    lines.append(f"deep-reach doctor")
    lines.append(f"keys:     {report.get('keys_file')} ({'found' if report.get('keys_file_exists') else 'missing'})")
    lines.append(
        f"opencli:  {opencli.get('installed', 'not installed')} "
        f"(recommended {opencli.get('recommended', '?')})"
    )
    if opencli.get("up_to_date") is False and opencli.get("action"):
        lines.append(f"          → {opencli['action']}")
    if profile.get("connected"):
        lines.append(
            f"browser:  connected (contextId {profile.get('context_id')}, "
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
        lines.append(f"browser:  not connected ({profile.get('error', 'install the Browser Bridge extension')})")
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
            actions = ", ".join(row["actions"]) or "-"
            tiers = ",".join(row.get("tiers") or [])
            lines.append(
                f"  {row['name']:<14} {row['status']:<13} {tiers:<7} {actions}"
            )
            if row["status"] not in {"ready", "experimental"} or row.get("next_action") not in {"-", ""}:
                lines.append(f"      → {row['next_action']}")
        lines.append("")

    if report.get("planned"):
        lines.append(f"PLANNED: {len(report['planned'])} channels (run `deep-reach roadmap`)")
        lines.append("")

    summary = report.get("summary", {})
    tiers = summary.get("tiers") or {}
    lines.append(
        f"{summary.get('visible', 0)} visible; "
        f"{summary.get('ready', 0)} ready; "
        f"{summary.get('degraded', 0)} degraded; "
        f"{summary.get('needs_setup', 0)} need setup; "
        f"{summary.get('needs_login', 0)} need login; "
        f"{summary.get('needs_key', 0)} need key; "
        f"{summary.get('experimental', 0)} experimental; "
        f"{summary.get('planned', 0)} planned; "
        f"{summary.get('runnable', 0)} runnable now"
    )
    lines.append(
        f"tiers:    p0 {tiers.get('p0', 0)} / p1 {tiers.get('p1', 0)} / "
        f"p2 {tiers.get('p2', 0)} channels"
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
    return "\n".join(lines)
