#!/usr/bin/env node
import { join, resolve } from "node:path";
import { createCliStyle, hint, row, status } from "@lewishowles/cli-style";
import { readExportsConfig, runExportsCheck } from "./checks/exports.js";
import { readRuntimeDependencyConfig, runRuntimeDependencyCheck } from "./checks/runtime-deps.js";
import { readSizeConfig, runSizeCheck } from "./checks/size.js";
import { runTestCoverageCheck } from "./checks/test-coverage.js";
import { runTypeDeclarationsCheck } from "./checks/type-declarations.js";

// The usage text, shown both for --help and after an argument error.
const usage = [
	"Usage: pkg-checks <command> <package-path>",
	"",
	"Commands:",
	"  exports <package-path>       Check category barrels and package.json exports.",
	"  runtime-deps <package-path>  Check configured runtime dependency policy.",
	"  size <package-path>          Check configured package size budgets.",
	"  type-declarations <package-path>  Check exports have matching type declarations.",
	"  test-coverage <package-path>      Check exports have colocated test files.",
	"",
	"Options:",
	"  --config <path>         Check config JSON (default: <package-path>/quality.config.json).",
	"",
	"Examples:",
	"  pkg-checks exports ./packages/helpers",
	"  pkg-checks exports ~/Dev/Repositories/Packages/components --config ./quality.config.json",
	"  pkg-checks runtime-deps ~/Dev/Repositories/Packages/helpers --config ./quality.config.json",
	"  pkg-checks size ~/Dev/Repositories/Packages/helpers --config ./quality.config.json",
	"  pkg-checks type-declarations ~/Dev/Repositories/Packages/helpers",
	"  pkg-checks test-coverage ~/Dev/Repositories/Packages/helpers",
].join("\n");

// The next step shown when a package has runtime dependencies that are not
// allowed.
const RUNTIME_DEPENDENCY_HINT =
	"Move runtime dependencies to devDependencies, or document the exception in ALLOWED_DEPS.";

// The next step shown when exported names have no type declaration.
const TYPE_DECLARATIONS_HINT = "Add the missing declarations to the types file before committing.";
// The next step shown when exported helpers have no test file.
const TEST_COVERAGE_HINT = "Add a test file for each helper before pushing.";

// The heading shown for each kind of export check.
const exportModeLabels = {
	"barrel-coverage": "Barrel coverage",
	"exports-map": "Exports map",
};

/**
 * Report one check result as failure rows with an optional hint, or a success
 * status.
 *
 * @param  {object}  result
 *     Check result to report.
 * @param  {object}  options
 *     CLI styling options.
 * @param  {object}  resultLabels
 *     Labels and optional guidance for the rendered result.
 * @param  {string}  resultLabels.failed
 *     Label shown when the check fails.
 * @param  {string}  resultLabels.success
 *     Label shown when the check passes.
 * @param  {string}  [resultLabels.hintText]
 *     Optional guidance shown below failure rows.
 *
 * @returns  {void}
 *     Nothing.
 */
function reportCheckResult(result, options, { failed, success, hintText }) {
	if (result.failures.length > 0) {
		// The rendered failure lines.
		const lines = [status("failed", "", { ...options, label: failed })];

		for (const failure of result.failures) {
			lines.push(row(failure.target, failure.reason, { ...options, result: "failed" }));
		}

		if (hintText) {
			lines.push(hint(hintText, options));
		}

		console.error(lines.join("\n"));

		return;
	}

	process.stdout.write(`${status("success", "", { ...options, label: success })}\n`);
}

/**
 * Resolve the check configuration path.
 *
 * @param  {string}  packagePath
 *     Package directory path.
 * @param  {string[]}  argumentsList
 *     Arguments following the package path.
 *
 * @throws  {Error}
 *     When an unsupported or incomplete option is provided.
 *
 * @returns  {string}
 *     Resolved configuration path.
 */
function getConfigPath(packagePath, argumentsList) {
	// The optional configuration path.
	let configPath;

	for (let index = 0; index < argumentsList.length; index += 1) {
		if (argumentsList[index] !== "--config") {
			throw new Error("Expected --config <path> after the package directory.");
		}

		// The path following the --config option.
		const nextArgument = argumentsList[index + 1];

		if (!nextArgument || nextArgument.startsWith("-")) {
			throw new Error("Expected a path after --config.");
		}

		if (configPath) {
			throw new Error("Only one --config path is supported.");
		}

		configPath = nextArgument;
		index += 1;
	}

	return resolve(configPath ?? join(packagePath, "quality.config.json"));
}

// Each command's options and the function that runs it.
const commands = {
	exports: {
		needsConfig: true,
		report: (result, options) => {
			for (const modeResult of result.results) {
				// The label for the current export check mode.
				const label = exportModeLabels[modeResult.mode];

				reportCheckResult(modeResult, options, {
					failed: `${label} failed`,
					success: `${label} passed (${modeResult.checked} checked).`,
				});
			}
		},
		run: async (packagePath, configPath) => {
			// The validated exports configuration.
			const config = await readExportsConfig(configPath);

			return runExportsCheck(packagePath, config);
		},
	},
	"runtime-deps": {
		needsConfig: true,
		report: (result, options) => {
			reportCheckResult(result, options, {
				failed: "Unexpected runtime dependency found",
				hintText: RUNTIME_DEPENDENCY_HINT,
				success: "Runtime dependencies are approved",
			});
		},
		run: async (packagePath, configPath) => {
			// The validated runtime dependency configuration.
			const config = await readRuntimeDependencyConfig(configPath);

			return runRuntimeDependencyCheck(packagePath, config);
		},
	},
	size: {
		needsConfig: true,
		report: (result, options) => {
			for (const budgetResult of result.results) {
				reportCheckResult(budgetResult, options, {
					failed: `${budgetResult.name} failed`,
					success: `${budgetResult.name} passed (${budgetResult.checked} checked).`,
				});
			}
		},
		run: async (packagePath, configPath) => {
			// The validated size configuration.
			const config = await readSizeConfig(configPath);

			return runSizeCheck(packagePath, config);
		},
	},
	"test-coverage": {
		report: (result, options) => {
			// The single coverage result.
			const [checkResult] = result.results;

			reportCheckResult(checkResult, options, {
				failed: "Test coverage check failed",
				hintText: TEST_COVERAGE_HINT,
				success: `Test coverage passed (${checkResult.checked} checked).`,
			});
		},
		run: (packagePath) => runTestCoverageCheck(packagePath),
	},
	"type-declarations": {
		report: (result, options) => {
			// The single type declaration result.
			const [checkResult] = result.results;

			reportCheckResult(checkResult, options, {
				failed: "Type declaration check failed",
				hintText: TYPE_DECLARATIONS_HINT,
				success: `Type declarations passed (${checkResult.checked} checked).`,
			});
		},
		run: (packagePath) => runTypeDeclarationsCheck(packagePath),
	},
};

/**
 * Report a usage error for a command and print the usage text.
 *
 * @param  {string}  command
 *     Command that was invoked.
 * @param  {object}  options
 *     CLI styling options.
 *
 * @returns  {void}
 *     Nothing.
 */
function reportUsageError(command, options) {
	console.error(
		status("failed", "", { ...options, label: `Expected one package directory after ${command}.` }),
	);
	console.error(`\n${usage}`);
}

/**
 * Run the package-checks command-line interface.
 *
 * @param  {string[]}  argumentsList
 *     Command-line arguments excluding the executable.
 *
 * @returns  {Promise<number>}
 *     Process exit code.
 */
export async function runCli(argumentsList) {
	// The configured command-line styling options.
	const ui = createCliStyle({
		argv: argumentsList,
		env: process.env,
		stdout: process.stdout,
	});

	if (
		argumentsList.length === 0 ||
		argumentsList.includes("--help") ||
		argumentsList.includes("-h")
	) {
		process.stdout.write(`${usage}\n`);

		return 0;
	}

	// The command, package path, and extra arguments.
	const [command, packagePath, ...extraArguments] = argumentsList;
	// The handler for the requested command.
	const commandDefinition = Object.hasOwn(commands, command) ? commands[command] : undefined;

	if (!commandDefinition) {
		console.error(status("failed", "", { ...ui.options, label: `Unknown command: ${command}` }));
		console.error(`\n${usage}`);

		return 1;
	}

	if (!packagePath || packagePath.startsWith("-")) {
		reportUsageError(command, ui.options);

		return 1;
	}

	if (!commandDefinition.needsConfig && extraArguments.length > 0) {
		reportUsageError(command, ui.options);

		return 1;
	}

	try {
		// The check configuration path, when the command needs one.
		const configPath = commandDefinition.needsConfig
			? getConfigPath(packagePath, extraArguments)
			: undefined;

		// The completed check result.
		const result = await commandDefinition.run(packagePath, configPath);

		commandDefinition.report(result, ui.options);

		return result.failures.length > 0 ? 1 : 0;
	} catch (error) {
		// The user-facing error message.
		const message = error instanceof Error ? error.message : String(error);

		console.error(status("failed", "", { ...ui.options, label: `pkg-checks: ${message}` }));

		return 1;
	}
}

if (import.meta.main) {
	process.exit(await runCli(process.argv.slice(2)));
}
