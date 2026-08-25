import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest
from project_checks import change_impact, repo_context, review_context


def _repository_context(git: dict[str, object]) -> dict[str, object]:
	return {
		"source": "WORKSPACE.md",
		"workspace": {"exists": True, "path": "WORKSPACE.md"},
		"summary": {"primary_stack": "Python"},
		"git": git,
		"generated_paths": ["dist"],
		"generators": [],
	}


def _impact_report() -> dict[str, object]:
	return {
		"changed_count": 1,
		"changed": [{"status": " M", "path": "src/example.py", "category": "source"}],
		"groups": {"source": ["src/example.py"]},
		"guard": {"available": True, "findings": [], "ok": True},
		"ok": True,
		"risks": [],
		"suggested_checks": ["pytest tests/test_example.py"],
		"verification_gaps": [],
	}


def _patch_composition(monkeypatch: pytest.MonkeyPatch, git: dict[str, object]) -> None:
	monkeypatch.setattr(
		repo_context, "build_context", lambda _project_dir: _repository_context(git)
	)
	monkeypatch.setattr(
		change_impact, "build_report", lambda _project_dir: _impact_report()
	)
	monkeypatch.setattr(
		change_impact,
		"diagnostics",
		mock.Mock(side_effect=AssertionError("diagnostics discovery was duplicated")),
	)
	monkeypatch.setattr(
		review_context,
		"_resolve_active_task",
		lambda _project_dir: {
			"status": "missing",
			"id": None,
			"slug": None,
			"title": "",
			"release": None,
			"position": None,
			"overview": "",
		},
	)


@pytest.mark.parametrize(
	"git_state",
	[
		{"available": True, "changed": {"added": 1}, "total_changed": 1},
		{"available": True, "changed": {"modified": 1}, "total_changed": 1},
		{"available": True, "changed": {"untracked": 1}, "total_changed": 1},
		{"available": True, "changed": {"other": 1}, "total_changed": 1},
		{"available": True, "changed": {}, "total_changed": 0},
		{
			"available": True,
			"branch": "No commits yet on main",
			"changed": {},
			"total_changed": 0,
		},
		{
			"available": False,
			"branch": "Not a Git repo",
			"changed": {},
			"total_changed": 0,
		},
		{
			"available": False,
			"branch": "Git command failed",
			"changed": {},
			"total_changed": 0,
		},
	],
)
def test_build_review_context_preserves_existing_git_shape(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	git_state: dict[str, object],
) -> None:
	_patch_composition(monkeypatch, git_state)

	context = review_context.build_review_context(tmp_path)

	assert context["git"] == git_state


def test_build_review_context_reports_unknown_diagnostics_without_evidence(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	_patch_composition(monkeypatch, {"available": True, "changed": {}})
	monkeypatch.setattr(
		change_impact,
		"build_report",
		lambda _project_dir: {**_impact_report(), "suggested_checks": []},
	)

	context = review_context.build_review_context(tmp_path)

	assert context["diagnostics"] == {"evidence": "unknown"}


def test_active_task_reads_ignored_planning_file_and_limits_summary(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	task_path = tmp_path / ".agent" / "tasks" / "current-task.md"
	task_path.parent.mkdir(parents=True)
	(tmp_path / ".gitignore").write_text(".agent/tasks/\n", encoding="utf-8")
	long_overview = (
		"An overview that is deliberately longer than the compact review context limit. "
		* 4
	)
	task_path.write_text(
		f"---\ntitle: Current task\noverview: {long_overview}\nstatus: in-progress\nrelease: phase-5\n---\n\n## Contract\n\nDo not include this source.\n",
		encoding="utf-8",
	)
	envelope = {
		"ok": True,
		"data": {
			"task": {
				"id": "tsk_current",
				"slug": "current-task",
				"title": "Current task",
				"overview": long_overview,
				"release_id": "rel_phase-5",
				"position": 2,
			},
		},
	}
	monkeypatch.setattr(
		review_context.subprocess,
		"run",
		lambda *args, **kwargs: subprocess.CompletedProcess(
			args, 0, json.dumps(envelope), ""
		),
	)

	active_task = review_context._resolve_active_task(tmp_path)

	assert active_task["status"] == "present"
	assert active_task["path"] == ".agent/tasks/current-task.md"
	assert active_task["release"] == "phase-5"
	assert active_task["position"] == 2
	assert len(active_task["overview"]) <= review_context.MAX_OVERVIEW_LENGTH
	assert "Do not include this source" not in json.dumps(active_task)


def test_active_task_uses_ignored_file_when_progress_is_unavailable(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	task_path = tmp_path / ".agent" / "tasks" / "current-task.md"
	task_path.parent.mkdir(parents=True)
	(tmp_path / ".gitignore").write_text(".agent/tasks/\n", encoding="utf-8")
	task_path.write_text(
		"---\ntitle: Current task\noverview: Use the ignored planning file\nstatus: in-progress\n---\n",
		encoding="utf-8",
	)
	monkeypatch.setattr(
		review_context.subprocess,
		"run",
		mock.Mock(side_effect=FileNotFoundError),
	)

	active_task = review_context._resolve_active_task(tmp_path)

	assert active_task["status"] == "present"
	assert active_task["path"] == ".agent/tasks/current-task.md"


@pytest.mark.parametrize(
	"file_body, expected_status",
	[
		("not front matter", "broken"),
		("", "broken"),
	],
)
def test_active_task_reports_broken_planning_file(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	file_body: str,
	expected_status: str,
) -> None:
	task_path = tmp_path / ".agent" / "tasks" / "current-task.md"
	task_path.parent.mkdir(parents=True)
	task_path.write_text(file_body, encoding="utf-8")
	envelope = {
		"ok": True,
		"data": {
			"task": {"slug": "current-task", "title": "Current task"},
		},
	}
	monkeypatch.setattr(
		review_context.subprocess,
		"run",
		lambda *args, **kwargs: subprocess.CompletedProcess(
			args, 0, json.dumps(envelope), ""
		),
	)

	assert review_context._resolve_active_task(tmp_path)["status"] == expected_status


def test_active_task_reports_ambiguous_title_matches(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	task_directory = tmp_path / ".agent" / "tasks"
	task_directory.mkdir(parents=True)
	for name in ("first.md", "second.md"):
		(task_directory / name).write_text(
			"---\ntitle: Current task\noverview: Short\nstatus: ready\n---\n",
			encoding="utf-8",
		)
	envelope = {
		"ok": True,
		"data": {
			"task": {"slug": "missing-slug", "title": "Current task"},
		},
	}
	monkeypatch.setattr(
		review_context.subprocess,
		"run",
		lambda *args, **kwargs: subprocess.CompletedProcess(
			args, 0, json.dumps(envelope), ""
		),
	)

	active_task = review_context._resolve_active_task(tmp_path)

	assert active_task["status"] == "ambiguous"
	assert active_task["candidates"] == [
		".agent/tasks/first.md",
		".agent/tasks/second.md",
	]


def test_active_task_reports_ambiguous_ignored_files_when_progress_is_unavailable(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	task_directory = tmp_path / ".agent" / "tasks"
	task_directory.mkdir(parents=True)
	for name in ("first.md", "second.md"):
		(task_directory / name).write_text(
			"---\ntitle: Current task\noverview: Short\nstatus: in-progress\n---\n",
			encoding="utf-8",
		)
	monkeypatch.setattr(
		review_context.subprocess,
		"run",
		mock.Mock(side_effect=FileNotFoundError),
	)

	active_task = review_context._resolve_active_task(tmp_path)

	assert active_task["status"] == "ambiguous"
	assert active_task["candidates"] == [
		".agent/tasks/first.md",
		".agent/tasks/second.md",
	]


def test_renderers_cap_sections_and_repeat_deterministically() -> None:
	changed = [
		{"status": " M", "path": f"src/file-{index}.py", "category": "source"}
		for index in range(25)
	]
	context = {
		"project_dir": "/tmp/project",
		"source": "WORKSPACE.md",
		"active_task": {"status": "missing"},
		"workspace": {"exists": True, "path": "WORKSPACE.md"},
		"summary": {},
		"git": {"available": True, "changed": {"modified": 25}},
		"generated_paths": [],
		"generators": [],
		"changed_count": 25,
		"changed": changed,
		"groups": {"source": [item["path"] for item in changed]},
		"guard": {},
		"ok": True,
		"risks": [],
		"diagnostics": {"evidence": "unknown"},
		"suggested_checks": [],
		"verification_gaps": [],
	}

	json_output = review_context.render_json(context)
	json_data = json.loads(json_output)
	markdown_output = review_context.render_markdown(context)

	assert json_output == review_context.render_json(context)
	assert markdown_output == review_context.render_markdown(context)
	assert len(json_data["changed"]["items"]) == 20
	assert json_data["changed"]["omitted"] == 5
	assert len(json_data["groups"]["source"]["items"]) == 20
	assert "+5 omitted" in markdown_output
