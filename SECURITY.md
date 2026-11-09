# Security Policy

Deep-Reach is a local, read-only internet access layer. It does not post, comment, like, follow or send direct messages.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub Security Advisories:

https://github.com/wayneace/deep-reach/security/advisories/new

Do not open a public issue for a vulnerability.

## In scope

- URL handling in `web read` / `http-read`: scheme allowlist, private-address blocking and redirect validation.
- Read-only enforcement in the OpenCLI backend.
- Key handling: `~/.deep-reach/keys.yaml` is local and never committed; POSIX writes through `profile set` are tightened to `0600`.
- State files: only error codes and timestamps are stored; queries, results, cookies and keys are never written.

## Known boundaries

- `DEEP_REACH_ALLOW_PRIVATE_URLS=1` is an explicit opt-in. When set, private URLs may be read and may be sent to a configured P2 reader.
- DNS rebinding and transparent-proxy DNS rewriting remain residual risks because validation happens before the request.
- Live smoke tests contact public platforms; never put secrets in query strings.
