"""First-run deployment: private keys file and next steps.

`setup` is intentionally not a diagnostic command. It builds a plan, asks the
caller to confirm, then creates the private keys file from the packaged
template. OpenCLI installation is delegated to the agent client's own package
manager; this module only prints the instruction.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .availability import BROWSER_BRIDGE_URL, OPENCLI_CLIENT_HINT
from .child_env import child_env
from .keys import Keys, default_keys_path, template_path
from .result import CONFIG_ERROR, ReachError, redact_text
from .secure_paths import ensure_private_dir, tighten_file

KEY_NOTES: tuple[tuple[str, str], ...] = (
    ("official.github.token", "GitHub API: 5,000 req/h instead of 60"),
    ("official.youtube.api_key", "YouTube P0 API (search costs 100 units)"),
    ("official.ebay.client_id", "eBay Browse API (with client_secret)"),
    ("official.ebay.client_secret", "eBay Browse API (with client_id)"),
    ("official.etsy.api_key", "Etsy Open API"),
    ("official.producthunt.token", "Product Hunt GraphQL API"),
    ("official.uspto.odp_api_key", "USPTO Open Data Portal"),
    ("official.epo.consumer_key", "EPO OPS (with consumer_secret)"),
    ("official.epo.consumer_secret", "EPO OPS (with consumer_key)"),
    ("xueqiu.cookie", "Xueqiu cookie for hot/hot_stocks"),
    ("search.tavily.api_key", "Tavily search"),
    ("search.firecrawl.api_key", "Firecrawl search and scrape"),
    ("search.brightdata.api_token", "Bright Data SERP and Unlocker"),
    ("search.brave.api_key", "Brave search"),
    ("search.jina.api_key", "Jina Reader: 500 RPM instead of 20"),
)


@dataclass(frozen=True)
class SetupPlan:
    keys_path: Path
    keys_exists: bool
    keys_is_symlink: bool
    parent_exists: bool
    parent_is_canonical: bool
    opencli_version: str
    keys: Keys

    @property
    def create_file(self) -> bool:
        return not self.keys_exists and not self.keys_is_symlink

    @property
    def create_dir(self) -> bool:
        return not self.parent_exists


@dataclass(frozen=True)
class ActionResult:
    status: str
    path: Path
    note: str = ""


def detect_opencli_version() -> str:
    bin_path = os.environ.get("DEEP_REACH_OPENCLI_BIN") or shutil.which("opencli")
    if not bin_path:
        return ""
    try:
        result = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            env=child_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    output = (result.stdout or result.stderr).strip()
    return output or "unknown"


def build_setup_plan(
    keys: Keys, opencli_version: Optional[str] = None
) -> SetupPlan:
    path = Path(keys.path) if keys.path else default_keys_path()
    parent = path.parent
    return SetupPlan(
        keys_path=path,
        keys_exists=path.exists(),
        keys_is_symlink=path.is_symlink(),
        parent_exists=parent.exists(),
        parent_is_canonical=parent == Path.home() / ".deep-reach",
        opencli_version=(
            detect_opencli_version() if opencli_version is None else opencli_version
        ),
        keys=keys,
    )


def apply_setup(plan: SetupPlan) -> list[ActionResult]:
    results: list[ActionResult] = []
    parent = plan.keys_path.parent

    if plan.parent_is_canonical:
        note = ensure_private_dir(parent)
        status = "kept" if plan.parent_exists else "created"
    elif plan.parent_exists:
        note = ""
        status = "kept"
    else:
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ReachError(
                CONFIG_ERROR, f"cannot create {parent}: {exc}"
            ) from exc
        note = ""
        status = "created"
    results.append(ActionResult(status, parent, note))

    if plan.keys_is_symlink:
        results.append(
            ActionResult(
                "skipped", plan.keys_path, "symlink; target not touched"
            )
        )
        return results

    if plan.keys_exists:
        results.append(ActionResult("kept", plan.keys_path, tighten_file(plan.keys_path)))
        return results

    _write_template(plan.keys_path)
    results.append(ActionResult("created", plan.keys_path))
    return results


def _write_template(path: Path) -> None:
    source = template_path()
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise ReachError(
            CONFIG_ERROR, f"cannot read template {source}: {exc}"
        ) from exc

    fd, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix="keys-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def format_setup_plan(plan: SetupPlan) -> str:
    from ..backends.opencli import RECOMMENDED_VERSION

    lines = ["Deep-Reach setup", ""]

    creates: list[str] = []
    keeps: list[str] = []
    if plan.create_dir:
        creates.append(
            f"  {_display_path(plan.keys_path.parent)}/  directory, 0700"
        )
    if plan.create_file:
        creates.append(
            f"  {_display_path(plan.keys_path)}  from template, 0600"
        )
    if plan.keys_exists:
        keeps.append(
            f"  {_display_path(plan.keys_path)}  already exists; not overwritten"
        )
    elif plan.keys_is_symlink:
        keeps.append(
            f"  {_display_path(plan.keys_path)}  symlink; target not touched"
        )

    if creates:
        lines.append("Will create:")
        lines.extend(creates)
    if keeps:
        lines.append("Keep:")
        lines.extend(keeps)
    if not creates and not keeps:
        lines.append("No file changes.")

    lines.append("")
    lines.append("No API keys will be written.")
    lines.append("Main Chrome profile is not touched.")
    lines.append("")

    if plan.opencli_version:
        lines.append(
            f"OpenCLI: {plan.opencli_version} (installed; no install needed)"
        )
    else:
        lines.append("OpenCLI: not installed")
        lines.append(f"  {OPENCLI_CLIENT_HINT}")
        lines.append(
            f"  Recommended: npm install -g @jackwener/opencli@{RECOMMENDED_VERSION}"
        )

    return redact_text("\n".join(lines))


def format_setup_summary(
    plan: SetupPlan, results: list[ActionResult], keys: Keys
) -> str:
    lines = ["Deep-Reach setup complete.", "", "Files:"]
    if results:
        for result in results:
            mode = _mode(result.path)
            line = f"  {result.status:<8} {_display_path(result.path)}"
            if mode:
                line += f"  {mode}"
            if result.note:
                line += f"  ({result.note})"
            lines.append(line)
    else:
        lines.append("  no changes")

    missing = [
        (name, description)
        for name, description in KEY_NOTES
        if not keys.has(name)
    ]
    lines.append("")
    if missing:
        lines.append("Empty keys (all optional):")
        for name, description in missing:
            lines.append(f"  {name:<32} {description}")
    else:
        lines.append("Empty keys: none.")

    lines.append("")
    lines.append("Next:")
    step = 1
    if not plan.opencli_version:
        lines.append(
            f"  {step}. Install OpenCLI with your agent client's package manager."
        )
        step += 1
    lines.append(f"  {step}. deep-reach profile launch")
    step += 1
    lines.append(f"  {step}. Install/enable the OpenCLI extension in that window:")
    lines.append(f"     {BROWSER_BRIDGE_URL}")
    step += 1
    lines.append(f"  {step}. deep-reach profile status")
    step += 1
    lines.append(f"  {step}. deep-reach profile set <contextId>")
    step += 1
    lines.append(f"  {step}. deep-reach doctor")

    return redact_text("\n".join(lines))


def _display_path(path: Path) -> str:
    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        return str(path)
    return "~/" + relative.as_posix()


def _mode(path: Path) -> str:
    if os.name == "nt":
        return ""
    try:
        return f"{stat.S_IMODE(path.stat().st_mode):03o}"
    except OSError:
        return ""
