from pathlib import Path

import pytest

from project_checks import diagnostics
from project_checks.diagnostics import detect_python_checks, has_pytest_test_files


def test_has_pytest_test_files_detects_test_prefixed_file(tmp_path: Path) -> None:
	(tmp_path / "test_example.py").write_text("", encoding="utf-8")

	assert has_pytest_test_files(tmp_path) is True


def test_has_pytest_test_files_detects_test_suffixed_file(tmp_path: Path) -> None:
	(tmp_path / "example_test.py").write_text("", encoding="utf-8")

	assert has_pytest_test_files(tmp_path) is True


def test_has_pytest_test_files_ignores_non_matching_python_files(tmp_path: Path) -> None:
	(tmp_path / "example.py").write_text("", encoding="utf-8")

	assert has_pytest_test_files(tmp_path) is False


def test_has_pytest_test_files_ignores_excluded_directories(tmp_path: Path) -> None:
	venv_tests = tmp_path / ".venv" / "lib"
	venv_tests.mkdir(parents=True)
	(venv_tests / "test_vendored.py").write_text("", encoding="utf-8")

	assert has_pytest_test_files(tmp_path) is False


def test_detect_python_checks_requires_pyproject_toml(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/uv")
	(tmp_path / "test_example.py").write_text("", encoding="utf-8")

	assert detect_python_checks(tmp_path, set()) == []


def test_detect_python_checks_requires_uv_on_path(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)
	(tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
	(tmp_path / "test_example.py").write_text("", encoding="utf-8")

	assert detect_python_checks(tmp_path, set()) == []


def test_detect_python_checks_requires_pytest_test_files(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/uv")
	(tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

	assert detect_python_checks(tmp_path, set()) == []


def test_detect_python_checks_returns_test_unit_when_name_is_free(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/uv")
	(tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
	(tmp_path / "test_example.py").write_text("", encoding="utf-8")

	checks = detect_python_checks(tmp_path, set())

	assert len(checks) == 1
	assert checks[0].name == "test:unit"
	assert checks[0].command == ["uv", "run", "pytest"]
	assert checks[0].test_target_style == diagnostics.TEST_TARGET_STYLE_PATHS


def test_detect_python_checks_renames_to_avoid_collision(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/uv")
	(tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
	(tmp_path / "test_example.py").write_text("", encoding="utf-8")

	checks = detect_python_checks(tmp_path, {"test:unit"})

	assert len(checks) == 1
	assert checks[0].name == "test:unit:python"
