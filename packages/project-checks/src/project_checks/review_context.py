from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from project_checks import change_impact, repo_context

# Default target for --project-dir when the flag is omitted.
DEFAULT_PROJECT_DIR = Path.cwd()

# Maximum number of entries rendered in each bounded section.
MAX_SECTION_ENTRIES = 20

# Maximum length of one-line task and overview text before rendering.
MAX_OVERVIEW_LENGTH = 160

# Maximum number of task front matter lines read from a planning file.
MAX_FRONT_MATTER_LINES = 200


def _bounded_entries(value: object) -> dict[str, Any]:
	"""Cap a list-like section to MAX_SECTION_ENTRIES and report the omitted count."""
	entries = list(value) if isinstance(value, (list, tuple)) else []
	omitted = max(0, len(entries) - MAX_SECTION_ENTRIES)

	return {
		"items": entries[:MAX_SECTION_ENTRIES],
		"omitted": omitted,
	}


def _one_line(value: object) -> str:
	"""Collapse whitespace and truncate a value to MAX_OVERVIEW_LENGTH characters."""
	line = " ".join(str(value or "").split())
	if len(line) <= MAX_OVERVIEW_LENGTH:
		return line

	return f"{line[: MAX_OVERVIEW_LENGTH - 3].rstrip()}..."


def _read_front_matter(path: Path) -> dict[str, str]:
	"""Parse a task file's leading `---` front matter into flat key-value fields."""
	fields: dict[str, str] = {}
	lines: list[str] = []

	with path.open(encoding="utf-8") as task_file:
		for line in task_file:
			lines.append(line.rstrip("\n"))
			if len(lines) > MAX_FRONT_MATTER_LINES:
				raise ValueError("task front matter is too long")
			if len(lines) > 1 and lines[-1].strip() == "---":
				break

	if not lines or lines[0].strip() != "---" or lines[-1].strip() != "---":
		raise ValueError("task front matter is missing")

	for line in lines[1:-1]:
		if not line.strip():
			continue
		if line[:1].isspace() or ":" not in line:
			raise ValueError("task front matter must use flat key-value lines")

		key, value = line.split(":", 1)
		key = key.strip()
		if not key:
			raise ValueError("task front matter contains an empty key")
		fields[key] = value.strip()

	if not fields.get("title"):
		raise ValueError("task front matter has no title")

	return fields


def _planning_files(project_dir: Path) -> list[Path]:
	"""List a project's task planning files in deterministic order."""
	task_directory = project_dir / ".agent" / "tasks"
	if not task_directory.is_dir():
		return []

	return sorted(task_directory.rglob("*.md"))


def _progress_task(project_dir: Path) -> tuple[dict[str, Any] | None, str]:
	"""Run `progress next --json` and return the active task with its resolution state."""
	try:
		completed = subprocess.run(
			["progress", "next", "--json"],
			cwd=project_dir,
			text=True,
			stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL,
			check=False,
			timeout=10,
		)
	except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
		return None, "unavailable"

	if completed.returncode != 0:
		return None, "broken"

	try:
		envelope = json.loads(completed.stdout)
	except json.JSONDecodeError:
		return None, "broken"

	if not isinstance(envelope, dict) or envelope.get("ok") is not True:
		return None, "broken"

	data = envelope.get("data")
	if not isinstance(data, dict):
		return None, "broken"

	task = data.get("task")
	if task is None:
		return None, "missing"
	if not isinstance(task, dict):
		return None, "broken"

	return task, "present"


def _task_summary(
	task: dict[str, Any], resolution: str, fields: dict[str, str] | None = None
) -> dict[str, Any]:
	"""Build the compact active-task summary shape shared by every resolution path."""
	front_matter = fields or {}
	overview = front_matter.get("overview") or task.get("overview")
	release = front_matter.get("release") or task.get("release_id")
	position = front_matter.get("position") or task.get("position")

	return {
		"status": resolution,
		"id": task.get("id"),
		"slug": task.get("slug"),
		"title": task.get("title") or front_matter.get("title", ""),
		"release": release,
		"position": position,
		"overview": _one_line(overview),
	}


def _relative_path(project_dir: Path, path: Path) -> str:
	"""Render a path relative to the project directory, falling back to its absolute form."""
	try:
		return path.relative_to(project_dir).as_posix()
	except ValueError:
		return path.as_posix()


def _resolve_from_task_file(project_dir: Path, task: dict[str, Any]) -> dict[str, Any]:
	"""Resolve the active task's planning file by slug, falling back to a title match."""
	files = _planning_files(project_dir)
	slug = str(task.get("slug", "")).strip()
	expected = project_dir / ".agent" / "tasks" / f"{slug}.md" if slug else None

	if expected is not None and expected.exists():
		try:
			fields = _read_front_matter(expected)
		except (OSError, ValueError) as error:
			result = _task_summary(task, "broken")
			result["path"] = _relative_path(project_dir, expected)
			result["reason"] = str(error)
			return result

		result = _task_summary(task, "present", fields)
		result["path"] = _relative_path(project_dir, expected)
		return result

	title = str(task.get("title", "")).strip()
	matches: list[tuple[Path, dict[str, str]]] = []
	for path in files:
		try:
			fields = _read_front_matter(path)
		except (OSError, ValueError):
			continue
		if fields.get("title", "").strip() == title:
			matches.append((path, fields))

	if len(matches) > 1:
		result = _task_summary(task, "ambiguous")
		result["candidates"] = [
			_relative_path(project_dir, path) for path, _fields in matches
		]
		return result

	if matches:
		path, fields = matches[0]
		result = _task_summary(task, "present", fields)
		result["path"] = _relative_path(project_dir, path)
		return result

	result = _task_summary(task, "missing")
	if expected is not None:
		result["path"] = _relative_path(project_dir, expected)
	return result


def _resolve_from_ignored_files(project_dir: Path) -> dict[str, Any] | None:
	"""Resolve the ignored planning file marked in-progress: ambiguous for multiple matches, None for none."""
	matches: list[tuple[Path, dict[str, str]]] = []
	for path in _planning_files(project_dir):
		try:
			fields = _read_front_matter(path)
		except (OSError, ValueError):
			continue
		if fields.get("status") == "in-progress":
			matches.append((path, fields))

	if len(matches) > 1:
		result = _task_summary({}, "ambiguous")
		result["candidates"] = [
			_relative_path(project_dir, path) for path, _fields in matches
		]
		return result

	if not matches:
		return None

	path, fields = matches[0]
	result = _task_summary(
		{
			"slug": path.stem,
			"title": fields.get("title", ""),
		},
		"present",
		fields,
	)
	result["path"] = _relative_path(project_dir, path)
	return result


def _resolve_active_task(project_dir: Path) -> dict[str, Any]:
	"""Resolve the active task summary, falling back to ignored planning files when progress is unavailable."""
	task, state = _progress_task(project_dir)
	if state == "present" and task is not None:
		return _resolve_from_task_file(project_dir, task)

	if state == "unavailable":
		fallback = _resolve_from_ignored_files(project_dir)
		if fallback is not None:
			return fallback

	return _task_summary({}, state)


def _diagnostics_summary(impact_report: dict[str, Any]) -> dict[str, Any]:
	"""Report change-impact's suggested-check evidence, or 'unknown' when none exists."""
	evidence = impact_report.get("suggested_checks")
	if not isinstance(evidence, list) or not evidence:
		evidence = "unknown"

	return {"evidence": evidence}


def build_review_context(project_dir: Path) -> dict[str, Any]:
	"""Compose repository and change-impact context into one unbounded review context."""
	project_dir = Path(project_dir)
	repository = repo_context.build_context(project_dir)
	impact = change_impact.build_report(project_dir)

	return {
		"project_dir": str(project_dir),
		"source": repository.get("source", ""),
		"active_task": _resolve_active_task(project_dir),
		"workspace": repository.get("workspace", {}),
		"summary": repository.get("summary", {}),
		"git": repository.get("git", {}),
		"generated_paths": repository.get("generated_paths", []),
		"generators": repository.get("generators", []),
		"changed_count": impact.get("changed_count", 0),
		"changed": impact.get("changed", []),
		"groups": impact.get("groups", {}),
		"guard": impact.get("guard", {}),
		"ok": impact.get("ok"),
		"risks": impact.get("risks", []),
		"diagnostics": _diagnostics_summary(impact),
		"suggested_checks": impact.get("suggested_checks", []),
		"verification_gaps": impact.get("verification_gaps", []),
	}


def _bounded_groups(groups: object) -> dict[str, dict[str, Any]]:
	"""Cap each impact group's entries, ordered by change_impact's known category order."""
	if not isinstance(groups, dict):
		return {}

	known_order = list(change_impact.CATEGORY_ORDER)
	unknown_order = sorted(set(groups) - set(known_order))
	ordered_categories = known_order + unknown_order

	return {
		category: _bounded_entries(groups[category])
		for category in ordered_categories
		if category in groups
	}


def _bounded_diagnostics(value: object) -> dict[str, Any]:
	"""Cap a list-shaped diagnostics evidence value the same way as other bounded sections."""
	if not isinstance(value, dict):
		return {"evidence": "unknown"}

	result: dict[str, Any] = {
		"evidence": value.get("evidence", "unknown"),
	}
	if isinstance(result["evidence"], list):
		result["evidence"] = _bounded_entries(result["evidence"])

	return result


def _render_data(context: dict[str, Any]) -> dict[str, Any]:
	"""Apply section capping to an unbounded review context before rendering."""
	return {
		"project_dir": context.get("project_dir", ""),
		"source": context.get("source", ""),
		"active_task": context.get("active_task", {}),
		"workspace": context.get("workspace", {}),
		"summary": context.get("summary", {}),
		"git": context.get("git", {}),
		"generated_paths": _bounded_entries(context.get("generated_paths", [])),
		"generators": _bounded_entries(context.get("generators", [])),
		"changed_count": context.get("changed_count", 0),
		"changed": _bounded_entries(context.get("changed", [])),
		"groups": _bounded_groups(context.get("groups", {})),
		"guard": context.get("guard", {}),
		"ok": context.get("ok"),
		"risks": _bounded_entries(context.get("risks", [])),
		"diagnostics": _bounded_diagnostics(context.get("diagnostics", {})),
		"suggested_checks": _bounded_entries(context.get("suggested_checks", [])),
		"verification_gaps": _bounded_entries(context.get("verification_gaps", [])),
	}


def _render_items(section: dict[str, Any], formatter: Any) -> list[str]:
	"""Render a bounded section's items with a formatter, appending an omitted-count line."""
	lines = [formatter(item) for item in section["items"]]
	if section["omitted"]:
		lines.append(f"- +{section['omitted']} omitted")

	return lines


def render_markdown(context: dict[str, Any]) -> str:
	"""Render the bounded review context as fixed-order Markdown."""
	data = _render_data(context)
	active_task = data["active_task"]
	git = data["git"]
	summary = data["summary"]
	lines = [
		"# Review context",
		"",
		f"- Project: `{data['project_dir']}`",
		f"- Source: {data['source'] or 'unknown'}",
		"",
		"## Active task",
		"",
	]

	if active_task.get("status") in {"present", "missing", "broken", "ambiguous"}:
		lines.extend(
			[
				f"- Status: {active_task['status']}",
				f"- Title: {active_task.get('title') or 'unknown'}",
				f"- Release: {active_task.get('release') or 'unknown'}",
				f"- Position: {active_task.get('position') or 'unknown'}",
				f"- Overview: {active_task.get('overview') or 'unknown'}",
			]
		)
	else:
		lines.append(f"- Status: {active_task.get('status', 'unknown')}")

	lines.extend(["", "## Repository", ""])
	lines.extend(
		[
			f"- Workspace: {data['workspace'].get('path') or 'not detected'}",
			f"- Primary stack: {summary.get('primary_stack', 'unknown')}",
			f"- Package manager: {summary.get('package_manager', 'unknown')}",
			f"- Script runner: {summary.get('script_runner', 'unknown')}",
		]
	)

	lines.extend(["", "## Git", ""])
	changed = git.get("changed", {}) if isinstance(git, dict) else {}
	changed_summary = (
		", ".join(f"{count} {name}" for name, count in sorted(changed.items()))
		or "clean"
	)
	lines.extend(
		[
			f"- Available: {git.get('available', False)}",
			f"- Branch: {git.get('branch', 'unknown')}",
			f"- Ahead/behind: {git.get('ahead', 0)}/{git.get('behind', 0)}",
			f"- Changed: {changed_summary}",
		]
	)

	lines.extend(["", "## Changed files", ""])
	lines.extend(
		_render_items(
			data["changed"],
			lambda item: (
				f"- {item.get('status', '??')}: `{item.get('path', '')}` ({item.get('category', 'unknown')})"
			),
		)
		or ["- None detected."]
	)

	lines.extend(["", "## Impact groups", ""])
	if data["groups"]:
		for category, section in data["groups"].items():
			lines.append(f"- {category}: {len(section['items'])} shown")
			if section["omitted"]:
				lines.append(f"  - +{section['omitted']} omitted")
	else:
		lines.append("- None detected.")

	lines.extend(["", "## Generated output", ""])
	lines.extend(
		_render_items(data["generated_paths"], lambda item: f"- `{item}`")
		or ["- None detected."]
	)

	lines.extend(["", "## Diagnostics", ""])
	evidence = data["diagnostics"].get("evidence", "unknown")
	if isinstance(evidence, dict):
		lines.extend(_render_items(evidence, lambda item: f"- `{item}`"))
	else:
		lines.append(f"- Evidence: {evidence}")

	lines.extend(["", "## Risks", ""])
	lines.extend(
		_render_items(
			data["risks"],
			lambda item: (
				f"- {item.get('severity', 'unknown')}: {item.get('message', 'unknown')}"
			),
		)
		or ["- None detected."]
	)

	lines.extend(["", "## Verification", ""])
	lines.extend(
		_render_items(data["verification_gaps"], lambda item: f"- Gap: {item}")
		or ["- No gaps reported."]
	)
	lines.extend(
		_render_items(data["suggested_checks"], lambda item: f"- Check: `{item}`")
		or ["- No relevant checks reported."]
	)

	return "\n".join(lines)


def render_json(context: dict[str, Any]) -> str:
	"""Render the bounded review context as fixed-order JSON."""
	return json.dumps(_render_data(context), ensure_ascii=False, indent=2)


def main() -> None:
	"""Parse CLI arguments and print the bounded review context."""
	parser = argparse.ArgumentParser(
		description="Print bounded project context for a focused review."
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

	context = build_review_context(args.project_dir.resolve())
	if args.json:
		print(render_json(context))
	else:
		print(render_markdown(context))


if __name__ == "__main__":
	main()
