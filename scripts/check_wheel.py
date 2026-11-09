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

    channels = {
        str(name): (spec or {}) for name, spec in (data.get("channels") or {}).items()
    }
    visible = sorted(
        name
        for name, spec in channels.items()
        if str(spec.get("level", "optional")) != "planned"
    )
    planned = sorted(set(channels) - set(visible))

    if len(visible) != EXPECTED_VISIBLE:
        print(
            f"{wheel}: {len(visible)} visible channels, expected {EXPECTED_VISIBLE}: "
            f"{visible}",
            file=sys.stderr,
        )
        return 1

    print(
        f"{wheel}: {len(visible)} visible + {len(planned)} planned channels packaged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
