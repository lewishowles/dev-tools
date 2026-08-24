import argparse
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


def test_detect_python_checks_registers_ruff_checks_when_configured(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/uv")
	(tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")

	checks = detect_python_checks(tmp_path, set())

	assert [(check.name, check.command) for check in checks] == [
		("lint:python", ["uv", "run", "ruff", "check"]),
		("format:python", ["uv", "run", "ruff", "format", "--check"]),
	]


def test_detect_python_checks_skips_ruff_without_ruff_configuration(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/uv")
	(tmp_path / "pyproject.toml").write_text(
		"[tool.pytest.ini_options]\n", encoding="utf-8"
	)
	(tmp_path / "test_example.py").write_text("", encoding="utf-8")

	checks = detect_python_checks(tmp_path, set())
	check_names = {check.name for check in checks}

	assert "lint:python" not in check_names
	assert "format:python" not in check_names


def test_detect_python_checks_skips_ruff_for_malformed_pyproject(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/uv")
	(tmp_path / "pyproject.toml").write_text("[tool.ruff\n", encoding="utf-8")
	(tmp_path / "test_example.py").write_text("", encoding="utf-8")

	checks = detect_python_checks(tmp_path, set())
	check_names = {check.name for check in checks}

	assert "lint:python" not in check_names
	assert "format:python" not in check_names


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


@pytest.mark.parametrize("command", ["vitest run", "npx vitest run", "vp test run"])
def test_package_test_target_style_identifies_vitest(command: str) -> None:
	style = diagnostics.package_test_target_style("test:unit:run", command)

	assert style == diagnostics.TEST_TARGET_STYLE_VITEST


def test_package_test_target_style_preserves_other_unit_runners() -> None:
	style = diagnostics.package_test_target_style("test:unit", "bun test")

	assert style == diagnostics.TEST_TARGET_STYLE_PATHS


def test_apply_vitest_worker_limit_caps_full_suite() -> None:
	check = diagnostics.Check(
		"test:unit:run",
		["bun", "run", "test:unit:run"],
		"unit tests",
		test_target_style=diagnostics.TEST_TARGET_STYLE_VITEST,
	)

	limited = diagnostics.apply_vitest_worker_limit([check], 2)

	assert limited[0].command == [
		"bun",
		"run",
		"test:unit:run",
		"--",
		"--maxWorkers=2",
	]


def test_apply_vitest_worker_limit_precedes_test_targets() -> None:
	check = diagnostics.Check(
		"test:unit:run",
		["bun", "run", "test:unit:run"],
		"unit tests",
		test_target_style=diagnostics.TEST_TARGET_STYLE_VITEST,
	)
	targeted, errors = diagnostics.apply_test_targets([check], ["src/example.test.ts"])

	limited = diagnostics.apply_vitest_worker_limit(targeted, 2)

	assert errors == []
	assert limited[0].command == [
		"bun",
		"run",
		"test:unit:run",
		"--",
		"--maxWorkers=2",
		"src/example.test.ts",
	]


def test_apply_vitest_worker_limit_allows_runner_default() -> None:
	check = diagnostics.Check(
		"test:unit:run",
		["bun", "run", "test:unit:run"],
		"unit tests",
		test_target_style=diagnostics.TEST_TARGET_STYLE_VITEST,
	)

	unlimited = diagnostics.apply_vitest_worker_limit([check], None)

	assert unlimited[0].command == ["bun", "run", "test:unit:run"]


def test_apply_vitest_worker_limit_preserves_other_test_runners() -> None:
	check = diagnostics.Check(
		"test:unit",
		["bun", "run", "test:unit"],
		"unit tests",
		test_target_style=diagnostics.TEST_TARGET_STYLE_PATHS,
	)

	limited = diagnostics.apply_vitest_worker_limit([check], 2)

	assert limited[0].command == ["bun", "run", "test:unit"]


@pytest.mark.parametrize("value", ["0", "-1", "many"])
def test_parse_test_workers_rejects_invalid_values(value: str) -> None:
	with pytest.raises(argparse.ArgumentTypeError):
		diagnostics.parse_test_workers(value)


def test_parse_test_workers_accepts_auto() -> None:
	assert diagnostics.parse_test_workers("auto") is None


def test_parse_test_workers_accepts_positive_integer() -> None:
	assert diagnostics.parse_test_workers("3") == 3


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
