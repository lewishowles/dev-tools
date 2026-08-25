#!/usr/bin/env python3
# Check that file paths claimed in agent-facing markdown actually exist on disk.
#
# Paths include relative Markdown links and inline code paths in agent instruction files.

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from project_checks import style

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
RE_CODE_FENCE = re.compile(
	r"(?P<fence>`{3,})(?P<language>[^\n`]*)\n(?P<body>.*?)(?P=fence)",
	re.DOTALL,
)
RE_CLAIM_MARKER = re.compile(r"<!--\s*markdown-claims:\s*(planned|historical)\s*-->")
RE_SOURCE_LOCATION = re.compile(r"^(?P<path>.+?):\d+(?::\d+)?$")
NON_CURRENT_MARKERS = frozenset({"historical", "planned"})


@dataclass
class Issue:
	"""Record one missing Markdown path claim.

	Attributes:
		file: Repository-relative path of the Markdown file.
		claim: Path string as written in the source.
		kind: Issue kind, currently ``missing_path``.
	"""

	file: str
	claim: str
	kind: str


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
	"""Remove fenced code blocks before scanning Markdown claims."""
	return RE_CODE_FENCE.sub("", text)


def extract_markers(line: str) -> frozenset[str]:
	"""Return Markdown claim markers declared on one source line."""
	return frozenset(RE_CLAIM_MARKER.findall(line))


def is_non_current(markers: frozenset[str]) -> bool:
	"""Return whether a line describes planned or historical repository state."""
	return bool(markers & NON_CURRENT_MARKERS)


def normalise_path_reference(path: str) -> str:
	"""Remove an optional source line and column suffix from a path."""
	match = RE_SOURCE_LOCATION.fullmatch(path)
	if match is None:
		return path

	return match.group("path")


def resolve_claim_matches(path: Path) -> list[Path]:
	"""Return concrete paths matching a literal path or glob claim."""
	path_text = str(path)
	if not glob.has_magic(path_text):
		return [path] if path.exists() else []

	return sorted(Path(match) for match in glob.glob(path_text, recursive=True))


def extract_link_claims(text: str, source_file: Path) -> list[tuple[str, Path]]:
	"""Extract relative Markdown link claims and their resolved paths.

	Args:
		text: Markdown source with fences already stripped.
		source_file: Absolute path of the file being scanned, used to resolve
			relative targets.

	Returns:
		Pairs containing each claimed target and its resolved path.
	"""
	claims = []
	for line in text.splitlines():
		if is_non_current(extract_markers(line)):
			continue

		for match in RE_MD_LINK.finditer(line):
			target = match.group(1).strip()
			if target.startswith(("http://", "https://", "#", "mailto:", "/")):
				continue
			path_target = target.split("#", maxsplit=1)[0]
			path_target = normalise_path_reference(path_target)
			resolved = (source_file.parent / path_target).resolve()
			claims.append((target, resolved))
	return claims


def extract_inline_path_claims(
	text: str,
	project_dir: Path,
	prefixes: tuple[str, ...],
) -> list[tuple[str, Path]]:
	"""Extract current inline-code path claims and their resolved paths.

	Inline claims may include command arguments; only the path token is resolved.

	Args:
		text: Markdown source to scan.
		project_dir: Project directory used to resolve repo-root-relative paths.
		prefixes: Prefixes that identify inline-code path claims.

	Returns:
		Pairs containing each claimed path and its resolved path.
	"""
	claims = []
	for line in strip_fences(text).splitlines():
		markers = extract_markers(line)
		if is_non_current(markers):
			continue

		for match in RE_INLINE_CODE.finditer(line):
			code = match.group(1).strip()
			if not code.startswith(prefixes):
				continue
			claim = code.split()[0].rstrip("/")
			if "<" in claim:
				continue
			path_part = normalise_path_reference(claim)
			resolved = project_dir / path_part
			claims.append((claim, resolved))
	return claims


def _load_config(config_path: Path) -> dict[str, object]:
	"""Read optional JSON configuration and return its mapping.

	Return an empty mapping when the file is absent and raise ``ValueError`` for
	invalid JSON or a non-object configuration.
	"""
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
	"""Read one configured key as a list of strings.

	Return an empty list when the key is absent and raise ``ValueError`` when its
	value is not a list of strings.
	"""
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


def check_paths(
	project_dir: Path,
	prefixes: tuple[str, ...] = DEFAULT_REPO_PATH_PREFIXES,
	ignore_dirs: frozenset[str] = MARKDOWN_SCAN_IGNORE_DIRS,
) -> list[Issue]:
	"""Find missing relative path claims in project Markdown files."""
	project_dir = project_dir.resolve()
	files = collect_files(project_dir, ignore_dirs)
	issues = []

	for md_file in files:
		text = strip_fences(md_file.read_text(encoding="utf-8"))
		rel = str(md_file.relative_to(project_dir))

		link_claims = extract_link_claims(text, md_file)
		code_claims = extract_inline_path_claims(text, project_dir, prefixes)

		for claim, resolved in link_claims + code_claims:
			if not resolve_claim_matches(resolved):
				issues.append(Issue(file=rel, claim=claim, kind="missing_path"))

	return issues


def _print_issues(issues: list[Issue]) -> None:
	"""Print each issue using the CLI-styled row format."""
	for issue in issues:
		print(style.row(issue.file, f"missing path '{issue.claim}'", "failed"))


def main(arguments: list[str] | None = None) -> None:
	"""Run the Markdown claims checker and fail when issues are found."""
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
		choices=["paths"],
		default="paths",
		help="Path checks to run (default: paths)",
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

	issues = check_paths(project_dir, path_prefixes, ignore_dirs)

	if args.json:
		print(json.dumps({"issues": [asdict(i) for i in issues]}, indent=2))
	else:
		_print_issues(issues)
		if issues:
			print()
			print(style.status("failed", detail=f"{len(issues)} issue(s) found"))

	if issues:
		sys.exit(1)


if __name__ == "__main__":
	main()
