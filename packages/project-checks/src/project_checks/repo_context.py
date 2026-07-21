#!/usr/bin/env python3
# Print a compact repo briefing for session startup.
#
# This complements WORKSPACE.md. Workspace and safety facts stay in that file;
# this command lifts the most useful startup facts and adds
# current Git state without printing diffs or file contents.

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_PROJECT_DIR = Path.cwd()

SUMMARY_FIELDS = {
	"Agent rules": "agent_rules",
	"Main source directories": "source_dirs",
	"Package manager": "package_manager",
	"Primary stack": "primary_stack",
	"Progress files": "progress_files",
	"Runtime requirements": "runtime_requirements",
	"Script runner": "script_runner",
}

GENERATED_PATH_NAMES = [
	"dist",
	"dist-docs",
	"build",
	"coverage",
	"test-results",
	"playwright-report",
]

PACKAGE_MANAGERS = [
	("bun.lockb", "Bun"),
	("bun.lock", "Bun"),
	("pnpm-lock.yaml", "pnpm"),
	("yarn.lock", "Yarn"),
	("package-lock.json", "npm"),
]

STATUS_GROUPS = {
	"??": "untracked",
	"A": "added",
	"C": "copied",
	"D": "deleted",
	"M": "modified",
	"R": "renamed",
}


def workspace_path(project_dir: Path) -> Path:
	path = project_dir / "WORKSPACE.md"
	if path.exists():
		return path
	return project_dir / "AGENT_CAPABILITIES.md"


def read_workspace(project_dir: Path) -> str:
	path = workspace_path(project_dir)
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


def bullet_value(line: str) -> tuple[str, str] | None:
	if not line.startswith("- ") or ": " not in line:
		return None

	label, value = line[2:].split(": ", 1)
	return label, value


def summary_from_workspace(body: str) -> dict[str, str]:
	summary = {}

	for heading in ["## Repo summary", "## Important paths"]:
		for line in section_lines(body, heading):
			item = bullet_value(line)
			if not item:
				continue

			label, value = item
			key = SUMMARY_FIELDS.get(label)
			if key:
				summary[key] = value

	return summary


def generated_paths_from_workspace(body: str) -> list[str]:
	paths = []

	for line in section_lines(body, "## Generated or build output"):
		if line.startswith("- `") and line.endswith("`"):
			paths.append(line[3:-1])

	return paths


def generators_from_workspace(body: str) -> list[dict[str, str]]:
	generators = []

	for line in section_lines(body, "## Generators"):
		if (
			not line.startswith("| ")
			or line.startswith("| ---")
			or line.startswith("| Name")
		):
			continue

		columns = [column.strip() for column in line.strip("|").split("|")]
		if len(columns) != 3:
			continue

		generators.append(
			{
				"name": columns[0].strip("`"),
				"command": columns[1].strip("`"),
				"notes": columns[2],
			}
		)

	return generators


def detect_package_manager(project_dir: Path) -> str:
	for filename, manager in PACKAGE_MANAGERS:
		if (project_dir / filename).exists():
			return f"{manager} (inferred from `{filename}`)"

	if (project_dir / "package.json").exists():
		return "npm (inferred from `package.json`)"

	return "Not detected"


def inferred_summary(project_dir: Path) -> dict[str, str]:
	progress_files = [
		name
		for name in ["PROGRESS.md", ".claude/PROGRESS.md", ".agents/PROGRESS.md"]
		if (project_dir / name).exists()
	]
	agent_rules = ["AGENTS.md"] if (project_dir / "AGENTS.md").exists() else []

	return {
		"agent_rules": ", ".join(f"`{name}`" for name in agent_rules)
		if agent_rules
		else "Not detected",
		"package_manager": detect_package_manager(project_dir),
		"primary_stack": "Not detected",
		"progress_files": ", ".join(f"`{name}`" for name in progress_files)
		if progress_files
		else "Not detected",
		"runtime_requirements": "Not detected",
		"script_runner": "Not detected",
		"source_dirs": ", ".join(
			f"`{name}`"
			for name in ["src", "app", "lib", "packages"]
			if (project_dir / name).exists()
		)
		or "Not detected",
	}


def inferred_generated_paths(project_dir: Path) -> list[str]:
	return [name for name in GENERATED_PATH_NAMES if (project_dir / name).exists()]


def inferred_generators(project_dir: Path) -> list[dict[str, str]]:
	if not (project_dir / ".boilersuit").exists():
		return []

	return [{"name": "Boilersuit", "command": ".boilersuit", "notes": "inferred"}]


def diagnostics_entry(project_dir: Path) -> str:
	path = project_dir / ".agent" / "scripts" / "project-diagnostics.py"
	if path.exists():
		return ".agent/scripts/project-diagnostics.py --list"

	return "Not detected"


def git_output(project_dir: Path) -> list[str]:
	completed = subprocess.run(
		["git", "status", "--porcelain=v1", "--branch"],
		cwd=project_dir,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.DEVNULL,
		check=False,
	)

	if completed.returncode != 0:
		return []

	return completed.stdout.splitlines()


def parse_branch(line: str) -> dict[str, Any]:
	value = line.removeprefix("## ")
	result: dict[str, Any] = {
		"ahead": 0,
		"behind": 0,
		"branch": value,
		"upstream": "",
	}

	if "..." in value:
		branch, rest = value.split("...", 1)
		result["branch"] = branch
		if " [" in rest:
			upstream, state = rest.split(" [", 1)
			result["upstream"] = upstream
			for item in state.rstrip("]").split(", "):
				if item.startswith("ahead "):
					result["ahead"] = int(item.removeprefix("ahead "))
				if item.startswith("behind "):
					result["behind"] = int(item.removeprefix("behind "))
		else:
			result["upstream"] = rest

	return result


def parse_git_state(project_dir: Path) -> dict[str, Any]:
	lines = git_output(project_dir)
	if not lines:
		return {
			"available": False,
			"ahead": 0,
			"behind": 0,
			"branch": "Not a Git repo",
			"changed": {},
			"total_changed": 0,
			"upstream": "",
		}

	branch = parse_branch(lines[0])
	changed: dict[str, int] = {}

	for line in lines[1:]:
		status = line[:2]
		key = (
			"untracked"
			if status == "??"
			else STATUS_GROUPS.get(status.strip()[:1], "other")
		)
		changed[key] = changed.get(key, 0) + 1

	return {
		"available": True,
		**branch,
		"changed": changed,
		"total_changed": sum(changed.values()),
	}


def build_context(project_dir: Path) -> dict[str, Any]:
	body = read_workspace(project_dir)
	has_workspace = bool(body)
	path = workspace_path(project_dir)

	return {
		"workspace": {
			"exists": has_workspace,
			"path": path.name if has_workspace else "",
		},
		"diagnostics": diagnostics_entry(project_dir),
		"generated_paths": generated_paths_from_workspace(body)
		if has_workspace
		else inferred_generated_paths(project_dir),
		"generators": generators_from_workspace(body)
		if has_workspace
		else inferred_generators(project_dir),
		"git": parse_git_state(project_dir),
		"project_dir": str(project_dir),
		"repo_dir": str(project_dir),
		"source": path.name if has_workspace else "inferred",
		"summary": summary_from_workspace(body)
		if has_workspace
		else inferred_summary(project_dir),
	}


def _drift_score(repo_dir: Path) -> str:
	drift_script = repo_dir / "scripts" / "repo-drift.py"
	if not drift_script.exists():
		return "n/a"
	try:
		result = subprocess.run(
			["python3", str(drift_script), "--json"],
			capture_output=True,
			text=True,
			timeout=10,
			cwd=repo_dir,
		)
		data = json.loads(result.stdout)
		return f"{data['score']}/{data['max']}"
	except Exception:
		return "n/a"


def format_count(label: str, count: int) -> str:
	return f"{count} {label}"


def render_markdown(context: dict[str, Any]) -> str:
	summary = context["summary"]
	git = context["git"]
	changed = git["changed"]
	changed_text = (
		", ".join(
			format_count(label, count) for label, count in sorted(changed.items())
		)
		if changed
		else "clean"
	)
	upstream = f" -> {git['upstream']}" if git.get("upstream") else ""

	lines = [
		"# Repo context",
		"",
		f"- Source: {context['source']}",
		f"- Project: `{context['project_dir']}`",
		f"- Workspace: `{context['workspace']['path']}`"
		if context["workspace"]["exists"]
		else "- Workspace: Not detected",
		f"- Primary stack: {summary.get('primary_stack', 'Not detected')}",
		f"- Package manager: {summary.get('package_manager', 'Not detected')}",
		f"- Script runner: {summary.get('script_runner', 'Not detected')}",
		f"- Runtime requirements: {summary.get('runtime_requirements', 'Not detected')}",
		f"- Source dirs: {summary.get('source_dirs', 'Not detected')}",
		f"- Agent rules: {summary.get('agent_rules', 'Not detected')}",
		f"- Progress files: {summary.get('progress_files', 'Not detected')}",
		f"- Diagnostics: `{context['diagnostics']}`"
		if context["diagnostics"] != "Not detected"
		else "- Diagnostics: Not detected",
		f"- Git: {git['branch']}{upstream}; ahead {git['ahead']}, behind {git['behind']}; {changed_text}",
		f"- Drift score: {_drift_score(Path(context['repo_dir']))}",
		"",
		"## Generated output",
		"",
	]

	if context["generated_paths"]:
		lines.extend(f"- `{path}`" for path in context["generated_paths"])
	else:
		lines.append("- None detected")

	lines.extend(["", "## Generators", ""])

	if context["generators"]:
		for generator in context["generators"]:
			lines.append(f"- {generator['name']}: `{generator['command']}`")
	else:
		lines.append("- None detected")

	return "\n".join(lines)


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Print compact repo context for agent session startup."
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

	context = build_context(args.project_dir.resolve())
	if args.json:
		print(json.dumps(context, indent=2, sort_keys=True))
	else:
		print(render_markdown(context))


if __name__ == "__main__":
	main()
