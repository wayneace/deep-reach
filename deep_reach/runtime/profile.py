"""Dedicated Chrome profile helpers.

`auto` follows the Chrome profile the OpenCLI extension is connected to.
A dedicated profile is opt-in: launch Chrome with its own user-data-dir,
install the OpenCLI extension once, then set the contextId.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from ..backends.opencli import OpenCLIClient
from .keys import Keys, default_keys_path


def status(keys: Optional[Keys] = None, client: Optional[OpenCLIClient] = None) -> dict:
    keys = keys or Keys.load()
    client = client or OpenCLIClient(profile=keys.get("browser.opencli_profile") or "auto")
    return {
        "setting": keys.get("browser.opencli_profile") or "auto",
        "opencli": client.profile_status(),
        "dedicated_dir": str(profile_dir()),
    }


def set_context(context_id: str) -> Path:
    path = default_keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = 'version: 1\n\nbrowser:\n  opencli_profile: "auto"\n'

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
    path.write_text(text, encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return path


def profile_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "deep-reach" / "chrome-profile"
    return Path.home() / ".deep-reach" / "chrome-profile"


def chrome_path() -> Optional[str]:
    candidates = [
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    for name in ("chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    return None


def launch() -> dict:
    chrome = chrome_path()
    if not chrome:
        return {"ok": False, "error": "Chrome not found; set CHROME_PATH or install Chrome"}
    path = profile_dir()
    path.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.Popen(
            [
                chrome,
                f"--user-data-dir={path}",
                "--profile-directory=Default",
                "chrome://extensions",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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
