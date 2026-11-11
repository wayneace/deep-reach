# Setup as a deployment entry

Date: 2026-11-11
Status: proposed

## Intent

`deep-reach setup` currently prints a diagnostic table. It should instead be the
first-run deployment entry: tell the user exactly what will be written, ask for
permission, create the private keys file from the packaged template, and leave a
clear, client-neutral install prompt for OpenCLI. `deep-reach doctor` remains the
diagnostic command.

## Goals

- `setup` creates `~/.deep-reach/` (0700 on POSIX) and
  `~/.deep-reach/keys.yaml` (0600) from the packaged template when missing.
- Existing keys files are never overwritten; permissions are tightened by the
  existing `secure_paths` helpers.
- Before any write, `setup` lists every path and action and asks for approval.
- `--dry-run` prints the plan without changing anything. `--yes` skips the
  prompt for scripted/agent use. A non-interactive run without `--yes` makes no
  changes and exits non-zero.
- After deployment, `setup` reports:
  - files created/kept, their paths and modes;
  - empty key entries and what each unlocks;
  - the dedicated-profile steps and the Chrome Web Store extension URL;
  - that `deep-reach doctor` is the diagnostic command.
- `setup` never launches Chrome.

## OpenCLI installation

`setup` does **not** execute an installer. It prints a client-neutral instruction:

> Install OpenCLI with your agent client's package manager. For example, Cherry
> Studio manages CLIs itself (`cli_install`, recipe `npm:@jackwener/opencli`);
> a plain environment can use `npm install -g @jackwener/opencli@2.0.3`.

The agent reading the output chooses the install route for its own client. This
keeps Cherry's managed toolchain authoritative and avoids hard-coding a
package manager that may not exist. The same client-neutral wording is used by
`doctor`, `update`, and OpenCLI-missing errors so an agent is never told to run
`npm -g` inside a managed client by mistake.

## Non-goals

- Installing OpenCLI automatically, or detecting a specific agent client.
- Launching Chrome or binding a profile automatically.
- Writing any key values.
- Migrating or rewriting an existing keys file.
- Replacing `doctor` diagnostics.

## Flow

1. Build a plan: keys path, parent directory, whether each exists, OpenCLI
   version if available, and the file actions.
2. Print the plan and the OpenCLI install prompt.
3. If `--dry-run`, stop.
4. If file actions exist, ask `Proceed with file setup? [y/N]`. Decline or EOF
   makes no changes and exits 2.
5. Apply: create the parent private directory, then write the template with an
   atomic temp file + replace, mode 0600, only if the target is missing.
6. Print the deployment summary, empty-key checklist, and next steps.

If the existing keys file cannot be parsed, `setup` reports the error and does
not overwrite it.

## Security

- Directory 0700, file 0600 on POSIX; existing ownership/symlink rules from
  `runtime/secure_paths.py` apply.
- No key value is printed; only key names and descriptions.
- Errors are redacted through the existing result helpers.
- The template contains no secrets.

## Files touched

- `deep_reach/runtime/setup.py` (new): plan, key notes, apply, formatting.
- `deep_reach/cli.py`: rewrite `cmd_setup`, add `--dry-run` / `--yes`.
- `deep_reach/runtime/availability.py`, `runtime/doctor.py`,
  `backends/opencli.py`: client-neutral install wording.
- `tests/test_setup.py` (new), `tests/test_cli_channels.py` (update setup tests).
- `README.md`, `skill/SKILL.md`, `CHANGELOG.md`.

## Test plan

- Missing keys file: plan shows create; `--yes` creates 0700/0600 and template
  content.
- Existing keys file: no overwrite, content preserved; summary says kept.
- `--dry-run`: no filesystem changes.
- Declined prompt / non-interactive without `--yes`: no filesystem changes,
  exit 2.
- Invalid YAML: no overwrite, exit 2.
- Summary lists empty keys and the extension URL; never prints values.
- OpenCLI install prompt contains the client-neutral wording, not a hard-coded
  npm-only command.
- All existing tests pass.
