# Contributing

## Development

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run python scripts/smoke.py   # live, optional
```

## Before a pull request

- `uv run pytest -q`
- `uv run ruff check .`
- `uv build --wheel && uv run python scripts/check_wheel.py`
- Add a test for every behavior change; unit tests must stay offline.
- Do not commit keys, cookies, state files or generated `dist/` output.

## Design rules

- Deep-Reach is read-only: never add post/comment/like/DM actions.
- Backends are ordered P0 → P1 → P2 by the registry; do not bypass the order.
- A visible channel must have actions, `requires`, tiers, limits/not_supported and a capability note.
- P0/P1/P2 failures follow `FINAL_CODES` / `RETRYABLE_CODES`; do not add ad-hoc fallback rules.
