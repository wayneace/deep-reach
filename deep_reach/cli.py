"""Deep-Reach product CLI.

Primary surface:

    deep-reach <channel> <action> [args]
    deep-reach doctor | channels | capabilities | setup | profile | update

Default output is one JSON object. `--text` gives a human summary.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .backends.brave import register_brave_backend
from .backends.brightdata import register_brightdata_backends
from .backends.bsk_guard import run_bsk
from .backends.ebay import register_ebay_backend
from .backends.epo import register_epo_backend
from .backends.etsy import register_etsy_backend
from .backends.firecrawl import register_firecrawl_backends
from .backends.github import register_github_backend
from .backends.http import register_http_backends
from .backends.jina import register_jina_backend
from .backends.opencli import OpenCLIClient, register_opencli_backends
from .backends.producthunt import register_producthunt_backend
from .backends.public import register_public_backends
from .backends.tavily import register_tavily_backends
from .backends.uspto import register_uspto_backend
from .backends.v2ex import register_v2ex_backend
from .backends.xueqiu import register_xueqiu_backends
from .channels import load_registry
from .channels.base import TIERS
from .product import LEVELS, NAME, NON_GOALS, PROMISES, TAGLINE, TIER_TABLE
from .runtime import health as health_state
from .runtime import quota as quota_state
from .runtime import state as state_store
from .runtime.availability import (
    OPENCLI_BIN_ENV,
    OPENCLI_INSTALL_COMMAND,
    action_risk,
    channel_availability,
    channel_risk,
    detect_environment,
    next_action_for,
)
from .runtime.dispatch import run_action
from .runtime.doctor import build_doctor_report, format_doctor_text
from .runtime.keys import Keys, template_path
from .runtime.profile import launch as launch_profile
from .runtime.profile import profile_dir, set_context, status as profile_status
from .runtime.result import ReachError, dump

JSON_DEFAULT = True


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001 - best effort
                pass


def _load_keys() -> Keys:
    return Keys.load()


def _as_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _register_backends(keys: Keys) -> None:
    profile = keys.get("browser.opencli_profile") or "auto"
    register_opencli_backends(OpenCLIClient(profile=profile))
    register_jina_backend(keys)
    register_tavily_backends(keys)
    register_brave_backend(keys)
    register_firecrawl_backends(keys)
    register_brightdata_backends(keys)
    register_http_backends()
    register_public_backends(keys)
    register_github_backend(keys)
    register_v2ex_backend()
    register_xueqiu_backends(keys)
    register_ebay_backend(keys)
    register_etsy_backend(keys)
    register_producthunt_backend(keys)
    register_uspto_backend(keys)
    register_epo_backend(keys)


def _print_json(data: dict, pretty: bool = False) -> None:
    print(dump(data, pretty=pretty))


def _text_summary(env: dict) -> str:
    if env.get("ok"):
        items = env.get("items") or []
        lines = [
            f"{env.get('channel')}/{env.get('action')}: {len(items)} item(s) "
            f"via {env.get('backend')} ({env.get('tier')})"
        ]
        for item in items[:5]:
            title = item.get("title") or item.get("text") or "(no title)"
            url = item.get("url") or ""
            lines.append(f"- {str(title)[:100]}")
            if url:
                lines.append(f"  {url}")
        if len(items) > 5:
            lines.append(f"... {len(items) - 5} more")
        return "\n".join(lines)
    error = env.get("error") or {}
    return (
        f"{env.get('channel')}/{env.get('action')}: {error.get('code')}\n"
        f"{error.get('message')}\n"
        f"→ {error.get('hint')}"
    )


# ── channel actions ──────────────────────────────────────────


def cmd_channel_action(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
        keys = _load_keys()
    except ReachError as exc:
        print(f"CONFIG_ERROR: {exc.message}", file=sys.stderr)
        return 2

    channel = registry.get(args.channel_name)
    if channel is None:
        print(f"unknown channel: {args.channel_name}", file=sys.stderr)
        return 2
    action = channel.action(args.action_name) if hasattr(channel, "action") else None
    if action is None:
        print(f"unknown action: {args.action_name}", file=sys.stderr)
        return 2

    params = {}
    for param in action.params:
        value = getattr(args, param.name, None)
        if value is not None:
            params[param.name] = value

    _register_backends(keys)
    env = run_action(channel, action.name, params, keys=keys)
    if getattr(args, "text", False):
        print(_text_summary(env))
    else:
        _print_json(env, pretty=getattr(args, "pretty", False))
    return 0 if env.get("ok") else 1


def cmd_channel_help(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
    except ReachError as exc:
        print(f"CONFIG_ERROR: {exc.message}", file=sys.stderr)
        return 2
    channel = registry.get(args.channel_name)
    if channel is None:
        print(f"unknown channel: {args.channel_name}", file=sys.stderr)
        return 2
    print(f"{channel.name} [{channel.level}/{channel.status}] {channel.description}")
    for action in channel.actions:
        params = ", ".join(p.name for p in action.params) or "-"
        tiers = "+".join(action.tiers) or "-"
        print(
            f"  {action.name:<12} requires={action.requires:<6} "
            f"tiers={tiers:<7} params={params}"
        )
    if channel.limits:
        print(f"  limits: {channel.limits}")
    if channel.next_action:
        print(f"  next: {channel.next_action}")
    return 0


# ── product commands ─────────────────────────────────────────


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
        keys = _load_keys()
    except ReachError as exc:
        print(f"CONFIG_ERROR: {exc.message}", file=sys.stderr)
        return 2
    report = build_doctor_report(registry, keys)
    if args.json:
        _print_json(report, pretty=True)
    else:
        print(format_doctor_text(report))
    return 0


def cmd_channels(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
        keys = _load_keys()
    except ReachError as exc:
        print(f"CONFIG_ERROR: {exc.message}", file=sys.stderr)
        return 2
    env = detect_environment(keys)
    channels = registry.visible
    if args.json:
        rows = []
        for channel in channels.values():
            availability = channel_availability(channel, env)
            rows.append(
                {
                    "name": channel.name,
                    "level": channel.level,
                    "status": availability.status,
                    "declared_status": availability.declared_status,
                    "runnable": availability.runnable,
                    "available_actions": list(availability.available_actions),
                    "unavailable_actions": availability.unavailable_actions,
                    "category": channel.category,
                    "description": channel.description,
                    "risk": channel_risk(channel),
                    "tiers": list(channel.tiers),
                    "ui_fallback_actions": list(availability.ui_fallback_actions),
                    "actions": [
                        {
                            "name": a.name,
                            "requires": a.requires,
                            "tiers": list(a.tiers),
                            "risk": action_risk(a),
                            "ui_fallback": a.ui_fallback,
                            "description": a.description,
                        }
                        for a in channel.actions
                    ],
                    "limits": channel.limits,
                    "not_supported": list(channel.not_supported),
                    "next_action": channel.next_action,
                    "effective_next_action": next_action_for(
                        channel, availability, env
                    ),
                }
            )
        _print_json({"channels": rows}, pretty=True)
        return 0

    for level in ("default", "optional", "experimental"):
        rows = [c for c in channels.values() if c.level == level]
        if not rows:
            continue
        print(level.upper())
        for channel in sorted(rows, key=lambda c: c.name):
            availability = channel_availability(channel, env)
            ui_fallback = set(availability.ui_fallback_actions)
            actions = (
                ", ".join(
                    f"{a.name}(bsk)" if a.name in ui_fallback else a.name
                    for a in channel.actions
                )
                or "-"
            )
            print(
                f"  {channel.name:<14} {availability.status:<13} "
                f"risk={channel_risk(channel):<6} {actions}"
            )
            hint = next_action_for(channel, availability, env)
            if availability.status not in {"ready", "experimental"} and hint != "-":
                print(f"      → {hint}")
        print()
    print("Use `deep-reach <channel> <action> --help` for arguments.")
    print("Status is environment-aware; run `deep-reach doctor` for browser/key details.")
    return 0


def cmd_capabilities(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
    except ReachError as exc:
        print(f"CONFIG_ERROR: {exc.message}", file=sys.stderr)
        return 2
    channels = registry.visible
    if args.channel:
        channel = registry.get(args.channel)
        if channel is None:
            print(f"unknown channel: {args.channel}", file=sys.stderr)
            return 2
        channels = {channel.name: channel}

    if args.json:
        payload = {
            "channels": [
                {
                    "name": c.name,
                    "level": c.level,
                    "status": c.status,
                    "description": c.description,
                    "risk": channel_risk(c),
                    "tiers": list(c.tiers),
                    "actions": [
                        {
                            "name": a.name,
                            "requires": a.requires,
                            "tiers": list(a.tiers),
                            "risk": action_risk(a),
                            "ui_fallback": a.ui_fallback,
                            "description": a.description,
                        }
                        for a in c.actions
                    ],
                    "limits": c.limits,
                    "not_supported": list(c.not_supported),
                    "next_action": c.next_action,
                }
                for c in channels.values()
            ]
        }
        _print_json(payload, pretty=True)
        return 0

    for channel in sorted(channels.values(), key=lambda c: c.name):
        print(
            f"{channel.name} [{channel.level}/{channel.status}] "
            f"risk={channel_risk(channel)} {channel.description}"
        )
        for action in channel.actions:
            tiers = "+".join(action.tiers)
            if action.ui_fallback:
                tiers = f"{tiers}+bsk" if tiers else "bsk"
            else:
                tiers = tiers or "-"
            print(
                f"  {action.name:<12} requires={action.requires:<6} "
                f"tiers={tiers:<7} risk={action_risk(action):<6} "
                f"{action.description}"
            )
        if channel.limits:
            print(f"  limits: {channel.limits}")
        if channel.not_supported:
            print(f"  not supported: {', '.join(channel.not_supported)}")
        print()
    return 0


def cmd_tiers(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
    except ReachError as exc:
        print(f"CONFIG_ERROR: {exc.message}", file=sys.stderr)
        return 2

    channels = registry.visible

    def tier_channels(tier: str) -> list[str]:
        if tier == "p3":
            return sorted(
                name
                for name, channel in channels.items()
                if any(action.ui_fallback for action in channel.actions)
            )
        return sorted(
            name for name, channel in channels.items() if tier in channel.tiers
        )

    payload = {
        "tiers": [
            {
                "id": tier,
                "label": TIER_TABLE[tier]["label"],
                "access": TIER_TABLE[tier]["access"],
                "kind": "fallback" if tier == "p3" else "automatic",
                "manual": tier == "p3",
                "channels": tier_channels(tier),
            }
            for tier in TIERS
        ],
        "channels": [
            {
                "name": channel.name,
                "risk": channel_risk(channel),
                "tiers": list(channel.tiers),
                "actions": {a.name: list(a.tiers) for a in channel.actions},
                "ui_fallback_actions": [
                    a.name for a in channel.actions if a.ui_fallback
                ],
            }
            for channel in sorted(channels.values(), key=lambda c: c.name)
        ],
    }
    if args.json:
        _print_json(payload, pretty=True)
        return 0

    print("TIERS (dispatch order)")
    for row in payload["tiers"]:
        print(f"  {row['id'].upper():<3} {row['label']}")
        if row["manual"]:
            print(f"      fallback / manual; {len(row['channels'])} channel(s)")
        else:
            print(f"      {row['access']}; {len(row['channels'])} channel(s)")
        if row["channels"]:
            print(f"      {', '.join(row['channels'])}")
        print()
    print("COVERAGE")
    for channel in sorted(channels.values(), key=lambda c: c.name):
        parts = []
        for action in channel.actions:
            tiers = "+".join(action.tiers)
            if action.ui_fallback:
                tiers = f"{tiers}+bsk" if tiers else "bsk"
            parts.append(f"{action.name}({tiers or '-'})")
        print(
            f"  {channel.name:<14} {','.join(channel.tiers) or '-':<7} "
            f"{', '.join(parts)}"
        )
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    if args.clear:
        state_store.clear()
        print("deep-reach state cleared")
        return 0
    payload = health_state.report()
    if args.json:
        _print_json(payload, pretty=True)
        return 0
    print(f"state: {payload['path']}")
    logs = payload.get("requests_last_minute") or {}
    if not payload["cooldowns"] and not payload["paused_backends"] and not logs:
        print("  clean")
        return 0
    for item in payload["cooldowns"]:
        print(
            f"  cooldown {item['channel']:<14} "
            f"{item['retry_after_seconds']:>5}s  {item['code']}"
        )
    for item in payload["paused_backends"]:
        print(
            f"  paused   {item['channel']}/{item['action']}/{item['backend']}  "
            f"{item['retry_after_seconds']}s  {item['code']}"
        )
    if logs:
        print(
            "  requests/min: "
            + ", ".join(f"{name} {count}" for name, count in sorted(logs.items()))
        )
    for row in (quota_state.report().get("backends") or []):
        if row["used"]:
            print(
                f"  quota {row['backend']}: {row['used']}/{row['limit']} today"
            )
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    checks = []
    checks.append(("python", sys.version.split()[0], "ok"))
    uv = shutil.which("uv")
    checks.append(("uv", uv or "not found", "ok" if uv else "missing"))
    npm = shutil.which("npm")
    checks.append(("npm", npm or "not found", "ok" if npm else "missing"))
    opencli = os.environ.get(OPENCLI_BIN_ENV) or shutil.which("opencli")
    version = "not installed"
    if opencli:
        try:
            result = subprocess.run(
                [opencli, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            version = (result.stdout or result.stderr).strip() or "unknown"
        except Exception as exc:  # noqa: BLE001
            version = f"error: {exc}"
    checks.append(("opencli", version, "ok" if opencli else "missing"))

    try:
        keys = _load_keys()
    except ReachError as exc:
        print(f"CONFIG_ERROR: {exc.message}", file=sys.stderr)
        return 2
    checks.append(("keys", str(keys.path), "ok" if keys.path and keys.path.exists() else "missing (optional)"))
    template = template_path()
    checks.append(("template", str(template), "ok" if template.is_file() else "missing"))

    profile = profile_status(keys)
    connected = bool(profile.get("opencli", {}).get("connected"))
    checks.append(
        (
            "browser",
            f"connected ({profile['opencli'].get('context_id')})" if connected else "not connected",
            "ok" if connected else "missing",
        )
    )

    print("Deep-Reach setup")
    print()
    for name, value, state in checks:
        print(f"  {name:<10} {state:<18} {value}")
    print()
    keys_exists = bool(keys.path and keys.path.exists())
    if not keys_exists and keys.path is not None:
        keys.path.parent.mkdir(parents=True, exist_ok=True)
    printed_next = False
    if not opencli:
        print("Next: install OpenCLI:")
        print(f"  {OPENCLI_INSTALL_COMMAND}")
        print("Then install/enable the Browser Bridge extension:")
        print("  1. opencli.info/download or Chrome Web Store")
        print("  2. chrome://extensions → enable")
        print("  3. deep-reach doctor")
        printed_next = True
    elif not connected:
        print("Next: install/enable the OpenCLI Browser Bridge extension:")
        print("  1. opencli.info/download or Chrome Web Store")
        print("  2. chrome://extensions → enable")
        print("  3. deep-reach doctor")
        printed_next = True
    if not keys_exists:
        if printed_next:
            print()
        print(f"Keys: optional — copy {template} to {keys.path}.")
    if opencli and connected:
        print("Next: deep-reach doctor")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    if args.profile_command == "status":
        try:
            keys = _load_keys()
        except ReachError as exc:
            print(f"CONFIG_ERROR: {exc.message}", file=sys.stderr)
            return 2
        payload = profile_status(keys)
        if args.json:
            _print_json(payload, pretty=True)
        else:
            print(f"setting: {payload.get('setting')}")
            opencli = payload.get("opencli", {})
            print(f"connected: {opencli.get('connected')}")
            print(f"contextId: {opencli.get('context_id')}")
            print(f"extension: {opencli.get('extension_version')}")
            print(f"dedicated dir: {payload.get('dedicated_dir')}")
        return 0
    if args.profile_command == "set":
        path = set_context(args.context_id)
        print(f"opencli_profile set to {args.context_id} in {path}")
        return 0
    if args.profile_command == "launch":
        result = launch_profile()
        _print_json(result, pretty=True)
        return 0 if result.get("ok") else 1
    print("usage: deep-reach profile status|set <contextId>|launch", file=sys.stderr)
    return 2


def cmd_bsk(args: argparse.Namespace) -> int:
    try:
        keys = _load_keys()
    except ReachError:
        keys = Keys({})
    guard = _as_bool(keys.get("browser.bsk_guard"), True)
    return run_bsk(list(args.bsk_args), guard=guard)


def cmd_about(args: argparse.Namespace) -> int:
    print(f"{NAME} {__version__}")
    print(TAGLINE)
    print()
    print("Promises:")
    for promise in PROMISES:
        print(f"  - {promise}")
    print()
    print("Non-goals:")
    for item in NON_GOALS:
        print(f"  - {item}")
    print()
    print("Tiers (dispatch order):")
    for tier in TIERS:
        info = TIER_TABLE[tier]
        print(f"  {tier.upper():<3} {info['label']}")
        print(f"      {info['access']}")
    print()
    print("Levels:")
    for level, meaning in LEVELS.items():
        print(f"  {level:<13} {meaning}")
    return 0


def _latest_opencli_version() -> Optional[str]:
    npm = shutil.which("npm")
    if not npm:
        return None
    try:
        result = subprocess.run(
            [npm, "view", "@jackwener/opencli", "version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except Exception:  # noqa: BLE001 - optional network check
        return None
    return (result.stdout or "").strip() or None


def cmd_update(args: argparse.Namespace) -> int:
    from .backends.opencli import RECOMMENDED_VERSION

    print("Deep-Reach update")
    print()
    print(f"OpenCLI target version: {RECOMMENDED_VERSION}")
    print("Update OpenCLI with npm:")
    print(f"  {OPENCLI_INSTALL_COMMAND}@{RECOMMENDED_VERSION}")
    print("  or check: opencli --version")
    print("  or: deep-reach doctor   # compares installed vs recommended")
    if args.check:
        latest = _latest_opencli_version()
        if latest:
            print(f"  latest on npm: {latest}")
        else:
            print("  latest on npm: unavailable (npm missing or offline)")
    print()
    print("Project update:")
    print("  cd <deep-reach project>")
    print("  git pull")
    print("  uv sync")
    print()
    print("Then run: deep-reach doctor")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    paths = [
        Path.home() / ".deep-reach",
        profile_dir(),
    ]
    print("Deep-Reach uninstall (dry run)" if args.dry_run else "Deep-Reach uninstall")
    for path in paths:
        print(f"  would remove: {path}")
    print(f"  project: {Path.cwd()}")
    if not args.dry_run:
        print()
        print("Refusing to delete automatically. Re-run with --dry-run to review, then remove manually.")
        return 1
    return 0


# ── parser ───────────────────────────────────────────────────


def _add_action_parser(channel, action, parent) -> None:
    parser = parent.add_parser(action.name, help=action.description or action.name)
    for param in action.params:
        if param.name in {"query", "target", "id", "symbol", "keyword", "category", "url"}:
            kwargs = {"help": param.name}
            if not param.required:
                kwargs["nargs"] = "?"
            parser.add_argument(param.name, **kwargs)
        elif param.name == "limit":
            parser.add_argument("--limit", type=int, default=param.default or 20)
        elif param.name == "page":
            parser.add_argument("--page", type=int, default=param.default or 1)
        else:
            flags = [f"--{param.name}"]
            if param.type is int:
                parser.add_argument(*flags, type=int, default=param.default)
            else:
                parser.add_argument(*flags, default=param.default)
    parser.add_argument("--text", action="store_true", help="human-readable summary")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    parser.set_defaults(
        func=cmd_channel_action,
        channel_name=channel.name,
        action_name=action.name,
    )


def build_parser(registry) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=NAME,
        description=f"{TAGLINE} {__version__}",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor", help="what works, what doesn't, and next steps")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    channels = sub.add_parser("channels", help="list available channels")
    channels.add_argument("--json", action="store_true")
    channels.set_defaults(func=cmd_channels)

    capabilities = sub.add_parser("capabilities", help="channel capability contract")
    capabilities.add_argument("channel", nargs="?")
    capabilities.add_argument("--json", action="store_true")
    capabilities.set_defaults(func=cmd_capabilities)

    tiers = sub.add_parser("tiers", help="show the P0/P1/P2 ladder and coverage")
    tiers.add_argument("--json", action="store_true")
    tiers.set_defaults(func=cmd_tiers)

    state_cmd = sub.add_parser(
        "state", help="cooldowns, paused backends and pacing timestamps"
    )
    state_cmd.add_argument("--json", action="store_true")
    state_cmd.add_argument("--clear", action="store_true", help="forget saved health")
    state_cmd.set_defaults(func=cmd_state)

    setup = sub.add_parser("setup", help="check environment and next steps")
    setup.set_defaults(func=cmd_setup)

    profile = sub.add_parser("profile", help="inspect or set the Chrome profile")
    profile_sub = profile.add_subparsers(dest="profile_command")
    p_status = profile_sub.add_parser("status")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_profile)
    p_set = profile_sub.add_parser("set")
    p_set.add_argument("context_id")
    p_set.set_defaults(func=cmd_profile)
    p_launch = profile_sub.add_parser("launch")
    p_launch.set_defaults(func=cmd_profile)

    bsk = sub.add_parser(
        "bsk",
        help="guarded bsk passthrough (blocks direct internal-API calls)",
    )
    bsk.add_argument("bsk_args", nargs=argparse.REMAINDER)
    bsk.set_defaults(func=cmd_bsk)

    about = sub.add_parser("about", help="product promises and non-goals")
    about.set_defaults(func=cmd_about)

    update = sub.add_parser("update", help="how to update OpenCLI and this project")
    update.add_argument("--check", action="store_true", help="query the latest npm version")
    update.set_defaults(func=cmd_update)

    uninstall = sub.add_parser("uninstall", help="review what would be removed")
    uninstall.add_argument("--dry-run", action="store_true")
    uninstall.set_defaults(func=cmd_uninstall)

    for channel in registry.visible.values():
        ch = sub.add_parser(channel.name, help=channel.description or channel.name)
        ch_sub = ch.add_subparsers(dest="action")
        ch.set_defaults(func=cmd_channel_help, channel_name=channel.name)
        for action in channel.actions:
            _add_action_parser(channel, action, ch_sub)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    _ensure_utf8()
    try:
        registry = load_registry()
    except ReachError as exc:
        print(f"CONFIG_ERROR: {exc.message}", file=sys.stderr)
        return 2
    parser = build_parser(registry)
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        print(f"{NAME} {__version__}")
        print(TAGLINE)
        print()
        print("Quick start:")
        print("  deep-reach doctor")
        print("  deep-reach channels")
        print("  deep-reach bilibili search \"收纳\" --limit 5")
        print()
        print("Channels:", ", ".join(sorted(registry.visible)))
        return 0
    try:
        return int(args.func(args))
    except ReachError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        if exc.hint:
            print(f"→ {exc.hint}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
