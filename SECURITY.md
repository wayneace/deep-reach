# Security Policy

Deep-Reach is a local, tiered internet access layer. It can read and write; write actions must be declared in the channel action and confirmed by the user. P3 `bsk` runs in the user's real browser profile and can perform writes.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub Security Advisories:

https://github.com/wayneace/deep-reach/security/advisories/new

Do not open a public issue for a vulnerability.

## In scope

- URL handling in `web read` / `http-read`: scheme allowlist, private-address blocking and redirect validation.
- Write-capability declaration: write actions must be explicit in the action definition and must require user confirmation.
- P3 bsk guard: direct fetch/XHR to site internal APIs, `debug replay`, and network calls inside `evaluate` are blocked; other bsk capabilities, including writes, are allowed.
- Key handling: `~/.deep-reach/keys.yaml` is local and never committed; POSIX writes through `profile set` are tightened to `0600`.
- State files: only error codes and timestamps are stored; queries, results, cookies and keys are never written.

## Known boundaries

- `DEEP_REACH_ALLOW_PRIVATE_URLS=1` is an explicit opt-in. When set, private URLs may be read and may be sent to a configured P2 reader.
- DNS rebinding and transparent-proxy DNS rewriting remain residual risks because validation happens before the request.
- Live smoke tests contact public platforms; never put secrets in query strings.
