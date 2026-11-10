"""Live smoke test for Deep-Reach default channels.

Run from the project directory:

    uv run python scripts/smoke.py

Optional channels (login) are skipped unless --include-optional is passed.
"""

from __future__ import annotations

import argparse
import sys

from deep_reach.backends.ebay import register_ebay_backend
from deep_reach.backends.epo import register_epo_backend
from deep_reach.backends.etsy import register_etsy_backend
from deep_reach.backends.github import register_github_backend
from deep_reach.backends.http import register_http_backends
from deep_reach.backends.jina import register_jina_backend
from deep_reach.backends.opencli import OpenCLIClient, register_opencli_backends
from deep_reach.backends.producthunt import register_producthunt_backend
from deep_reach.backends.public import register_public_backends
from deep_reach.backends.uspto import register_uspto_backend
from deep_reach.backends.v2ex import register_v2ex_backend
from deep_reach.runtime.browser_config import normalize_opencli_profile
from deep_reach.backends.xueqiu import register_xueqiu_backends
from deep_reach.channels import load_registry
from deep_reach.runtime.dispatch import run_action
from deep_reach.runtime.keys import Keys

CASES = [
    ("bilibili", "search", {"query": "收纳", "limit": 2}),
    ("youtube", "search", {"query": "desk organizer", "limit": 2}),
    ("weibo", "hot", {"limit": 2}),
    ("xueqiu", "quote", {"target": "SH600519"}),
    ("amazon", "search", {"query": "desk organizer", "limit": 2}),
    ("web", "read", {"target": "https://example.com"}),
    ("github", "search", {"query": "desk organizer", "limit": 2}),
    ("v2ex", "hot", {"limit": 2}),
]

OPTIONAL_CASES = [
    ("x", "search", {"query": "AI", "limit": 2}),
    ("reddit", "search", {"query": "desk", "limit": 2}),
    ("xiaohongshu", "search", {"query": "收纳", "limit": 2}),
    ("zhihu", "search", {"query": "收纳", "limit": 2}),
    ("douyin", "search", {"query": "收纳", "limit": 2}),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-optional", action="store_true")
    args = parser.parse_args()

    registry = load_registry()
    keys = Keys.load()
    profile = normalize_opencli_profile(keys.get("browser.opencli_profile"))
    register_opencli_backends(OpenCLIClient(profile=profile))
    register_jina_backend(keys)
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

    cases = list(CASES)
    if args.include_optional:
        cases.extend(OPTIONAL_CASES)

    failures = 0
    for channel_name, action, params in cases:
        channel = registry.get(channel_name)
        if channel is None:
            print(f"{channel_name}/{action}: MISSING CHANNEL")
            failures += 1
            continue
        env = run_action(channel, action, params, keys=keys, timeout=60)
        code = env["error"]["code"] if env["error"] else "-"
        print(
            f"{channel_name}/{action}: ok={env['ok']} "
            f"tier={env.get('tier')} backend={env.get('backend')} "
            f"code={code} items={len(env['items'])}"
        )
        if not env["ok"]:
            failures += 1
            print(f"   {env['error']['message'][:200]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
