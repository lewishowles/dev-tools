#!/usr/bin/env python3
# Detect generated-file edits and stale generated output from Git status.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PROJECT_DIR = Path.cwd()

COMMON_GENERATED_PATHS = [
	"dist",
	"dist-docs",
	"build",
	"coverage",
	"test-results",
	"playwright-report",
]

CONFIG_REPO_RULES = [
	{
		"generated": ["dist/claude/CLAUDE.md"],
		"sources": ["rules/", "dist/claude/source/header.md"],
		"label": "Claude global instructions",
	},
	{
		"generated": ["dist/codex/AGENTS.md"],
		"sources": ["rules/", "dist/codex/source/"],
		"label": "Codex global instructions",
	},
	{
		"generated": ["dist/claude/settings.json"],
		"sources": ["adapters/claude/settings.base.json", "hooks/claude/"],
		"label": "Claude settings",
	},
	{
		"generated": ["dist/claude/.mcp.json"],
		"sources": ["adapters/claude/mcp.json"],
		"label": "Claude MCP config",
	},
	{
		"generated": ["dist/codex/hooks.json"],
		"sources": ["adapters/codex/hooks.json"],
		"label": "Codex hooks config",
	},
	{
		"generated": ["dist/claude/source/global-skills.md"],
		"sources": ["scripts/build/build-skill-mds.py"],
		"label": "Claude skill index",
	},
	{
		"generated": ["dist/skills/"],
		"sources": ["skills/", "scripts/build/build-skill-mds.py"],
		"label": "runtime skills",
	},
	{
		"generated": ["dist/chatgpt/"],
		"sources": ["dist/chatgpt/source/", "scripts/build/build-chatgpt-target.py"],
		"label": "ChatGPT target",
	},
	{
		"generated": [
			"docs/agents.md",
			"docs/commands.md",
			"docs/hooks.md",
			"docs/plugins.md",
			"docs/skills.md",
		],
		"sources": ["scripts/build/build-docs.py"],
		"label": "generated docs tables",
	},
]


@dataclass
class Finding:
	code: str
	message: str
	path: str
	source: str


def workspace_body(project_dir: Path) -> str:
	path = project_dir / "WORKSPACE.md"
	if not path.exists():
		path = project_dir / "AGENT_CAPABILITIES.md"
	if not path.exists():
		return ""

	return path.read_text()


def section_lines(body: str, heading: str) -> list[str]:
	lines = body.splitlines()
	start = None

	for index, line in enumerate(lines):
		if line == heading:
			start = index + 1
			break

	if start is None:
		return []

	result = []
	for line in lines[start:]:
		if line.startswith("## "):
			break
		result.append(line)

	return result


def generated_paths_from_workspace(project_dir: Path) -> list[str]:
	body = workspace_body(project_dir)
	paths = []

	for line in section_lines(body, "## Generated or build output"):
		if line.startswith("- `") and line.endswith("`"):
			paths.append(line[3:-1])

	return paths


def git_status(project_dir: Path) -> list[str]:
	completed = subprocess.run(
		["git", "status", "--porcelain=v1"],
		cwd=project_dir,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.DEVNULL,
		check=False,
	)

	if completed.returncode != 0:
		return []

	return completed.stdout.splitlines()


def changed_paths(project_dir: Path) -> list[str]:
	paths = []

	for line in git_status(project_dir):
		path = line[3:]
		if " -> " in path:
			_, path = path.split(" -> ", 1)
		paths.append(path)

	return sorted(set(paths))


def is_path_match(path: str, pattern: str) -> bool:
	if pattern.endswith("/"):
		return path.startswith(pattern)

	return path == pattern or path.startswith(f"{pattern}/")


def any_changed(changed: list[str], patterns: list[str]) -> bool:
	return any(is_path_match(path, pattern) for path in changed for pattern in patterns)


def generated_exists(project_dir: Path, patterns: list[str]) -> bool:
	for pattern in patterns:
		path = project_dir / pattern.rstrip("/")
		if path.exists():
			return True

	return False


def source_hint(sources: list[str]) -> str:
	return ", ".join(f"`{source}`" for source in sources)


def config_repo_rules(project_dir: Path) -> list[dict[str, Any]]:
	if not (project_dir / "scripts" / "sync.sh").exists():
		return []
	if not (project_dir / "rules").exists():
		return []
	if not (project_dir / "dist" / "claude").exists():
		return []

	skill_manifests = [
		str(skill_json.relative_to(project_dir))
		for skill_json in sorted((project_dir / "skills").glob("*/*/skill.json"))
	]
	hook_manifests = [
		str(hook_json.relative_to(project_dir))
		for hook_json in sorted((project_dir / "hooks" / "claude").glob("*/hook.json"))
	]

	rules = []
	for rule in CONFIG_REPO_RULES:
		rule_copy = dict(rule)
		if rule["label"] == "Claude skill index":
			rule_copy["sources"] = rule["sources"] + skill_manifests
		elif rule["label"] == "generated docs tables":
			rule_copy["sources"] = rule["sources"] + skill_manifests + hook_manifests
		rules.append(rule_copy)

	for hook_script in sorted((project_dir / "hooks" / "claude").glob("*/*.sh")):
		rules.append(
			{
				"generated": [f"dist/claude/hooks/{hook_script.name}"],
				"sources": [
					str(hook_script.relative_to(project_dir)),
					str(hook_script.with_name("hook.json").relative_to(project_dir)),
				],
				"label": f"Claude hook {hook_script.name}",
			}
		)

	return rules


def generic_generated_paths(project_dir: Path) -> list[str]:
	return sorted(
		set(
			generated_paths_from_workspace(project_dir)
			+ [path for path in COMMON_GENERATED_PATHS if (project_dir / path).exists()]
		)
	)


def generic_source_changed(path: str) -> bool:
	return not any(
		is_path_match(path, generated) for generated in COMMON_GENERATED_PATHS
	)


def guard(project_dir: Path) -> dict[str, Any]:
	changed = changed_paths(project_dir)
	findings: list[Finding] = []
	rule_generated = []

	for rule in config_repo_rules(project_dir):
		generated = rule["generated"]
		sources = rule["sources"]
		if not generated_exists(project_dir, generated):
			continue

		rule_generated.extend(generated)

		generated_changed = any_changed(changed, generated)
		source_changed = any_changed(changed, sources)

		if generated_changed and not source_changed:
			for path in changed:
				if any(is_path_match(path, pattern) for pattern in generated):
					findings.append(
						Finding(
							code="generated-edited",
							message=f"{rule['label']} generated output changed without its source.",
							path=path,
							source=source_hint(sources),
						)
					)

		if source_changed and not generated_changed:
			findings.append(
				Finding(
					code="generated-stale",
					message=f"{rule['label']} source changed but generated output is not changed.",
					path=", ".join(generated),
					source="Run `scripts/sync.sh`.",
				)
			)

	for generated in generic_generated_paths(project_dir):
		for path in changed:
			if not is_path_match(path, generated):
				continue
			if any(is_path_match(path, pattern) for pattern in rule_generated):
				continue
			if any(generic_source_changed(changed_path) for changed_path in changed):
				continue

			findings.append(
				Finding(
					code="generated-only-change",
					message="Generated output changed without any source change.",
					path=path,
					source="Edit source files and regenerate output.",
				)
			)

	return {
		"changed": changed,
		"findings": [finding.__dict__ for finding in findings],
		"ok": not findings,
		"project_dir": str(project_dir),
	}


def render_markdown(result: dict[str, Any]) -> str:
	lines = ["# Generated file guard", ""]

	if result["ok"]:
		lines.append("No generated-file issues detected.")
		return "\n".join(lines)

	lines.extend(["Findings:", ""])
	for finding in result["findings"]:
		lines.extend(
			[
				f"- `{finding['path']}`: {finding['message']}",
				f"  Source: {finding['source']}",
			]
		)

	return "\n".join(lines)


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Detect generated-file edits and stale generated output."
	)
	parser.add_argument(
		"--project-dir",
		type=Path,
		default=DEFAULT_PROJECT_DIR,
		help="Project directory to inspect.",
	)
	parser.add_argument(
		"--json", action="store_true", help="Print machine-readable JSON."
	)
	args = parser.parse_args()

	project_dir = args.project_dir.resolve()
	if not project_dir.is_dir():
		print(f"Project directory not found: {project_dir}", file=sys.stderr)
		sys.exit(2)

	result = guard(project_dir)
	if args.json:
		print(json.dumps(result, indent=2, sort_keys=True))
	else:
		print(render_markdown(result))

	if not result["ok"]:
		sys.exit(1)


if __name__ == "__main__":
	main()
