# project-checks

Runs conservative diagnostics against a project: safe package scripts, Git change-impact summaries, generated-file drift detection, Markdown claims verification, and a compact repo briefing for agent session startup. Built for agent workflows, where a script needs to know what's safe to run without guessing.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Getting started

Install it globally with `uv`:

```bash
uv tool install project-checks
```

To install it into an existing Python environment with `pip`:

```bash
pip install project-checks
```

This installs five commands on your PATH:

- `project-checks`: list or run conservative project diagnostics (package scripts such as lint, typecheck, and test)
- `project-checks-change-impact`: summarise local change impact from Git status
- `project-checks-generated-file-guard`: detect generated-file edits and stale generated output
- `project-checks-markdown-claims`: check that paths and commands claimed in Markdown files actually exist
- `project-checks-repo-context`: print a compact repo briefing for agent session startup

## Usage

```bash
# List available checks without running them
project-checks --list --project ./my-project

# Run one or more checks
project-checks --check lint --check test:unit --project ./my-project

# The other four commands take --project-dir instead of --project
project-checks-change-impact --project-dir ./my-project
project-checks-generated-file-guard --project-dir ./my-project
project-checks-markdown-claims --project-dir ./my-project --mode all
project-checks-repo-context --project-dir ./my-project
```

Add `--json` to any command for machine-readable output.

## Other packages in this workspace

- [dev-tools](../../README.md)
