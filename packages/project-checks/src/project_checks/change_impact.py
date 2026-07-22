#!/usr/bin/env python3
# Summarise Git change categories, risk signals, and focused verification hints.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PROJECT_DIR = Path.cwd()

CATEGORY_LABELS = {
	"config": "Config",
	"docs": "Docs",
	"generated": "Generated",
	"scripts": "Scripts",
	"skills": "Skills",
	"source": "Source",
	"templates": "Templates",
	"tests": "Tests",
	"other": "Other",
}

CATEGORY_ORDER = [
	"source",
	"tests",
	"skills",
	"scripts",
	"config",
	"templates",
	"docs",
	"generated",
	"other",
]

GENERATED_PATHS = [
	"dist/",
	"dist-docs/",
	"build/",
	"coverage/",
	"test-results/",
	"playwright-report/",
	"docs/agents.md",
	"docs/commands.md",
	"docs/hooks.md",
	"docs/plugins.md",
	"docs/skills.md",
]

CONFIG_FILENAMES = {
	".editorconfig",
	".eslintrc",
	".gitignore",
	".prettierrc",
	"AGENTS.md",
	"AGENT_CAPABILITIES.md",
	"WORKSPACE.md",
	"package.json",
	"pyproject.toml",
	"tsconfig.json",
}

DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt"}
SOURCE_EXTENSIONS = {
	".css",
	".go",
	".html",
	".js",
	".jsx",
	".py",
	".rb",
	".swift",
	".ts",
	".tsx",
	".vue",
}
TEST_MARKERS = ["/test/", "/tests/", "/__tests__/", ".test.", ".spec.", "_test."]


@dataclass
class ChangedPath:
	status: str
	path: str
	category: str


@dataclass
class RiskSignal:
	code: str
	message: str
	path: str
	severity: str


def command_output(command: list[str], project_dir: Path) -> tuple[int, str]:
	completed = subprocess.run(
		command,
		cwd=project_dir,
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.DEVNULL,
		check=False,
	)

	return completed.returncode, completed.stdout


def git_status(project_dir: Path) -> list[str]:
	exit_code, output = command_output(["git", "status", "--porcelain=v1"], project_dir)
	if exit_code != 0:
		return []

	return output.splitlines()


def changed_paths(project_dir: Path) -> list[ChangedPath]:
	changed = []

	for line in git_status(project_dir):
		status = line[:2]
		path = line[3:]
		if " -> " in path:
			_, path = path.split(" -> ", 1)
		changed.append(
			ChangedPath(status=status, path=path, category=classify_path(path))
		)

	return sorted(changed, key=lambda item: item.path)


def is_path_match(path: str, pattern: str) -> bool:
	if pattern.endswith("/"):
		return path.startswith(pattern)

	return path == pattern or path.startswith(f"{pattern}/")


def classify_path(path: str) -> str:
	path_object = Path(path)
	name = path_object.name
	suffix = path_object.suffix

	if any(is_path_match(path, pattern) for pattern in GENERATED_PATHS):
		return "generated"
	if path.startswith("tests/") or any(
		marker in f"/{path}" for marker in TEST_MARKERS
	):
		return "tests"
	if path.startswith("skills/"):
		return "skills"
	if path.startswith("scripts/") or path.startswith("hooks/") or suffix in {".sh"}:
		return "scripts"
	if path.startswith("templates/"):
		return "templates"
	if (
		name in CONFIG_FILENAMES
		or path.startswith("adapters/")
		or path.startswith("rules/")
	):
		return "config"
	if path.startswith("docs/") or suffix in DOC_EXTENSIONS:
		return "docs"
	if (
		path.startswith(("src/", "app/", "lib/", "packages/"))
		or suffix in SOURCE_EXTENSIONS
	):
		return "source"

	return "other"


def group_changed(changed: list[ChangedPath]) -> dict[str, list[str]]:
	grouped = {category: [] for category in CATEGORY_ORDER}

	for item in changed:
		grouped.setdefault(item.category, []).append(item.path)

	return {category: paths for category, paths in grouped.items() if paths}


def script_candidates(project_dir: Path, script_name: str) -> list[Path]:
	return [
		Path(__file__).resolve().with_name(script_name),
		project_dir / ".agent" / "scripts" / script_name,
		project_dir / "scripts" / script_name,
	]


def existing_script(project_dir: Path, script_name: str) -> Path | None:
	for path in script_candidates(project_dir, script_name):
		if path.exists():
			return path

	return None


def generated_guard(project_dir: Path) -> dict[str, Any]:
	try:
		from project_checks.generated_file_guard import guard
	except ModuleNotFoundError as error:
		if error.name != "project_checks":
			return {"available": False, "findings": [], "ok": False}

		source_root = str(Path(__file__).resolve().parents[1])
		if source_root not in sys.path:
			sys.path.insert(0, source_root)

		try:
			from project_checks.generated_file_guard import guard
		except (ImportError, OSError):
			return {"available": False, "findings": [], "ok": False}
	except (ImportError, OSError):
		return {"available": False, "findings": [], "ok": False}

	try:
		result = guard(project_dir)
	except (OSError, ValueError):
		return {"available": False, "findings": [], "ok": False}

	result["available"] = True
	return result


def diagnostics(project_dir: Path) -> dict[str, Any]:
	script = existing_script(project_dir, "project-diagnostics.py")
	if not script:
		return {"available": False, "checks": []}

	exit_code, output = command_output(
		[str(script), "--project", str(project_dir), "--json", "--list"], project_dir
	)
	if exit_code != 0:
		return {"available": False, "checks": []}

	try:
		result = json.loads(output)
	except json.JSONDecodeError:
		return {"available": False, "checks": []}

	result["available"] = True
	return result


def risk_signals(
	grouped: dict[str, list[str]], guard_result: dict[str, Any]
) -> list[RiskSignal]:
	signals = []

	for finding in guard_result.get("findings", []):
		signals.append(
			RiskSignal(
				code=finding.get("code", "generated-risk"),
				message=finding.get("message", "Generated output needs review."),
				path=finding.get("path", ""),
				severity="high",
			)
		)

	if "scripts" in grouped:
		signals.append(
			RiskSignal(
				code="scripts-changed",
				message="Script changes can affect setup, validation, or generated output.",
				path=", ".join(grouped["scripts"]),
				severity="medium",
			)
		)

	if "config" in grouped:
		signals.append(
			RiskSignal(
				code="config-changed",
				message="Configuration or rule changes can affect agent behaviour.",
				path=", ".join(grouped["config"]),
				severity="medium",
			)
		)

	if "generated" in grouped and not guard_result.get("findings"):
		signals.append(
			RiskSignal(
				code="generated-changed",
				message="Generated output changed; verify it came from the source generator.",
				path=", ".join(grouped["generated"]),
				severity="low",
			)
		)

	return signals


def verification_gaps(
	grouped: dict[str, list[str]], guard_result: dict[str, Any]
) -> list[str]:
	gaps = []
	substantive_categories = {"config", "scripts", "skills", "source", "templates"}

	if substantive_categories.intersection(grouped) and "tests" not in grouped:
		gaps.append(
			"No test files changed alongside source, skill, script, template, or config changes."
		)

	if {"config", "scripts", "source"}.intersection(grouped) and "docs" not in grouped:
		gaps.append("No docs changed alongside source, script, or config changes.")

	if guard_result.get("findings"):
		gaps.append("Generated/source mismatch detected by generated-file guard.")
	elif "generated" in grouped:
		gaps.append("Generated output changed; confirm the generator was run.")

	return gaps


def suggested_checks(
	project_dir: Path, diagnostics_result: dict[str, Any], guard_result: dict[str, Any]
) -> list[str]:
	checks = []

	if guard_result.get("available"):
		checks.append("scripts/validate/generated-file-guard.py")

	if (project_dir / "scripts" / "validate.sh").exists():
		checks.append("bash scripts/validate.sh")

	for check in diagnostics_result.get("checks", []):
		command = check.get("command", [])
		if command:
			checks.append(" ".join(command))

	return checks


def build_report(project_dir: Path) -> dict[str, Any]:
	changed = changed_paths(project_dir)
	grouped = group_changed(changed)
	guard_result = generated_guard(project_dir)
	diagnostics_result = diagnostics(project_dir)
	risks = risk_signals(grouped, guard_result)

	return {
		"changed": [item.__dict__ for item in changed],
		"changed_count": len(changed),
		"groups": grouped,
		"guard": guard_result,
		"ok": not any(risk.severity == "high" for risk in risks),
		"project_dir": str(project_dir),
		"risks": [risk.__dict__ for risk in risks],
		"suggested_checks": suggested_checks(
			project_dir, diagnostics_result, guard_result
		),
		"verification_gaps": verification_gaps(grouped, guard_result),
	}


def render_paths(paths: list[str], limit: int = 4) -> str:
	if len(paths) <= limit:
		return ", ".join(f"`{path}`" for path in paths)

	visible = ", ".join(f"`{path}`" for path in paths[:limit])
	return f"{visible}, +{len(paths) - limit} more"


def render_markdown(report: dict[str, Any]) -> str:
	lines = [
		"# Change impact",
		"",
		f"Project: `{report['project_dir']}`",
		f"Git: {report['changed_count']} changed file(s)",
		"",
		"## Changed files",
		"",
	]

	if report["groups"]:
		lines.extend(["| Category | Count | Paths |", "| --- | ---: | --- |"])
		for category in CATEGORY_ORDER:
			paths = report["groups"].get(category)
			if paths:
				lines.append(
					f"| {CATEGORY_LABELS[category]} | {len(paths)} | {render_paths(paths)} |"
				)
	else:
		lines.append("No changed files detected.")

	lines.extend(["", "## Risk signals", ""])
	if report["risks"]:
		for risk in report["risks"]:
			path = f" `{risk['path']}`:" if risk["path"] else ""
			lines.append(
				f"- {risk['severity']}: {path} {risk['message']}".replace(":  ", ": ")
			)
	else:
		lines.append("- None detected.")

	lines.extend(["", "## Verification gaps", ""])
	if report["verification_gaps"]:
		lines.extend(f"- {gap}" for gap in report["verification_gaps"])
	else:
		lines.append("- None detected.")

	lines.extend(["", "## Suggested checks", ""])
	if report["suggested_checks"]:
		lines.extend(f"- `{check}`" for check in report["suggested_checks"])
	else:
		lines.append("- No local checks discovered.")

	return "\n".join(lines)


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Summarise local change impact from Git status."
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
	report = build_report(project_dir)

	if args.json:
		print(json.dumps(report, indent=2, sort_keys=True))
	else:
		print(render_markdown(report))

	if not report["ok"]:
		sys.exit(1)


if __name__ == "__main__":
	main()
