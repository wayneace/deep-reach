"""OpenCLI 2.x backend.

OpenCLI is an external CLI. We run it in the Deep-Reach browser profile,
read its JSON envelope, and normalize the result. Write commands are allowed
when the channel action declares them.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
from typing import Optional

from ..channels.base import BackendSpec, Channel
from ..runtime.availability import OPENCLI_CLIENT_HINT, OPENCLI_PACKAGE
from ..runtime.browser_config import normalize_opencli_profile
from ..runtime.child_env import child_env
from ..runtime.dispatch import BACKENDS
from ..runtime.result import (
    BAD_INPUT,
    NEED_SETUP,
    TIMEOUT,
    UPSTREAM_BROKEN,
    ReachError,
)
from .opencli_compat import classify_opencli_error, opencli_items, parse_envelope

#: Oldest OpenCLI this project is tested against. `deep-reach doctor` compares
#: the installed version and tells the user how to upgrade; it never upgrades
#: automatically, because OpenCLI is an external CLI.
RECOMMENDED_VERSION = "2.0.3"

OPENCLI_LABELS = (
    "opencli-youtube",
    "opencli-twitter",
    "opencli-reddit",
    "opencli-bilibili",
    "opencli-xueqiu",
    "opencli-xiaohongshu",
    "opencli-zhihu",
    "opencli-weibo",
    "opencli-douyin",
    "opencli-amazon",
    "opencli-producthunt",
)


def _version_tuple(text: str):
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def version_status(
    installed: str, recommended: str = RECOMMENDED_VERSION
) -> dict:
    """Compare the installed OpenCLI with the version this project targets."""
    current = _version_tuple(installed)
    target = _version_tuple(recommended)
    if current is None or target is None:
        return {
            "installed": installed,
            "missing": False,
            "recommended": recommended,
            "up_to_date": None,
            "action": "cannot parse the installed OpenCLI version",
        }
    up_to_date = current >= target
    return {
        "installed": installed,
        "missing": False,
        "recommended": recommended,
        "up_to_date": up_to_date,
        "action": ""
        if up_to_date
        else "OpenCLI is older than recommended; upgrade with: "
        f"npm install -g {OPENCLI_PACKAGE}@{recommended}",
    }


class OpenCLIClient:
    def __init__(
        self,
        bin_path: Optional[str] = None,
        profile: Optional[str] = None,
        window: str = "background",
        auto_launch: bool = False,
    ):
        self.bin = (
            bin_path
            or os.environ.get("DEEP_REACH_OPENCLI_BIN")
            or shutil.which("opencli")
            or "opencli"
        )
        self.profile = normalize_opencli_profile(profile)
        self.window = window
        self.auto_launch = auto_launch
        self.connect_timeout = 15.0
        self._read_cache: dict[str, set[str]] = {}

    def _binary_available(self) -> bool:
        if os.path.isabs(self.bin):
            return os.path.exists(self.bin)
        return bool(shutil.which(self.bin))

    def ensure_browser(self) -> None:
        """Start the dedicated Chrome profile when a P1 action needs it."""
        if not self.auto_launch or not self.profile:
            return
        if not self._binary_available():
            return
        if self.profile_status().get("connected"):
            return

        from ..runtime.profile import launch

        result = launch(page="about:blank")
        if not result.get("ok"):
            raise ReachError(
                NEED_SETUP,
                "cannot launch the dedicated Chrome profile: "
                f"{result.get('error', 'unknown error')}",
                hint=(
                    "Run `deep-reach profile launch` and make sure the OpenCLI "
                    "extension is installed in that window."
                ),
            )

        deadline = time.monotonic() + self.connect_timeout
        while time.monotonic() < deadline:
            time.sleep(0.5)
            if self.profile_status().get("connected"):
                return
        raise ReachError(
            NEED_SETUP,
            "the dedicated Chrome profile did not connect",
            hint=(
                "Open the dedicated Chrome window and make sure the OpenCLI "
                "extension is enabled; then run `deep-reach profile status`."
            ),
        )

    def _effective_profile(self) -> str:
        return self.profile

    @staticmethod
    def _kill_tree(proc: "subprocess.Popen[str]") -> None:
        """Kill the wrapper and its children.

        On Windows `opencli` is often a .cmd shim; killing only the shim leaves
        node holding the stdout pipe, so `communicate()` never returns.
        """
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                env=child_env(),
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                pass

    def _run(self, argv: list[str], timeout: float, with_profile: bool = True):
        if with_profile and not self.profile:
            raise ReachError(
                NEED_SETUP,
                "OpenCLI requires a dedicated browser profile",
                hint=(
                    "Run `deep-reach profile launch`, install the OpenCLI "
                    "extension in that window, then `deep-reach profile set "
                    "<contextId>`."
                ),
            )
        env = child_env()
        if with_profile:
            env["OPENCLI_PROFILE"] = self.profile
        else:
            env.pop("OPENCLI_PROFILE", None)
        env["OPENCLI_WINDOW"] = self.window
        env["OPENCLI_CDP_ENDPOINT"] = ""
        env["OPENCLI_CDP_TARGET"] = ""
        try:
            proc = subprocess.Popen(
                [self.bin, *argv],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                start_new_session=os.name != "nt",
            )
        except FileNotFoundError as exc:
            raise ReachError(
                NEED_SETUP,
                f"opencli is not installed; {OPENCLI_CLIENT_HINT}",
            ) from exc
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except KeyboardInterrupt:
            self._kill_tree(proc)
            try:
                proc.communicate(timeout=5)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                pass
            raise
        except subprocess.TimeoutExpired as exc:
            self._kill_tree(proc)
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            raise ReachError(TIMEOUT, f"opencli timed out after {timeout}s") from exc
        return subprocess.CompletedProcess(
            args=[self.bin, *argv],
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def version(self) -> str:
        result = self._run(["--version"], timeout=10, with_profile=False)
        text = (result.stdout or result.stderr).strip()
        return text or "unknown"

    def _status_error(self, message: str) -> dict:
        return {
            "setting": self.profile,
            "configured": bool(self.profile),
            "connected": False,
            "context_id": self.profile or None,
            "profile_ids": [],
            "profiles": [],
            "window": self.window,
            "error": message,
        }

    def profile_status(self) -> dict:
        """Return connected profiles and whether the configured one is usable."""
        try:
            result = self._run(["doctor"], timeout=10, with_profile=False)
        except ReachError as exc:
            return self._status_error(exc.message)
        text = (result.stdout or "").strip()
        if not text:
            return self._status_error("opencli doctor returned nothing")
        try:
            payload = parse_envelope(text)
        except ReachError as exc:
            return self._status_error(exc.message)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        profiles = data.get("profiles", []) if isinstance(data, dict) else []
        if not isinstance(profiles, list):
            profiles = []
        profile_ids = [
            str(profile.get("contextId"))
            for profile in profiles
            if isinstance(profile, dict) and profile.get("contextId")
        ]
        selected = next(
            (
                profile
                for profile in profiles
                if isinstance(profile, dict)
                and str(profile.get("contextId")) == self.profile
            ),
            None,
        )
        configured = bool(self.profile)
        connected = bool(configured and selected is not None)
        error = ""
        if not configured:
            error = "no dedicated profile configured"
        elif not connected:
            error = f"configured profile {self.profile} is not connected"
        return {
            "setting": self.profile,
            "configured": configured,
            "connected": connected,
            "context_id": self.profile or None,
            "profile_ids": profile_ids,
            "profiles": profiles,
            "daemon": bool(data.get("daemonRunning")),
            "cli_version": data.get("cliVersion"),
            "extension_version": (
                (selected or {}).get("extensionVersion")
                or data.get("extensionVersion")
            ),
            "extension_outdated": bool(data.get("extensionOutdated")),
            "latest_extension_version": data.get("latestExtensionVersion"),
            "window": self.window,
            "error": error,
        }

    def read_commands(self, site: str) -> set[str]:
        if site in self._read_cache:
            return self._read_cache[site]
        result = self._run(
            ["list", "--site", site, "--limit", "100", "-f", "json"], timeout=30
        )
        if not result.stdout.strip():
            raise ReachError(
                UPSTREAM_BROKEN,
                result.stderr.strip() or f"opencli list returned nothing for {site}",
            )
        payload = parse_envelope(result.stdout)
        if not payload.get("ok"):
            raise classify_opencli_error(payload, result.stderr.strip())
        commands = payload.get("data", {}).get("commands", [])
        read = {
            str(c.get("command", "")).split()[-1]
            for c in commands
            if isinstance(c, dict) and c.get("access") == "read"
        }
        self._read_cache[site] = read
        return read

    def is_read(self, site: str, command: str) -> bool:
        return command in self.read_commands(site)

    def run(self, site: str, command: str, args: list[str], timeout: float):
        result = self._run([site, command, *args, "-f", "json"], timeout=timeout)
        stdout = result.stdout.strip()
        if not stdout:
            raise ReachError(
                UPSTREAM_BROKEN,
                result.stderr.strip() or f"opencli {site} {command} returned nothing",
            )
        payload = parse_envelope(stdout)
        if not payload.get("ok"):
            raise classify_opencli_error(payload, result.stderr.strip())
        return payload.get("data", {})


def _build_args(spec: BackendSpec, params: dict) -> list[str]:
    args: list[str] = []
    for token in spec.options.get("args", []):
        try:
            args.append(str(token).format(**params))
        except KeyError as exc:
            raise ReachError(
                BAD_INPUT, f"missing param for opencli arg {token!r}: {exc}"
            ) from exc
    if spec.options.get("limit") and "limit" in params:
        args.extend(["--limit", str(params["limit"])])
    return args


def make_opencli_handler(client: OpenCLIClient):
    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        site = spec.options.get("site")
        if not site:
            raise ReachError(BAD_INPUT, f"{spec.label} is missing the opencli site option")
        command = str(spec.options.get("command") or action)
        args = _build_args(spec, params)
        client.ensure_browser()
        data = client.run(str(site), command, args, timeout)
        return opencli_items(
            data,
            source=channel.name,
            category=channel.category,
            platform=str(spec.options.get("platform") or site),
            backend=spec.label,
        )

    return handler


def register_opencli_backends(
    client: Optional[OpenCLIClient] = None,
    labels: Optional[tuple[str, ...]] = None,
) -> OpenCLIClient:
    client = client or OpenCLIClient()
    handler = make_opencli_handler(client)
    for label in labels or OPENCLI_LABELS:
        BACKENDS.register(label, handler)
    return client
