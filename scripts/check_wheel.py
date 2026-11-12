"""Check that the built wheel ships the curated channel registry.

Run after `uv build --wheel`:

    uv run python scripts/check_wheel.py

The registry used to live outside the package, so an installed wheel silently
fell back to the two-channel builtin registry. This script is the release guard
for that failure mode.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import yaml

EXPECTED_VISIBLE = 21
REGISTRY_SUFFIX = "deep_reach/data/channels.yaml"
KEYS_TEMPLATE_SUFFIX = "deep_reach/data/keys.example.yaml"
SKILL_SUFFIX = "deep_reach/data/skill/SKILL.md"
SKILL_CAPS_SUFFIX = "deep_reach/data/skill/references/capabilities.md"


def main() -> int:
    wheels = sorted(Path("dist").glob("deep_reach-*.whl"))
    if not wheels:
        print("no wheel under dist/; run `uv build --wheel` first", file=sys.stderr)
        return 1

    wheel = wheels[-1]
    with zipfile.ZipFile(wheel) as archive:
        matches = [name for name in archive.namelist() if name.endswith(REGISTRY_SUFFIX)]
        if len(matches) != 1:
            print(
                f"{wheel}: expected one {REGISTRY_SUFFIX}, found {len(matches)}",
                file=sys.stderr,
            )
            return 1
        data = yaml.safe_load(archive.read(matches[0])) or {}
        keys_matches = [
            name for name in archive.namelist() if name.endswith(KEYS_TEMPLATE_SUFFIX)
        ]
        if len(keys_matches) != 1:
            print(
                f"{wheel}: expected one {KEYS_TEMPLATE_SUFFIX}, "
                f"found {len(keys_matches)}",
                file=sys.stderr,
            )
            return 1
        keys_template = yaml.safe_load(archive.read(keys_matches[0])) or {}
        if not isinstance(keys_template, dict) or "official" not in keys_template:
            print(
                f"{wheel}: {KEYS_TEMPLATE_SUFFIX} is not a keys template",
                file=sys.stderr,
            )
            return 1
        skill_matches = [
            name for name in archive.namelist() if name.endswith(SKILL_SUFFIX)
        ]
        if len(skill_matches) != 1:
            print(
                f"{wheel}: expected one {SKILL_SUFFIX}, found {len(skill_matches)}",
                file=sys.stderr,
            )
            return 1
        caps_matches = [
            name for name in archive.namelist() if name.endswith(SKILL_CAPS_SUFFIX)
        ]
        if len(caps_matches) != 1:
            print(
                f"{wheel}: expected one {SKILL_CAPS_SUFFIX}, "
                f"found {len(caps_matches)}",
                file=sys.stderr,
            )
            return 1

    channels = {
        str(name): (spec or {}) for name, spec in (data.get("channels") or {}).items()
    }
    planned = sorted(
        name
        for name, spec in channels.items()
        if str(spec.get("level", "optional")) == "planned"
    )
    if planned:
        print(
            f"{wheel}: planned channels are no longer supported: {', '.join(planned)}",
            file=sys.stderr,
        )
        return 1
    visible = sorted(channels)

    if len(visible) != EXPECTED_VISIBLE:
        print(
            f"{wheel}: {len(visible)} visible channels, expected {EXPECTED_VISIBLE}: "
            f"{visible}",
            file=sys.stderr,
        )
        return 1

    print(
        f"{wheel}: {len(visible)} visible channels + keys template + skill packaged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
