#!/usr/bin/env python3
# Check that file paths claimed in agent-facing markdown actually exist on disk.
#
# Modes:
#   paths    — relative markdown links and inline code paths in agent instruction files
#   commands — inline `scripts/` references across all markdown, verifying executability

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_PROJECT_DIR = Path.cwd()
# Configuration and directory names that apply to every project scanned.
DEFAULT_CONFIG_FILENAME = "markdown-claims.config.json"
MARKDOWN_SCAN_IGNORE_DIRS = frozenset(
	{
		".cache",
		".git",
		".mypy_cache",
		".next",
		".nuxt",
		".pytest_cache",
		".ruff_cache",
		".tox",
		".venv",
		"__pycache__",
		"coverage",
		"htmlcov",
		"node_modules",
		"vendor",
	}
)

# Inline code prefixes that are commonly repo-root-relative across projects.
DEFAULT_REPO_PATH_PREFIXES = (
	"scripts/",
	"docs/",
	"tests/",
	"templates/",
	"hooks/",
	"adapters/",
)

RE_MD_LINK = re.compile(r"\[(?:[^\]]*)\]\(([^)#\s][^)]*)\)")
RE_INLINE_CODE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
RE_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)


@dataclass
class Issue:
	file: str  # repo-relative path of the markdown file
	claim: str  # the path string as written in the source
	kind: str  # missing_path | missing_script | not_executable


def collect_files(
	project_dir: Path,
	ignore_dirs: frozenset[str] = MARKDOWN_SCAN_IGNORE_DIRS,
) -> list[Path]:
	"""Collect Markdown files while omitting generated and dependency trees."""
	project_dir = project_dir.resolve()

	return sorted(
		path
		for path in project_dir.rglob("*.md")
		if not any(part in ignore_dirs for part in path.relative_to(project_dir).parts)
	)


def strip_fences(text: str) -> str:
	return RE_CODE_FENCE.sub("", text)


# Returns (claim_text, resolved_path) pairs for relative markdown links.
#
# @param  {str}   text
#     Markdown source with fences already stripped.
# @param  {Path}  source_file
#     Absolute path of the file being scanned; used to resolve relative targets.
def extract_link_claims(text: str, source_file: Path) -> list[tuple[str, Path]]:
	claims = []
	for m in RE_MD_LINK.finditer(text):
		target = m.group(1).strip()
		if target.startswith(("http://", "https://", "#", "mailto:", "/")):
			continue
		resolved = (source_file.parent / target).resolve()
		claims.append((target, resolved))
	return claims


# Returns (claim_text, resolved_path) pairs for inline code matching prefixes.
# Paths are resolved from the repo root. Trailing arguments are stripped so
# `scripts/foo.sh --flag` resolves to scripts/foo.sh.
#
# @param  {str}        text
#     Markdown source with fences already stripped.
# @param  {Path}       project_dir
#     Project directory used to resolve repo-root-relative paths.
# @param  {tuple[str]} prefixes
#     Only inline code starting with one of these prefixes is included.
def extract_code_claims(
	text: str,
	project_dir: Path,
	prefixes: tuple[str, ...],
) -> list[tuple[str, Path]]:
	claims = []
	for m in RE_INLINE_CODE.finditer(text):
		code = m.group(1).strip()
		if not code.startswith(prefixes):
			continue
		path_part = code.split()[0].rstrip("/")
		if "<" in path_part:
			continue
		resolved = project_dir / path_part
		claims.append((path_part, resolved))
	return claims


def _load_config(config_path: Path) -> dict[str, object]:
	if not config_path.exists():
		return {}

	try:
		config = json.loads(config_path.read_text(encoding="utf-8"))
	except json.JSONDecodeError as error:
		raise ValueError(
			f"Invalid JSON in Markdown claims configuration: {error}"
		) from error

	if not isinstance(config, dict):
		raise ValueError("Markdown claims configuration must contain a JSON object.")

	return config


def _load_config_strings(config_path: Path, key: str) -> list[str]:
	config = _load_config(config_path)
	values = config.get(key, [])
	if not isinstance(values, list) or not all(
		isinstance(value, str) for value in values
	):
		raise ValueError(
			f"Markdown claims configuration '{key}' must be an array of strings."
		)

	return values


def load_path_prefixes(config_path: Path) -> tuple[str, ...]:
	"""Load optional project-specific inline-code path prefixes."""
	extra_prefixes = _load_config_strings(config_path, "extraPathPrefixes")
	return DEFAULT_REPO_PATH_PREFIXES + tuple(extra_prefixes)


def load_ignore_dirs(config_path: Path) -> frozenset[str]:
	"""Load optional project-specific Markdown scan ignore directories."""
	extra_ignore_dirs = _load_config_strings(config_path, "extraIgnoreDirs")
	return MARKDOWN_SCAN_IGNORE_DIRS | frozenset(extra_ignore_dirs)


# Checks relative path claims in agent instruction files.
# Returns one Issue per missing path.
def check_paths(
	project_dir: Path,
	prefixes: tuple[str, ...] = DEFAULT_REPO_PATH_PREFIXES,
	ignore_dirs: frozenset[str] = MARKDOWN_SCAN_IGNORE_DIRS,
) -> list[Issue]:
	project_dir = project_dir.resolve()
	files = collect_files(project_dir, ignore_dirs)
	issues = []

	for md_file in files:
		text = strip_fences(md_file.read_text(encoding="utf-8"))
		rel = str(md_file.relative_to(project_dir))

		link_claims = extract_link_claims(text, md_file)
		code_claims = extract_code_claims(text, project_dir, prefixes)

		for claim, resolved in link_claims + code_claims:
			if not resolved.exists():
				issues.append(Issue(file=rel, claim=claim, kind="missing_path"))

	return issues


# Checks that scripts/ references in markdown exist and are executable.
# Returns one Issue per missing or non-executable script.
def check_commands(
	project_dir: Path,
	ignore_dirs: frozenset[str] = MARKDOWN_SCAN_IGNORE_DIRS,
) -> list[Issue]:
	project_dir = project_dir.resolve()
	files = collect_files(project_dir, ignore_dirs)
	issues = []

	for md_file in files:
		text = strip_fences(md_file.read_text(encoding="utf-8"))
		rel = str(md_file.relative_to(project_dir))

		for claim, resolved in extract_code_claims(
			text,
			project_dir,
			("scripts/",),
		):
			if not resolved.exists():
				issues.append(Issue(file=rel, claim=claim, kind="missing_script"))
			elif not resolved.stat().st_mode & 0o111:
				issues.append(Issue(file=rel, claim=claim, kind="not_executable"))

	return issues


def _print_issues(issues: list[Issue]) -> None:
	for issue in issues:
		if issue.kind == "missing_path":
			print(f"  {issue.file}: missing path '{issue.claim}'")
		elif issue.kind == "missing_script":
			print(f"  {issue.file}: missing script '{issue.claim}'")
		elif issue.kind == "not_executable":
			print(f"  {issue.file}: script not executable '{issue.claim}'")


def main(arguments: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--project-dir",
		type=Path,
		default=DEFAULT_PROJECT_DIR,
		help="Project directory to inspect.",
	)
	parser.add_argument(
		"--config",
		type=Path,
		default=None,
		metavar="PATH",
		help=(
			"Path to Markdown claims configuration. Defaults to "
			f"<project-dir>/{DEFAULT_CONFIG_FILENAME}."
		),
	)
	parser.add_argument(
		"--mode",
		choices=["paths", "commands", "all"],
		default="all",
		help="Which claims to check (default: all)",
	)
	parser.add_argument(
		"--json",
		action="store_true",
		help="Output findings as JSON",
	)
	args = parser.parse_args(arguments)
	project_dir = args.project_dir.resolve()
	config_path = args.config or project_dir / DEFAULT_CONFIG_FILENAME

	try:
		path_prefixes = load_path_prefixes(config_path)
		ignore_dirs = load_ignore_dirs(config_path)
	except ValueError as error:
		parser.error(str(error))

	issues: list[Issue] = []

	if args.mode in ("paths", "all"):
		issues.extend(check_paths(project_dir, path_prefixes, ignore_dirs))

	if args.mode in ("commands", "all"):
		issues.extend(check_commands(project_dir, ignore_dirs))

	if args.json:
		print(json.dumps({"issues": [asdict(i) for i in issues]}, indent=2))
	else:
		_print_issues(issues)
		if issues:
			print(f"\n  {len(issues)} issue(s) found")

	if issues:
		sys.exit(1)


if __name__ == "__main__":
	main()
