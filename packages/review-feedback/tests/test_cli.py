from pathlib import Path
import json
import subprocess

import pytest

from review_feedback import cli
from review_feedback.draft import resolve_store


def git(repo: Path, *arguments: str) -> str:
	result = subprocess.run(
		["git", *arguments],
		cwd=repo,
		check=True,
		capture_output=True,
		text=True,
	)
	return result.stdout


def make_repo(tmp_path: Path) -> Path:
	repo = tmp_path / "repo"
	repo.mkdir()
	git(repo, "init", "--quiet")
	git(repo, "config", "user.email", "tests@example.com")
	git(repo, "config", "user.name", "Tests")
	(repo / "review.txt").write_text("before\nold selection\nafter\n", encoding="utf-8")
	git(repo, "add", ".")
	git(repo, "commit", "--quiet", "-m", "initial")
	return repo


def prepare_selection(repo: Path) -> None:
	(repo / "review.txt").write_text("before\nnew selection\nafter\n", encoding="utf-8")


def add_entry(
	repo: Path,
	monkeypatch: pytest.MonkeyPatch,
	comment: str = "Review this line",
) -> None:
	monkeypatch.chdir(repo)
	monkeypatch.setattr(cli, "read_clipboard", lambda: "new selection")
	monkeypatch.setattr("builtins.input", lambda _: comment)
	assert cli.main(["add"]) == 0


def test_commands_outside_a_worktree_fail_without_creating_state(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
	monkeypatch.chdir(tmp_path)

	result = cli.main(["show"])

	assert result == 2
	assert "Git worktree" in capsys.readouterr().err
	assert list(tmp_path.iterdir()) == []


def test_add_and_show_json_store_locations_without_source_excerpts(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	repo = make_repo(tmp_path)
	prepare_selection(repo)
	add_entry(repo, monkeypatch, "Needs a smaller boundary")
	capsys.readouterr()

	assert cli.main(["show", "--json"]) == 0
	show_output = json.loads(capsys.readouterr().out)
	entry = show_output["entries"][0]

	assert entry["number"] == 1
	assert entry["path"] == "review.txt"
	assert entry["side"] == "current"
	assert entry["start_line"] == 2
	assert entry["start_column"] == 1
	assert entry["end_line"] == 2
	assert entry["end_column"] == 14
	assert entry["comment"] == "Needs a smaller boundary"
	assert entry["selection_hash"]
	assert entry["repository_fingerprint"]
	assert "new selection" not in json.dumps(entry)


def test_remove_keeps_remaining_entry_numbers_stable(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	repo = make_repo(tmp_path)
	prepare_selection(repo)
	add_entry(repo, monkeypatch, "First")
	add_entry(repo, monkeypatch, "Second")
	capsys.readouterr()

	assert cli.main(["remove", "1"]) == 0
	assert cli.main(["show", "--json"]) == 0
	output = capsys.readouterr().out
	show_output = json.loads(output[output.index("{") :])

	assert [entry["number"] for entry in show_output["entries"]] == [2]


def test_preview_copy_failure_leaves_the_active_draft_unchanged(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	repo = make_repo(tmp_path)
	prepare_selection(repo)
	add_entry(repo, monkeypatch)
	store = resolve_store(repo)
	before = store.active_path.read_bytes()
	monkeypatch.setattr(
		cli,
		"copy_to_clipboard",
		lambda text: (_ for _ in ()).throw(cli.ClipboardError("copy failed")),
	)
	monkeypatch.chdir(repo)

	assert cli.main(["preview", "--copy"]) == 2

	assert store.active_path.read_bytes() == before
	assert "copy failed" in capsys.readouterr().err


def test_clear_retires_an_abandoned_draft_without_a_packet(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	repo = make_repo(tmp_path)
	prepare_selection(repo)
	add_entry(repo, monkeypatch)
	trash_root = tmp_path / "Trash"
	monkeypatch.setattr("review_feedback.draft._trash_root", lambda: trash_root)
	monkeypatch.chdir(repo)
	capsys.readouterr()

	assert cli.main(["clear"]) == 0

	assert not resolve_store(repo).active_path.exists()
	assert list(trash_root.glob("*.json"))
	assert "Review feedback" not in capsys.readouterr().out


def test_stale_preview_preserves_the_draft_and_identifies_the_entry(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	repo = make_repo(tmp_path)
	prepare_selection(repo)
	add_entry(repo, monkeypatch)
	store = resolve_store(repo)
	before = store.active_path.read_bytes()
	(repo / "review.txt").write_text(
		"before\nreplaced selection\nafter\n", encoding="utf-8"
	)
	monkeypatch.chdir(repo)

	assert cli.main(["preview"]) == 2

	assert store.active_path.read_bytes() == before
	assert "entry 1" in capsys.readouterr().err


def test_finish_retires_the_draft_and_next_add_starts_at_one(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	repo = make_repo(tmp_path)
	prepare_selection(repo)
	add_entry(repo, monkeypatch)
	monkeypatch.setattr(cli, "copy_to_clipboard", lambda text: None)
	trash_root = tmp_path / "Trash"
	monkeypatch.setattr("review_feedback.draft._trash_root", lambda: trash_root)
	monkeypatch.chdir(repo)

	assert cli.main(["finish", "--copy"]) == 0
	finish_output = capsys.readouterr().out
	store = resolve_store(repo)

	assert "# Review feedback" in finish_output
	assert not store.active_path.exists()
	assert list(trash_root.glob("*.json"))

	add_entry(repo, monkeypatch, "New review")
	assert store.active_path.read_text(encoding="utf-8").count('"number": 1') == 1
