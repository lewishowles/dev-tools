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

This installs six commands on your PATH:

- `project-checks`: list or run conservative project diagnostics (package scripts such as lint, typecheck, and test)
- `project-checks-change-impact`: summarise local change impact from Git status
- `project-checks-generated-file-guard`: detect generated-file edits and stale generated output
- `project-checks-markdown-claims`: check that current paths named in Markdown files exist
- `project-checks-repo-context`: print a compact repo briefing for agent session startup
- `project-checks-review-context`: print bounded project context for a focused review

## Usage

```bash
# List available checks without running them
project-checks --list --project ./my-project

# Run one or more checks
project-checks --check lint --check test:unit --project ./my-project

# The other five commands take --project-dir instead of --project
project-checks-change-impact --project-dir ./my-project
project-checks-generated-file-guard --project-dir ./my-project
project-checks-markdown-claims --project-dir ./my-project --mode paths
project-checks-repo-context --project-dir ./my-project
project-checks-review-context --project-dir ./my-project
```

Add `--json` to any command for machine-readable output.

`project-checks-markdown-claims` scans Markdown files across the project, skipping
common dependency, cache, coverage, and vendor directories. It also scans `dist`
and `build` unless a project opts into ignoring them. It recognises common
repo-root-relative path prefixes by default. Add project-specific prefixes or
ignore directories in an optional `<project-dir>/markdown-claims.config.json`, or
pass another file with `--config`:

```json
{
	"extraPathPrefixes": ["guides/"],
	"extraIgnoreDirs": ["dist", "build"]
}
```

Path claims include relative Markdown links and inline code that starts with a
configured path prefix. A `:line` or `:line:column` suffix is removed before
resolution. Globs pass when they match at least one current path and fail when
they match nothing.

Planned destinations and removed historical paths can be marked without
weakening checks for current paths. The marker applies to every path on the
same source line:

```markdown
- `scripts/future-check.sh` <!-- markdown-claims: planned -->
- `scripts/removed-check.sh` <!-- markdown-claims: historical -->
```

## Other packages in this workspace

- [dev-tools](../../README.md)
