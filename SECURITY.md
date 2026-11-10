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
- Key handling: `~/.deep-reach/keys.yaml` is local and never committed. On POSIX, reads and writes tighten it to `0600` and `~/.deep-reach` to `0700`. The dedicated Chrome profile directory is also `0700`.
- Child processes: OpenCLI, bsk, Chrome, npm and helper subprocesses receive a filtered environment with no `DEEP_REACH_*` variables and no credential-looking names.
- Output: known key values are redacted from `ReachError`, JSON output, `--text` summaries and `doctor` text. YAML parse errors report only line/column, never the offending content.
- Redirects: cross-origin redirects strip `Authorization`, `Cookie`, `X-API-Key`, `X-Subscription-Token`, `X-Goog-Api-Key` and similar credential headers/query parameters. Jina and Xueqiu use the same validated opener.
- Browser profile: P1 OpenCLI runs only against an explicitly bound dedicated Chrome profile. `auto`, empty, or malformed settings mean P1 is not runnable; Deep-Reach never falls back to the first connected profile.
- State files: only error codes and timestamps are stored; queries, results, cookies and keys are never written.

## Known boundaries

- `DEEP_REACH_ALLOW_PRIVATE_URLS=1` is an explicit opt-in. When set, private URLs may be read and may be sent to a configured P2 reader.
- DNS rebinding and transparent-proxy DNS rewriting remain residual risks because validation happens before the request.
- Keys are not encrypted at rest. The boundary is file permissions plus the OS account; use a separate OS account on a shared machine.
- Browser Bridge has no true headless mode. `OPENCLI_WINDOW=background` avoids a foreground window, but the dedicated Chrome profile must be running with the extension.
- bsk still uses the current browser profile by design; only OpenCLI is isolated to the dedicated profile.
- Live smoke tests contact public platforms; never put secrets in query strings.
