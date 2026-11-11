"""Dedicated Chrome profile helpers.

A dedicated profile is required: launch Chrome with its own user-data-dir,
install the OpenCLI extension once, then bind its contextId. Deep-Reach never
falls back to the first connected Chrome profile.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from ..backends.opencli import OpenCLIClient
from .browser_config import normalize_opencli_profile
from .child_env import child_env
from .keys import Keys, default_keys_path
from .result import BAD_INPUT, ReachError
from .secure_paths import ensure_private_dir, tighten_file, write_target


def status(keys: Optional[Keys] = None, client: Optional[OpenCLIClient] = None) -> dict:
    keys = keys or Keys.load()
    setting = normalize_opencli_profile(keys.get("browser.opencli_profile"))
    client = client or OpenCLIClient(profile=setting)
    return {
        "setting": setting,
        "opencli": client.profile_status(),
        "dedicated_dir": str(profile_dir()),
    }


def set_context(context_id: str) -> Path:
    normalized = normalize_opencli_profile(context_id)
    if not normalized:
        raise ReachError(
            BAD_INPUT,
            "contextId must be 4-64 letters, digits, underscores, or hyphens",
        )
    context_id = normalized
    path = default_keys_path()
    target = write_target(path)
    parent = target.parent
    if parent == Path.home() / ".deep-reach":
        ensure_private_dir(parent)
    else:
        parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        text = target.read_text(encoding="utf-8")
    else:
        text = 'version: 1\n\nbrowser:\n  opencli_profile: ""\n'

    line = re.compile(r"(?m)^(\s*opencli_profile:\s*).*$")
    if line.search(text):
        text = line.sub(lambda m: f'{m.group(1)}"{context_id}"', text, count=1)
    elif re.search(r"(?m)^browser:\s*$", text):
        text = re.sub(
            r"(?m)^browser:\s*$",
            f'browser:\n  opencli_profile: "{context_id}"',
            text,
            count=1,
        )
    else:
        text = text.rstrip() + f'\n\nbrowser:\n  opencli_profile: "{context_id}"\n'

    handle = tempfile.NamedTemporaryFile(
        "w",
        dir=str(parent),
        prefix="keys-",
        delete=False,
        encoding="utf-8",
    )
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    except Exception:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    tighten_file(target)
    return path


def profile_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "deep-reach" / "chrome-profile"
    return Path.home() / ".deep-reach" / "chrome-profile"


_MAC_CHROME_RE = re.compile(
    r"(?i)^/.*/google chrome\.app/contents/macos/google chrome(?: |$)"
)
_MAC_CHROMIUM_RE = re.compile(
    r"(?i)^/.*/chromium\.app/contents/macos/chromium(?: |$)"
)
_LINUX_CHROME_PREFIXES = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
)


def _is_chrome_command(command: str, needle: str) -> bool:
    if needle not in command:
        return False
    if _MAC_CHROME_RE.match(command) or _MAC_CHROMIUM_RE.match(command):
        return True
    lowered = command.lower()
    return any(lowered.startswith(prefix) for prefix in _LINUX_CHROME_PREFIXES)


def _chrome_pids() -> list[int]:
    path = profile_dir()
    if os.name == "nt":
        script = (
            "Get-CimInstance Win32_Process | Where-Object { "
            "$_.Name -match '^(chrome|chromium|msedge)\\.exe$' -and "
            f"$_.CommandLine -like '*--user-data-dir={path}*' }} | "
            "Select-Object -ExpandProperty ProcessId"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                env=child_env(),
            )
        except (OSError, subprocess.SubprocessError):
            return []
        pids = []
        for line in (result.stdout or "").splitlines():
            try:
                pids.append(int(line.strip()))
            except ValueError:
                pass
        return pids

    needle = f"--user-data-dir={path}"
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            env=child_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return []

    pids = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        pid_text, _, command = line.partition(" ")
        if _is_chrome_command(command, needle):
            try:
                pids.append(int(pid_text))
            except ValueError:
                pass
    return pids


def close() -> dict:
    """Close Chrome processes using the dedicated profile, never the main one."""
    pids = _chrome_pids()
    closed = []
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    env=child_env(),
                    timeout=10,
                )
            else:
                os.kill(pid, signal.SIGTERM)
            closed.append(pid)
        except (OSError, subprocess.SubprocessError):
            pass
    return {"ok": True, "closed": closed}


def chrome_path() -> Optional[str]:
    candidates = [
        os.environ.get("CHROME_PATH"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        str(
            Path.home()
            / "Applications"
            / "Google Chrome.app"
            / "Contents"
            / "MacOS"
            / "Google Chrome"
        ),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe"
        ),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    for name in ("chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    return None


def launch(page: Optional[str] = "chrome://extensions") -> dict:
    chrome = chrome_path()
    if not chrome:
        return {"ok": False, "error": "Chrome not found; set CHROME_PATH or install Chrome"}
    path = profile_dir()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    ensure_private_dir(path)
    args = [chrome, f"--user-data-dir={path}", "--profile-directory=Default"]
    if page is None:
        args.append("--no-startup-window")
    else:
        args.append(page)
    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=child_env(),
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc), "chrome": chrome, "profile_dir": str(path)}
    return {
        "ok": True,
        "chrome": chrome,
        "profile_dir": str(path),
        "pid": process.pid,
        "next": "在这个窗口安装/启用 OpenCLI 扩展，然后运行 `deep-reach profile status` 获取 contextId",
    }
