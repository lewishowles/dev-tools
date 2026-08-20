import sys
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


def test_has_pytest_test_files_ignores_non_matching_python_files(
	tmp_path: Path,
) -> None:
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


def test_append_xcode_tool_checks_uses_matching_shared_scheme(
	tmp_path: Path,
) -> None:
	container = tmp_path / "Boilersuit.xcodeproj"
	scheme_dir = container / "xcshareddata" / "xcschemes"
	scheme_dir.mkdir(parents=True)
	(scheme_dir / "BoilersuitCLI.xcscheme").write_text(
		"""
<Scheme>
  <BuildAction>
    <BuildActionEntries>
      <BuildActionEntry>
        <BuildableReference BlueprintName="boilersuit" />
      </BuildActionEntry>
    </BuildActionEntries>
  </BuildAction>
</Scheme>
""",
		encoding="utf-8",
	)
	checks: list[diagnostics.Check] = []

	diagnostics.append_xcode_tool_checks(
		checks,
		["xcodebuild", "build", "-project", "Boilersuit.xcodeproj"],
		["boilersuit"],
		container,
	)

	assert checks[0].name == "build:cli"
	assert checks[0].command == [
		"xcodebuild",
		"build",
		"-project",
		"Boilersuit.xcodeproj",
		"-scheme",
		"BoilersuitCLI",
		"-destination",
		diagnostics.XCODE_DESTINATION,
	]


def test_append_xcode_tool_checks_falls_back_to_target_without_matching_scheme(
	tmp_path: Path,
) -> None:
	container = tmp_path / "Boilersuit.xcodeproj"
	scheme_dir = container / "xcshareddata" / "xcschemes"
	scheme_dir.mkdir(parents=True)
	(scheme_dir / "Other.xcscheme").write_text(
		"""
<Scheme>
  <BuildAction>
    <BuildActionEntries>
      <BuildActionEntry>
        <BuildableReference BlueprintName="other" />
      </BuildActionEntry>
    </BuildActionEntries>
  </BuildAction>
</Scheme>
""",
		encoding="utf-8",
	)
	checks: list[diagnostics.Check] = []

	diagnostics.append_xcode_tool_checks(
		checks,
		["xcodebuild", "build", "-project", "Boilersuit.xcodeproj"],
		["Boilersuit"],
		container,
	)

	assert checks[0].command[4:] == [
		"-target",
		"Boilersuit",
		"-destination",
		diagnostics.XCODE_DESTINATION,
	]


def test_append_xcode_tool_checks_preserves_multi_target_names_and_uses_matching_schemes(
	tmp_path: Path,
) -> None:
	container = tmp_path / "Boilersuit.xcodeproj"
	scheme_dir = container / "xcshareddata" / "xcschemes"
	scheme_dir.mkdir(parents=True)
	(scheme_dir / "FirstCLI.xcscheme").write_text(
		"""
<Scheme>
  <BuildAction>
    <BuildActionEntries>
      <BuildActionEntry>
        <BuildableReference BlueprintName="first" />
      </BuildActionEntry>
      <BuildActionEntry>
        <BuildableReference BlueprintName="second" />
      </BuildActionEntry>
    </BuildActionEntries>
  </BuildAction>
</Scheme>
""",
		encoding="utf-8",
	)
	checks: list[diagnostics.Check] = []

	diagnostics.append_xcode_tool_checks(
		checks,
		["xcodebuild", "build", "-project", "Boilersuit.xcodeproj"],
		["first", "second"],
		container,
	)

	assert [check.name for check in checks] == [
		"build:cli:first",
		"build:cli:second",
	]
	assert checks[0].command[4:] == [
		"-scheme",
		"FirstCLI",
		"-destination",
		diagnostics.XCODE_DESTINATION,
	]
	assert checks[1].command[4:] == [
		"-scheme",
		"FirstCLI",
		"-destination",
		diagnostics.XCODE_DESTINATION,
	]


def test_append_xcode_tool_checks_ignores_non_build_references(
	tmp_path: Path,
) -> None:
	container = tmp_path / "Boilersuit.xcodeproj"
	scheme_dir = container / "xcshareddata" / "xcschemes"
	scheme_dir.mkdir(parents=True)
	(scheme_dir / "BoilersuitCLI.xcscheme").write_text(
		"""
<Scheme>
  <BuildAction>
    <BuildActionEntries>
      <BuildActionEntry>
        <BuildableReference BlueprintName="boilersuit" />
      </BuildActionEntry>
    </BuildActionEntries>
  </BuildAction>
  <TestAction>
    <Testables>
      <TestableReference>
        <BuildableReference BlueprintName="test-only" />
      </TestableReference>
    </Testables>
  </TestAction>
  <LaunchAction>
    <BuildableProductRunnable>
      <BuildableReference BlueprintName="runnable-only" />
    </BuildableProductRunnable>
  </LaunchAction>
</Scheme>
""",
		encoding="utf-8",
	)
	checks: list[diagnostics.Check] = []

	diagnostics.append_xcode_tool_checks(
		checks,
		["xcodebuild", "build", "-project", "Boilersuit.xcodeproj"],
		["test-only", "runnable-only"],
		container,
	)

	assert [check.command[4] for check in checks] == ["-target", "-target"]


def test_xcode_scheme_build_targets_skips_malformed_scheme(
	tmp_path: Path,
) -> None:
	container = tmp_path / "Boilersuit.xcodeproj"
	scheme_dir = container / "xcshareddata" / "xcschemes"
	scheme_dir.mkdir(parents=True)
	(scheme_dir / "Broken.xcscheme").write_text("<Scheme>", encoding="utf-8")

	assert diagnostics.xcode_scheme_build_targets(container) == {}


def test_detect_python_checks_renames_to_avoid_collision(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/uv")
	(tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
	(tmp_path / "test_example.py").write_text("", encoding="utf-8")

	checks = detect_python_checks(tmp_path, {"test:unit"})

	assert len(checks) == 1
	assert checks[0].name == "test:unit:python"


def test_resolve_fuzzy_test_targets_reports_zero_matches(
	tmp_path: Path,
) -> None:
	test_file = tmp_path / "tests" / "other.pw.ts"
	test_file.parent.mkdir()
	test_file.write_text("", encoding="utf-8")
	check = diagnostics.Check(
		"test:component",
		["bun", "run", "test:component"],
		"component tests",
		test_target_style=diagnostics.TEST_TARGET_STYLE_PLAYWRIGHT,
	)

	targets, errors = diagnostics.resolve_fuzzy_test_targets(
		tmp_path, check, ["data-table"]
	)

	assert targets == []
	assert errors == ["no test file matched pattern: data-table"]


def test_resolve_fuzzy_test_targets_returns_a_matching_file(
	tmp_path: Path,
) -> None:
	test_file = tmp_path / "tests" / "Data-Table.pw.ts"
	test_file.parent.mkdir()
	test_file.write_text("", encoding="utf-8")
	check = diagnostics.Check(
		"test:component",
		["bun", "run", "test:component"],
		"component tests",
		test_target_style=diagnostics.TEST_TARGET_STYLE_PLAYWRIGHT,
	)

	targets, errors = diagnostics.resolve_fuzzy_test_targets(
		tmp_path, check, ["DATA-TABLE"]
	)

	assert targets == ["tests/Data-Table.pw.ts"]
	assert errors == []


def test_resolve_fuzzy_test_targets_returns_all_matching_files(
	tmp_path: Path,
) -> None:
	first_file = tmp_path / "tests" / "data-table.pw.ts"
	second_file = tmp_path / "other" / "data-table.pw.js"
	first_file.parent.mkdir()
	second_file.parent.mkdir()
	first_file.write_text("", encoding="utf-8")
	second_file.write_text("", encoding="utf-8")
	check = diagnostics.Check(
		"test:component",
		["bun", "run", "test:component"],
		"component tests",
		test_target_style=diagnostics.TEST_TARGET_STYLE_PLAYWRIGHT,
	)

	targets, errors = diagnostics.resolve_fuzzy_test_targets(
		tmp_path, check, ["data-table"]
	)

	assert targets == ["other/data-table.pw.js", "tests/data-table.pw.ts"]
	assert errors == []


def test_resolve_fuzzy_test_targets_rejects_unsupported_check(
	tmp_path: Path,
) -> None:
	check = diagnostics.Check(
		"lint",
		["bun", "run", "lint"],
		"lint",
	)

	targets, errors = diagnostics.resolve_fuzzy_test_targets(
		tmp_path, check, ["data-table"]
	)

	assert targets == []
	assert errors == ["check does not support test targets: lint"]


def test_main_rejects_fuzzy_matching_with_another_target_option(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
	monkeypatch.setattr(
		sys,
		"argv",
		[
			"project-checks",
			"--project",
			str(tmp_path),
			"--check",
			"test:component",
			"--test-match",
			"data-table",
			"--test-file",
			"tests/data-table.pw.ts",
		],
	)

	real_which = diagnostics.shutil.which

	monkeypatch.setattr(
		diagnostics.shutil,
		"which",
		lambda name: None if name == "cli-style" else real_which(name),
	)

	result = diagnostics.main()
	captured = capsys.readouterr()

	assert result == 2
	assert captured.err == (
		"x Error Use --test-match on its own, not with --test-file or --test-glob.\n"
	)
