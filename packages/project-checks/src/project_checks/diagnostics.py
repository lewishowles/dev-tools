#!/usr/bin/env python3
# Run conservative project diagnostics and return compact output.

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DESCRIPTION = """Run conservative project diagnostics.

Default mode lists available checks without running them. Use --check to run a
specific check, or --all when broad safe verification has been explicitly
requested.
"""

EPILOG = """Commands:
  --list              Discover available diagnostics without running them.
  --check NAME        Run one named check, such as test:unit or lint.
  --test-file PATH    Run a targetable test check against one file. Repeat for multiple files.
  --test-glob PATTERN Run a targetable test check against matching files. Repeat for multiple globs.
  --test-match PATTERN
                      Run a targetable test check against files whose paths contain a pattern.
  --all               Run conservative checks that do not require explicit targets.
  --json              Return machine-readable output for the selected mode.

Xcode targeting maps the nearest directory ending in Tests to the test target
and the Swift filename to the test suite.

Examples:
  project-checks --list
  project-checks --check test:unit
  project-checks --check test:unit --test-file src/example.test.ts
  project-checks --check test:unit --test-glob 'src/**/*.test.ts'
  project-checks --check test:component --test-file src/example.pw.ts
  project-checks --check test:component --test-match data-table
  project-checks --check build:cli
  project-checks --check lint --check test:unit
  project-checks --all
  project-checks --json --list
"""

UNIT_TEST_SCRIPT_NAMES = {
	"test:unit",
	"test:unit:run",
}

SAFE_SCRIPT_NAMES = {
	"attw",
	"check",
	"check:types",
	"lint",
	"check",
	"publint",
	"test:component",
	"test:unit",
	"test:unit:run",
	"typecheck",
	"type-check",
	"validate",
}

SKIPPED_SCRIPT_NAMES = {
	"build",
	"dev",
	"e2e",
	"format",
	"lint:fix",
	"preview",
	"publish",
	"release",
	"start",
	"test",
	"test:all",
	"test:e2e",
}

MUTATING_COMMAND_HINTS = (
	"--fix",
	"--write",
	"format",
	"publish",
	"release",
	"deploy",
	"migrate",
)
ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

# Directories never worth walking when locating an Xcode project.
EXCLUDED_DIRS = {
	".git",
	".agent",
	".build",
	".swiftpm",
	"build",
	"DerivedData",
	"Pods",
	"node_modules",
	"dist",
	"vendor",
}

# How deep to look for an Xcode container. Projects live at the root or one level down in practice.
XCODE_SCAN_DEPTH = 3

# Xcode builds and test runs are far slower than Node checks, so they get their own ceiling.
XCODE_TIMEOUT = 600

# Xcode product type for command-line executable targets.
XCODE_TOOL_PRODUCT_TYPE = "com.apple.product-type.tool"

# Test destination. Pins arch=arm64 so xcodebuild doesn't warn about the ambiguous arm64/x86_64
# match (x86_64 is dropped in the next macOS). Override here (or via env) for iOS/other platforms.
XCODE_DESTINATION = os.environ.get(
	"PROJECT_DIAGNOSTICS_XCODE_DESTINATION", "platform=macOS,arch=arm64"
)

# Test target argument formats used by supported runners.
TEST_TARGET_STYLE_PATHS = "paths"
TEST_TARGET_STYLE_PLAYWRIGHT = "playwright"
TEST_TARGET_STYLE_XCODE = "xcode"

# Lines worth keeping from a verbose xcodebuild log when building the compact summary.
# Deliberately excludes the per-suite "started"/"passed" chatter, which floods the output.
XCODE_SUMMARY_TOKENS = (
	"error:",
	"** build",
	"** test",
	"failed on",
	"failing tests",
	"testing failed",
)

# Substrings that mark a failure reason inside an xcresult test-details node name.
XCRESULT_FAILURE_MARKERS = (
	"expectation failed",
	"issue recorded",
	"xctassert",
	"fatal error",
	"error:",
	"caught error",
	"threw error",
	"failed:",
)


@dataclass
class Check:
	name: str
	command: list[str]
	reason: str
	timeout: int | None = None
	xcresult: bool = False
	test_target_style: str | None = None
	test_targets_required: bool = False


@dataclass
class Result:
	name: str
	command: list[str]
	status: str
	exit_code: int | None
	log_path: str
	summary: list[str]


def load_package_json(project_dir: Path) -> dict[str, Any]:
	path = project_dir / "package.json"
	if not path.exists():
		return {}

	try:
		return json.loads(path.read_text())
	except json.JSONDecodeError:
		return {}


def detect_package_runner(project_dir: Path) -> list[str] | None:
	if (project_dir / "bun.lock").exists() or (project_dir / "bun.lockb").exists():
		return ["bun", "run"]
	if (project_dir / "pnpm-lock.yaml").exists():
		return ["pnpm", "run"]
	if (project_dir / "yarn.lock").exists():
		return ["yarn"]
	if (project_dir / "package-lock.json").exists() or (
		project_dir / "package.json"
	).exists():
		return ["npm", "run"]
	return None


def scan_xcode_layout(project_dir: Path) -> tuple[list[Path], list[Path], list[str]]:
	# Single shallow walk that prunes heavy directories and never descends into .xcodeproj or
	# .xcworkspace bundles. Returns (projects, workspaces, UI-test target names).
	projects: list[Path] = []
	workspaces: list[Path] = []
	ui_targets: set[str] = set()
	base_depth = len(project_dir.parts)

	for root, dirs, _files in os.walk(project_dir):
		root_path = Path(root)
		depth = len(root_path.parts) - base_depth

		keep: list[str] = []
		for name in dirs:
			if name.endswith(".xcodeproj"):
				projects.append(root_path / name)
				continue
			if name.endswith(".xcworkspace"):
				workspaces.append(root_path / name)
				continue
			if name in EXCLUDED_DIRS or name.startswith("."):
				continue
			if name.endswith("UITests"):
				ui_targets.add(name)
			keep.append(name)

		dirs[:] = [] if depth >= XCODE_SCAN_DEPTH else keep

	return projects, workspaces, sorted(ui_targets)


# Returns a PBX assignment value from one project.pbxproj line.
#
# @param  {str}  line
#     Source line from project.pbxproj.
# @param  {str}  key
#     PBX key to read.
def pbx_assignment_value(line: str, key: str) -> str | None:
	match = re.search(rf"\b{re.escape(key)}\s*=\s*(.*?);", line)
	if not match:
		return None

	value = match.group(1).strip()
	if value.startswith('"') and value.endswith('"'):
		return value[1:-1]
	return value


# Returns the display name embedded in a PBX object reference comment.
#
# @param  {str}  line
#     Object header line from project.pbxproj.
def pbx_reference_name(line: str) -> str | None:
	match = re.search(r"/\*\s*(.*?)\s*\*/", line)
	if match:
		return match.group(1)
	return None


# Slugifies a target name for use in diagnostics check names.
#
# @param  {str}  name
#     Xcode target name.
def check_name_slug(name: str) -> str:
	slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
	return slug or "target"


# Returns command-line tool target names declared by Xcode project files.
#
# @param  {list[Path]}  projects
#     Xcode project bundles to inspect.
def detect_xcode_tool_targets(projects: list[Path]) -> list[str]:
	targets: set[str] = set()

	for project in projects:
		pbxproj = project / "project.pbxproj"
		if not pbxproj.exists():
			continue

		current_name: str | None = None
		explicit_name: str | None = None
		is_native_target = False
		product_type: str | None = None

		for line in pbxproj.read_text(errors="ignore").splitlines():
			if current_name is None and " = {" in line:
				current_name = pbx_reference_name(line)
				explicit_name = None
				is_native_target = False
				product_type = None
				continue

			if current_name is None:
				continue

			isa = pbx_assignment_value(line, "isa")
			if isa == "PBXNativeTarget":
				is_native_target = True

			name = pbx_assignment_value(line, "name")
			if name:
				explicit_name = name

			target_product_type = pbx_assignment_value(line, "productType")
			if target_product_type:
				product_type = target_product_type

			if line.strip() == "};":
				if is_native_target and product_type == XCODE_TOOL_PRODUCT_TYPE:
					target_name = explicit_name or current_name
					if target_name:
						targets.add(target_name)

				current_name = None

	return sorted(targets)


# Adds command-line tool target build checks when Xcode declares tool targets.
#
# @param  {list[Check]}  checks
#     Check list to append to.
# @param  {list[str]}  base_command
#     xcodebuild command prefix for the selected container.
# @param  {list[str]}  tool_targets
#     Xcode command-line tool target names.
def append_xcode_tool_checks(
	checks: list[Check], base_command: list[str], tool_targets: list[str]
) -> None:
	if len(tool_targets) == 1:
		checks.append(
			Check(
				"build:cli",
				[
					*base_command,
					"-target",
					tool_targets[0],
					"-destination",
					XCODE_DESTINATION,
				],
				"Xcode CLI target build",
				timeout=XCODE_TIMEOUT,
			)
		)
		return

	used_slugs: set[str] = set()
	for target in tool_targets:
		slug = check_name_slug(target)
		if slug in used_slugs:
			slug = f"{slug}-{len(used_slugs) + 1}"
		used_slugs.add(slug)

		checks.append(
			Check(
				f"build:cli:{slug}",
				[*base_command, "-target", target, "-destination", XCODE_DESTINATION],
				f"Xcode CLI target build ({target})",
				timeout=XCODE_TIMEOUT,
			)
		)


def find_xcode_scheme(container: Path) -> str:
	scheme_dir = container / "xcshareddata" / "xcschemes"
	schemes = (
		sorted(path.stem for path in scheme_dir.glob("*.xcscheme"))
		if scheme_dir.is_dir()
		else []
	)
	if container.stem in schemes:
		return container.stem
	return schemes[0] if schemes else container.stem


def detect_xcode_checks(project_dir: Path) -> list[Check]:
	projects, workspaces, ui_targets = scan_xcode_layout(project_dir)
	containers = workspaces or projects
	if not containers:
		return []

	# Prefer the shallowest container, breaking ties deterministically by path.
	container = min(containers, key=lambda path: (len(path.parts), str(path)))
	scheme = find_xcode_scheme(container)
	container_flag = "-workspace" if container.suffix == ".xcworkspace" else "-project"
	container_path = str(container.relative_to(project_dir))

	# No -quiet: it hides the per-assertion "error:" lines that explain *why* a test failed.
	base = [
		"xcodebuild",
		container_flag,
		container_path,
		"-scheme",
		scheme,
		"-destination",
		XCODE_DESTINATION,
	]
	target_base = ["xcodebuild", "build", container_flag, container_path]
	skip_args = [f"-skip-testing:{target}" for target in ui_targets]
	skip_reason = " (UI tests skipped)" if skip_args else ""
	checks = [
		Check(
			"build",
			["xcodebuild", "build", *base[1:]],
			"Xcode build",
			timeout=XCODE_TIMEOUT,
		),
		Check(
			"test:unit",
			["xcodebuild", "test", *base[1:], *skip_args],
			f"Xcode unit tests{skip_reason}",
			timeout=XCODE_TIMEOUT,
			xcresult=True,
			test_target_style=TEST_TARGET_STYLE_XCODE,
		),
	]

	append_xcode_tool_checks(checks, target_base, detect_xcode_tool_targets(projects))
	return checks


def script_is_safe(name: str, command: str) -> bool:
	lower_command = command.lower()
	if name not in SAFE_SCRIPT_NAMES:
		return False
	return not any(hint in lower_command for hint in MUTATING_COMMAND_HINTS)


def script_skip_reason(name: str, command: str) -> str | None:
	lower_command = command.lower()
	if name in SKIPPED_SCRIPT_NAMES:
		return "broad, long-running, or mutating script"
	if any(hint in lower_command for hint in MUTATING_COMMAND_HINTS):
		return "mutating script"
	return None


def package_test_target_style(name: str, command: str) -> str | None:
	if name in UNIT_TEST_SCRIPT_NAMES:
		return TEST_TARGET_STYLE_PATHS
	if name == "test:component" and "playwright" in command.lower():
		return TEST_TARGET_STYLE_PLAYWRIGHT
	return None


# Directories never worth walking when locating pytest test files.
PYTHON_EXCLUDED_DIRS = EXCLUDED_DIRS | {".venv", "venv", "__pycache__"}


def has_pytest_test_files(project_dir: Path) -> bool:
	for root, dirs, files in os.walk(project_dir):
		dirs[:] = [
			name
			for name in dirs
			if name not in PYTHON_EXCLUDED_DIRS and not name.startswith(".")
		]
		if any(
			name.startswith("test_") or name.endswith("_test.py")
			for name in files
			if name.endswith(".py")
		):
			return True
	return False


def detect_python_checks(project_dir: Path, existing_names: set[str]) -> list[Check]:
	if not (project_dir / "pyproject.toml").exists():
		return []
	if not shutil.which("uv"):
		return []
	if not has_pytest_test_files(project_dir):
		return []

	name = "test:unit:python" if "test:unit" in existing_names else "test:unit"
	return [
		Check(
			name,
			["uv", "run", "pytest"],
			"pytest test suite",
			test_target_style=TEST_TARGET_STYLE_PATHS,
		)
	]


def discover_checks(project_dir: Path) -> tuple[list[Check], list[str]]:
	checks: list[Check] = []
	skipped: list[str] = []

	validate_script = project_dir / "scripts" / "validate.sh"
	if validate_script.exists():
		checks.append(
			Check(
				"validate", ["bash", "scripts/validate.sh"], "local validation script"
			)
		)

	package = load_package_json(project_dir)
	scripts = (
		package.get("scripts", {}) if isinstance(package.get("scripts"), dict) else {}
	)
	runner = detect_package_runner(project_dir)

	for name in sorted(scripts):
		command = str(scripts[name])
		skip_reason = script_skip_reason(name, command)
		if skip_reason:
			skipped.append(f"{name}: {skip_reason}")
			continue

		if runner and script_is_safe(name, command):
			test_target_style = package_test_target_style(name, command)
			checks.append(
				Check(
					name,
					[*runner, name],
					"targeted Playwright package script"
					if test_target_style == TEST_TARGET_STYLE_PLAYWRIGHT
					else "conservative package script",
					test_target_style=test_target_style,
					test_targets_required=test_target_style
					== TEST_TARGET_STYLE_PLAYWRIGHT,
				)
			)

	checks.extend(detect_xcode_checks(project_dir))
	checks.extend(detect_python_checks(project_dir, {check.name for check in checks}))

	if not checks:
		skipped.append("no conservative diagnostics command found")

	return checks, skipped


def dedupe_checks(checks: list[Check]) -> list[Check]:
	names = {check.name for check in checks}
	duplicates = {
		"test:unit": "test:unit:run",
	}

	return [check for check in checks if duplicates.get(check.name) not in names]


def selected_checks(
	checks: list[Check], requested_names: list[str], run_all: bool
) -> tuple[list[Check], list[str]]:
	if run_all:
		return [
			check for check in dedupe_checks(checks) if not check.test_targets_required
		], []

	by_name = {check.name: check for check in checks}
	selected = []
	errors = []

	for name in requested_names:
		if name in by_name:
			selected.append(by_name[name])
		else:
			errors.append(f"unknown or unsafe check: {name}")

	return selected, errors


def resolve_test_targets(
	project_dir: Path, test_files: list[str], test_globs: list[str]
) -> tuple[list[str], list[str]]:
	targets: set[str] = set()
	errors: list[str] = []

	for value in test_files:
		path = Path(value)
		if path.is_absolute() or ".." in path.parts:
			errors.append(f"test file must stay inside the project: {value}")
			continue

		resolved = (project_dir / path).resolve()
		try:
			relative = resolved.relative_to(project_dir)
		except ValueError:
			errors.append(f"test file must stay inside the project: {value}")
			continue

		if not resolved.is_file():
			errors.append(f"test file not found: {value}")
			continue

		targets.add(str(relative))

	for pattern in test_globs:
		path = Path(pattern)
		if path.is_absolute() or ".." in path.parts:
			errors.append(f"test glob must stay inside the project: {pattern}")
			continue

		matches = []
		try:
			matches = sorted(project_dir.glob(pattern))
		except (NotImplementedError, ValueError):
			errors.append(f"invalid test glob: {pattern}")
			continue

		valid_matches = 0
		for match in matches:
			resolved = match.resolve()
			try:
				relative = resolved.relative_to(project_dir)
			except ValueError:
				errors.append(f"test glob matched outside the project: {pattern}")
				continue

			if resolved.is_file():
				targets.add(str(relative))
				valid_matches += 1

		if valid_matches == 0:
			errors.append(f"test glob matched no files: {pattern}")

	return sorted(targets), errors


def resolve_fuzzy_test_targets(
	project_dir: Path, check: Check, patterns: list[str]
) -> tuple[list[str], list[str]]:
	targets: set[str] = set()
	errors: list[str] = []

	if check.test_target_style is None:
		return [], [f"check does not support test targets: {check.name}"]

	for pattern in patterns:
		matches: list[str] = []
		for root, dirs, files in os.walk(project_dir):
			dirs[:] = [
				name for name in dirs if name not in PYTHON_EXCLUDED_DIRS
			]
			for filename in files:
				relative_path = (Path(root) / filename).relative_to(project_dir)
				path_matches_style = (
					check.test_target_style == TEST_TARGET_STYLE_PLAYWRIGHT
					and filename.endswith((".pw.ts", ".pw.js"))
				) or (
					check.test_target_style == TEST_TARGET_STYLE_XCODE
					and filename.endswith(".swift")
					and any(
						part.endswith("Tests")
						for part in relative_path.parent.parts
					)
				) or (
					check.test_target_style == TEST_TARGET_STYLE_PATHS
					and (
						filename.endswith(
							(".test.ts", ".test.tsx", ".test.js", ".test.jsx")
						)
						or filename.startswith("test_") and filename.endswith(".py")
						or filename.endswith("_test.py")
					)
				)
				if path_matches_style and pattern.lower() in str(relative_path).lower():
					matches.append(str(relative_path))

		if not matches:
			errors.append(f"no test file matched pattern: {pattern}")
		else:
			targets.update(matches)

	return sorted(targets), errors


def xcode_test_arguments(targets: list[str]) -> tuple[list[str], list[str]]:
	arguments: list[str] = []
	errors: list[str] = []

	for target in targets:
		path = Path(target)
		test_target = next(
			(part for part in reversed(path.parent.parts) if part.endswith("Tests")),
			None,
		)

		if path.suffix != ".swift":
			errors.append(f"Xcode test file must be a Swift source file: {target}")
			continue
		if not test_target:
			errors.append(
				f"Xcode test file must be inside a directory ending in Tests: {target}"
			)
			continue

		arguments.append(f"-only-testing:{test_target}/{path.stem}")

	return arguments, errors


def apply_test_targets(
	checks: list[Check], targets: list[str]
) -> tuple[list[Check], list[str]]:
	if not targets:
		required_checks = [check for check in checks if check.test_targets_required]
		if required_checks:
			return checks, [
				f"{check.name} requires --test-file or --test-glob; for example: "
				f"project-checks --check {check.name} --test-file <path>"
				for check in required_checks
			]
		return checks, []
	if len(checks) != 1:
		return checks, ["test targets require exactly one check"]

	check = checks[0]
	if check.test_target_style is None:
		return checks, [f"check does not support test targets: {check.name}"]

	target_arguments = ["--", *targets]
	if check.test_target_style == TEST_TARGET_STYLE_PLAYWRIGHT:
		target_arguments = ["--", "--workers=1", *targets]
	elif check.test_target_style == TEST_TARGET_STYLE_XCODE:
		target_arguments, errors = xcode_test_arguments(targets)
		if errors:
			return checks, errors

	targeted = Check(
		name=check.name,
		command=[*check.command, *target_arguments],
		reason=check.reason,
		timeout=check.timeout,
		xcresult=check.xcresult,
		test_target_style=check.test_target_style,
		test_targets_required=check.test_targets_required,
	)
	return [targeted], []


def command_label(command: list[str]) -> str:
	return " ".join(shlex.quote(part) for part in command)


def redact(text: str) -> str:
	lines = []
	for line in ANSI_PATTERN.sub("", text).splitlines():
		lower = line.lower()
		if any(
			token in lower
			for token in [
				"api_key",
				"apikey",
				"authorization:",
				"password",
				"secret",
				"token=",
			]
		):
			lines.append("[redacted possible secret]")
		else:
			lines.append(line)
	return "\n".join(lines)


def summarise_output(output: str, limit: int = 8) -> list[str]:
	clean = redact(output).strip()
	if not clean:
		return ["No output."]

	lines = [line for line in clean.splitlines() if line.strip()]
	return lines[-limit:]


def summarise_xcode(output: str, limit: int = 15) -> list[str]:
	# xcodebuild's tail is linker noise. Prefer lines that name an error or a test result.
	clean = redact(output).strip()
	if not clean:
		return ["No output."]

	lines = [line for line in clean.splitlines() if line.strip()]
	relevant = [
		line
		for line in lines
		if any(token in line.lower() for token in XCODE_SUMMARY_TOKENS)
	]
	return (relevant or lines)[-limit:]


def summarise_for(check: Check, output: str) -> list[str]:
	if check.command and check.command[0] == "xcodebuild":
		return summarise_xcode(output)
	return summarise_output(output)


def _iter_nodes(node: Any):
	if isinstance(node, dict):
		yield node
		for value in node.values():
			yield from _iter_nodes(value)
	elif isinstance(node, list):
		for value in node:
			yield from _iter_nodes(value)


def _xcresulttool_json(args: list[str]) -> Any:
	try:
		completed = subprocess.run(
			["xcrun", "xcresulttool", *args],
			text=True,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			timeout=60,
			check=False,
		)
	except (FileNotFoundError, subprocess.TimeoutExpired):
		return None

	if completed.returncode != 0 or not completed.stdout:
		return None

	try:
		return json.loads(completed.stdout)
	except json.JSONDecodeError:
		return None


def extract_xcresult_failures(bundle: Path, max_tests: int = 12) -> list[str]:
	# Swift Testing writes expectation failures only to the result bundle, never to the
	# console, so read the reason for each failed test back out via xcresulttool.
	tests = _xcresulttool_json(["get", "test-results", "tests", "--path", str(bundle)])
	if not isinstance(tests, dict):
		return []

	failed: list[str] = []
	for node in _iter_nodes(tests.get("testNodes", [])):
		if node.get("nodeType") == "Test Case" and node.get("result") == "Failed":
			identifier = node.get("nodeIdentifier") or node.get("name")
			if identifier and identifier not in failed:
				failed.append(identifier)

	lines: list[str] = []
	for identifier in failed[:max_tests]:
		details = _xcresulttool_json(
			[
				"get",
				"test-results",
				"test-details",
				"--test-id",
				identifier,
				"--path",
				str(bundle),
			]
		)
		message = None
		for node in _iter_nodes(details):
			name = node.get("name")
			if isinstance(name, str) and any(
				marker in name.lower() for marker in XCRESULT_FAILURE_MARKERS
			):
				message = " ".join(name.split())
				break

		lines.append(
			f"{identifier}: {message[:240]}"
			if message
			else f"{identifier}: failed (reason not captured)"
		)

	remaining = len(failed) - max_tests
	if remaining > 0:
		lines.append(f"... and {remaining} more failing test(s).")

	return lines


def run_check(project_dir: Path, log_dir: Path, check: Check, timeout: int) -> Result:
	started = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
	log_path = log_dir / f"{started}-{check.name.replace(':', '-')}.log"
	effective_timeout = check.timeout or timeout

	# For xcodebuild test runs, write a result bundle we can mine for Swift Testing failure
	# reasons. xcodebuild refuses a pre-existing path, so clear any stale bundle first.
	command = list(check.command)
	bundle: Path | None = None
	if check.xcresult:
		bundle = log_dir / f"{started}-{check.name.replace(':', '-')}.xcresult"
		shutil.rmtree(bundle, ignore_errors=True)
		command = [*command, "-resultBundlePath", str(bundle)]

	try:
		completed = subprocess.run(
			command,
			cwd=project_dir,
			text=True,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			timeout=effective_timeout,
			check=False,
		)
		output = completed.stdout or ""
		log_path.write_text(redact(output))

		status = "passed" if completed.returncode == 0 else "failed"
		summary = summarise_for(check, output)
		if status != "passed" and bundle is not None and bundle.exists():
			failures = extract_xcresult_failures(bundle)
			if failures:
				summary = failures

		return Result(
			name=check.name,
			command=check.command,
			status=status,
			exit_code=completed.returncode,
			log_path=str(log_path.relative_to(project_dir)),
			summary=summary,
		)
	except subprocess.TimeoutExpired as error:
		output = error.stdout or ""
		if isinstance(output, bytes):
			output = output.decode(errors="replace")
		log_path.write_text(redact(output))

		return Result(
			name=check.name,
			command=check.command,
			status="timeout",
			exit_code=None,
			log_path=str(log_path.relative_to(project_dir)),
			summary=[f"Timed out after {effective_timeout}s."],
		)
	except FileNotFoundError:
		log_path.write_text("")
		return Result(
			name=check.name,
			command=check.command,
			status="skipped",
			exit_code=None,
			log_path=str(log_path.relative_to(project_dir)),
			summary=[f"Command not found: {check.command[0]}"],
		)
	finally:
		if bundle is not None:
			shutil.rmtree(bundle, ignore_errors=True)


def render_markdown(
	project_dir: Path, results: list[Result], skipped: list[str]
) -> str:
	lines = [
		"# Project diagnostics",
		"",
		f"Project: `{project_dir}`",
		"",
		"| Check | Status | Command | Log |",
		"| --- | --- | --- | --- |",
	]

	for result in results:
		lines.append(
			f"| {result.name} | {result.status} | `{command_label(result.command)}` | `{result.log_path}` |"
		)

	if not results:
		lines.append("| None | skipped |  |  |")

	lines.extend(["", "## Output summary", ""])

	for result in results:
		lines.append(f"### {result.name}")
		lines.extend(f"- {line}" for line in result.summary)
		lines.append("")

	if skipped:
		lines.extend(["## Skipped", ""])
		lines.extend(f"- {item}" for item in skipped)
		lines.append("")

	return "\n".join(lines).rstrip() + "\n"


def render_list_markdown(
	project_dir: Path, checks: list[Check], skipped: list[str]
) -> str:
	lines = [
		"# Project diagnostics",
		"",
		f"Project: `{project_dir}`",
		"",
		"Mode: list only. No checks were run.",
		"",
		"| Check | Command | Description |",
		"| --- | --- | --- |",
	]

	for check in checks:
		lines.append(
			f"| {check.name} | `{command_label(check.command)}` | {check.reason} |"
		)

	if not checks:
		lines.append("| None |  | No conservative diagnostics command found |")

	if skipped:
		lines.extend(["", "## Skipped", ""])
		lines.extend(f"- {item}" for item in skipped)

	return "\n".join(lines).rstrip() + "\n"


def render_json(project_dir: Path, results: list[Result], skipped: list[str]) -> str:
	payload = {
		"project": str(project_dir),
		"results": [
			{
				"name": result.name,
				"command": result.command,
				"status": result.status,
				"exit_code": result.exit_code,
				"log_path": result.log_path,
				"summary": result.summary,
			}
			for result in results
		],
		"skipped": skipped,
	}
	return json.dumps(payload, indent=2) + "\n"


def render_list_json(project_dir: Path, checks: list[Check], skipped: list[str]) -> str:
	payload = {
		"project": str(project_dir),
		"mode": "list",
		"checks": [
			{
				"name": check.name,
				"command": check.command,
				"description": check.reason,
			}
			for check in checks
		],
		"skipped": skipped,
	}
	return json.dumps(payload, indent=2) + "\n"


def main() -> int:
	parser = argparse.ArgumentParser(
		description=DESCRIPTION,
		epilog=EPILOG,
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	parser.add_argument(
		"--project",
		type=Path,
		default=Path.cwd(),
		help="Project directory to inspect. Defaults to the current directory.",
	)
	parser.add_argument(
		"--json",
		action="store_true",
		help="Print JSON instead of Markdown for list or run output.",
	)
	parser.add_argument(
		"--timeout",
		type=int,
		default=120,
		help="Timeout per check in seconds. Default: 120.",
	)
	parser.add_argument(
		"--list",
		action="store_true",
		help="List available and skipped checks without running anything. This is the default.",
	)
	parser.add_argument(
		"--check",
		action="append",
		default=[],
		metavar="NAME",
		help="Run one named check. Repeat to run multiple checks.",
	)
	parser.add_argument(
		"--test-file",
		action="append",
		default=[],
		metavar="PATH",
		help="Run a targetable test check against one project-relative file. Repeat for multiple files.",
	)
	parser.add_argument(
		"--test-glob",
		action="append",
		default=[],
		metavar="PATTERN",
		help="Run a targetable test check against matching project-relative files. Repeat for multiple globs.",
	)
	parser.add_argument(
		"--test-match",
		action="append",
		default=[],
		metavar="PATTERN",
		help="Run a targetable test check against files whose project-relative paths contain a pattern. Repeat for multiple patterns.",
	)
	parser.add_argument(
		"--all",
		action="store_true",
		help="Run conservative checks that do not require explicit targets. Use only after approval for broad verification.",
	)
	args = parser.parse_args()

	if args.all and args.check:
		print("Use either --all or --check, not both.", file=sys.stderr)
		return 2
	if args.test_match and (args.test_file or args.test_glob):
		print(
			"Use --test-match on its own, not with --test-file or --test-glob.",
			file=sys.stderr,
		)
		return 2
	if (args.test_file or args.test_glob or args.test_match) and (
		args.all or args.list or not args.check
	):
		print(
			"Test targets require one --check and cannot be used with --list or --all.",
			file=sys.stderr,
		)
		return 2

	project_dir = args.project.resolve()
	if not project_dir.is_dir():
		print(f"Project directory not found: {project_dir}", file=sys.stderr)
		return 2

	checks, skipped = discover_checks(project_dir)
	list_only = args.list or (not args.check and not args.all)

	if list_only:
		output = (
			render_list_json(project_dir, checks, skipped)
			if args.json
			else render_list_markdown(project_dir, checks, skipped)
		)
		print(output, end="")
		return 0

	checks_to_run, selection_errors = selected_checks(checks, args.check, args.all)
	if args.all:
		skipped.extend(
			f"{check.name}: requires --test-file or --test-glob and is excluded from --all"
			for check in dedupe_checks(checks)
			if check.test_targets_required
		)
	if selection_errors:
		for error in selection_errors:
			print(error, file=sys.stderr)
		print("Run with --list to see available checks.", file=sys.stderr)
		return 2

	if args.test_match:
		if len(checks_to_run) == 1:
			test_targets, target_errors = resolve_fuzzy_test_targets(
				project_dir, checks_to_run[0], args.test_match
			)
		else:
			# Multiple checks selected: skip fuzzy resolution and pass the raw patterns
			# through as targets so apply_test_targets' own single-check guard below
			# produces the shared "test targets require exactly one check" error.
			test_targets, target_errors = args.test_match, []
	else:
		test_targets, target_errors = resolve_test_targets(
			project_dir, args.test_file, args.test_glob
		)
	checks_to_run, applicability_errors = apply_test_targets(
		checks_to_run, test_targets
	)
	target_errors.extend(applicability_errors)
	if target_errors:
		for error in target_errors:
			print(error, file=sys.stderr)
		return 2

	log_dir = project_dir / ".agent" / "diagnostics"
	log_dir.mkdir(parents=True, exist_ok=True)

	results = [
		run_check(project_dir, log_dir, check, args.timeout) for check in checks_to_run
	]

	output = (
		render_json(project_dir, results, skipped)
		if args.json
		else render_markdown(project_dir, results, skipped)
	)
	print(output, end="")

	if any(result.status in {"failed", "timeout"} for result in results):
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
