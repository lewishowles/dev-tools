import { join, resolve } from "node:path";
import { createCliStyle, hint, row, status } from "@lewishowles/cli-style";
import { runExportsCheck } from "./checks/exports.js";
import { readRuntimeDependencyConfig, runRuntimeDependencyCheck } from "./checks/runtime-deps.js";
import { readSizeConfig, runSizeCheck } from "./checks/size.js";
import { runTypeDeclarationsCheck } from "./checks/type-declarations.js";

// Usage text shared by help and argument errors.
const usage = [
	"Usage: pkg-checks <command> <package-path>",
	"",
	"Commands:",
	"  exports <package-path>       Check category barrels and package.json exports.",
	"  runtime-deps <package-path>  Check configured runtime dependency policy.",
	"  size <package-path>          Check configured package size budgets.",
	"  type-declarations <package-path>  Check exports have matching type declarations.",
	"",
	"Options:",
	"  --config <path>         Check config JSON (default: <package-path>/quality.config.json).",
	"",
	"Examples:",
	"  pkg-checks exports ./packages/helpers",
	"  pkg-checks exports ~/Dev/Repositories/Packages/components",
	"  pkg-checks runtime-deps ~/Dev/Repositories/Packages/helpers --config ./quality.config.json",
	"  pkg-checks size ~/Dev/Repositories/Packages/helpers --config ./quality.config.json",
	"  pkg-checks type-declarations ~/Dev/Repositories/Packages/helpers",
].join("\n");

// Guidance shown when runtime dependencies violate the configured policy.
const RUNTIME_DEPENDENCY_HINT =
	"Move runtime dependencies to devDependencies, or document the exception in ALLOWED_DEPS.";

/**
 * Describe a check mode for human-readable CLI output.
 *
 * @param  {string}  mode
 *     Check mode to describe.
 * @returns  {string}
 *     Human-readable mode label.
 */
function modeLabel(mode) {
	return mode === "barrel-coverage" ? "Barrel coverage" : "Exports map";
}

/**
 * Report the result of an export check mode.
 *
 * @param  {object}  result
 *     Export check result to report.
 * @param  {object}  options
 *     CLI styling options.
 * @returns  {void}
 *     Nothing.
 */
function reportMode(result, options) {
	const label = modeLabel(result.mode);

	if (result.failures.length > 0) {
		console.error(
			status("failed", "", {
				...options,
				label: `${label} failed`,
			}),
		);
		for (const failure of result.failures) {
			console.error(
				row(failure.target, failure.reason, {
					...options,
					result: "failed",
				}),
			);
		}

		return;
	}

	console.log(
		status("success", "", {
			...options,
			label: `${label} passed (${result.checked} checked).`,
		}),
	);
}

/**
 * Report the result of a size budget check.
 *
 * @param  {object}  result
 *     Size budget result to report.
 * @param  {object}  options
 *     CLI styling options.
 * @returns  {void}
 *     Nothing.
 */
function reportSizeBudget(result, options) {
	if (result.failures.length > 0) {
		console.error(
			status("failed", "", {
				...options,
				label: `${result.name} failed`,
			}),
		);
		for (const failure of result.failures) {
			console.error(
				row(failure.target, failure.reason, {
					...options,
					result: "failed",
				}),
			);
		}

		return;
	}

	console.log(
		status("success", "", {
			...options,
			label: `${result.name} passed (${result.checked} checked).`,
		}),
	);
}

/**
 * Report the runtime dependency policy result.
 *
 * @param  {object}  result
 *     Runtime dependency result to report.
 * @param  {object}  options
 *     CLI styling options.
 * @returns  {void}
 *     Nothing.
 */
function reportRuntimeDependencies(result, options) {
	if (result.failures.length > 0) {
		console.error(
			status("failed", "", {
				...options,
				label: "Unexpected runtime dependency found",
			}),
		);

		for (const failure of result.failures) {
			console.error(
				row(failure.target, failure.reason, {
					...options,
					result: "failed",
				}),
			);
		}

		console.error(hint(RUNTIME_DEPENDENCY_HINT, options));

		return;
	}

	console.log(
		status("success", "", {
			...options,
			label: "Runtime dependencies are approved",
		}),
	);
}

/**
 * Report the type declarations check result.
 *
 * @param  {object}  result
 *     Type declarations result to report.
 * @param  {object}  options
 *     CLI styling options.
 * @returns  {void}
 *     Nothing.
 */
function reportTypeDeclarations(result, options) {
	if (result.failures.length > 0) {
		console.error(
			status("failed", "", {
				...options,
				label: "Type declaration check failed",
			}),
		);
		for (const failure of result.failures) {
			console.error(
				row(failure.target, failure.reason, {
					...options,
					result: "failed",
				}),
			);
		}

		return;
	}

	console.log(
		status("success", "", {
			...options,
			label: `Type declarations passed (${result.checked} checked).`,
		}),
	);
}

/**
 * Resolve the check configuration path.
 *
 * @param  {string}  packagePath
 *     Package directory path.
 * @param  {string[]}  argumentsList
 *     Arguments following the package path.
 * @returns  {string}
 *     Resolved configuration path.
 */
function getConfigPath(packagePath, argumentsList) {
	let configPath;

	for (let index = 0; index < argumentsList.length; index += 1) {
		if (argumentsList[index] !== "--config") {
			throw new Error("Expected --config <path> after the package directory.");
		}

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

/**
 * Run the package-checks command-line interface.
 *
 * @param  {string[]}  argumentsList
 *     Command-line arguments excluding the executable.
 * @returns  {Promise<number>}
 *     Process exit code.
 */
export async function runCli(argumentsList) {
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
		console.log(usage);

		return 0;
	}

	const [command, packagePath, ...extraArguments] = argumentsList;

	if (
		command !== "exports" &&
		command !== "runtime-deps" &&
		command !== "size" &&
		command !== "type-declarations"
	) {
		console.error(status("failed", "", { ...ui.options, label: `Unknown command: ${command}` }));
		console.error(`
${usage}`);

		return 1;
	}

	if (!packagePath || packagePath.startsWith("-")) {
		console.error(
			status("failed", "", {
				...ui.options,
				label: `Expected one package directory after ${command}.`,
			}),
		);
		console.error(`
${usage}`);

		return 1;
	}

	try {
		if (command === "exports") {
			if (extraArguments.length > 0) {
				console.error(
					status("failed", "", {
						...ui.options,
						label: "Expected one package directory after exports.",
					}),
				);
				console.error(`
${usage}`);

				return 1;
			}

			const result = await runExportsCheck(packagePath);

			for (const modeResult of result.results) {
				reportMode(modeResult, ui.options);
			}

			return result.failures.length > 0 ? 1 : 0;
		}

		if (command === "type-declarations") {
			if (extraArguments.length > 0) {
				console.error(
					status("failed", "", {
						...ui.options,
						label: "Expected one package directory after type-declarations.",
					}),
				);
				console.error(`
${usage}`);

				return 1;
			}

			const result = await runTypeDeclarationsCheck(packagePath);

			reportTypeDeclarations(result.results[0], ui.options);

			return result.failures.length > 0 ? 1 : 0;
		}

		const configPath = getConfigPath(packagePath, extraArguments);

		if (command === "runtime-deps") {
			const config = await readRuntimeDependencyConfig(configPath);
			const result = await runRuntimeDependencyCheck(packagePath, config);

			reportRuntimeDependencies(result, ui.options);

			return result.failures.length > 0 ? 1 : 0;
		}

		const config = await readSizeConfig(configPath);
		const result = await runSizeCheck(packagePath, config);

		for (const budgetResult of result.results) {
			reportSizeBudget(budgetResult, ui.options);
		}

		return result.failures.length > 0 ? 1 : 0;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);

		console.error(status("failed", "", { ...ui.options, label: `pkg-checks: ${message}` }));

		return 1;
	}
}

if (import.meta.main) {
	process.exit(await runCli(process.argv.slice(2)));
}
