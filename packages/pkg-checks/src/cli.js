import { join, resolve } from "node:path";
import { createCliStyle, row, status } from "@lewishowles/cli-style";
import { runExportsCheck } from "./checks/exports.js";
import { readSizeConfig, runSizeCheck } from "./checks/size.js";

// Usage text shared by help and argument errors.
const usage = [
	"Usage: pkg-checks <command> <package-path>",
	"",
	"Commands:",
	"  exports <package-path>  Check category barrels and package.json exports.",
	"  size <package-path>     Check configured package size budgets.",
	"",
	"Options:",
	"  --config <path>         Size budget JSON (default: <package-path>/quality.config.json).",
	"",
	"Examples:",
	"  pkg-checks exports ./packages/helpers",
	"  pkg-checks exports ~/Dev/Repositories/Packages/components",
	"  pkg-checks size ~/Dev/Repositories/Packages/helpers --config ./quality.config.json",
].join("\n");

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
 * Resolve the size budget configuration path.
 *
 * @param  {string}  packagePath
 *     Package directory path.
 * @param  {string[]}  argumentsList
 *     Arguments following the size package path.
 * @returns  {string}
 *     Resolved configuration path.
 */
function getSizeConfigPath(packagePath, argumentsList) {
	let configPath;

	for (let index = 0; index < argumentsList.length; index += 1) {
		if (argumentsList[index] !== "--config") {
			throw new Error("Expected --config <path> after the size package directory.");
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

	if (command !== "exports" && command !== "size") {
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

		const configPath = getSizeConfigPath(packagePath, extraArguments);
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
