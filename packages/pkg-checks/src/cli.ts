import { join, resolve } from "node:path";

import { createCliStyle, row, status } from "@lewishowles/cli-style";

import {
	runExportsCheck,
	type ExportCheckMode,
	type ExportModeResult,
} from "./checks/exports.ts";
import {
	readSizeConfig,
	runSizeCheck,
	type SizeBudgetResult,
} from "./checks/size.ts";

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
 * @param  {ExportCheckMode}  mode
 *     Check mode to describe.
 * @returns  {string}
 *     Human-readable mode label.
 */
function modeLabel(mode: ExportCheckMode): string {
	return mode === "barrel-coverage" ? "Barrel coverage" : "Exports map";
}

/**
 * Print one mode's result and failures.
 *
 * @param  {ExportModeResult}  result
 *     Mode result to report.
 * @param  {ReturnType<typeof createCliStyle>["options"]}  options
 *     CLI output options.
 */
function reportMode(
	result: ExportModeResult,
	options: ReturnType<typeof createCliStyle>["options"],
): void {
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
 * Print one size budget's result and failures.
 *
 * @param  {SizeBudgetResult}  result
 *     Size budget result to report.
 * @param  {ReturnType<typeof createCliStyle>["options"]}  options
 *     CLI output options.
 */
function reportSizeBudget(
	result: SizeBudgetResult,
	options: ReturnType<typeof createCliStyle>["options"],
): void {
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
 * Resolve the size budget configuration path from CLI options.
 *
 * @param  {string}  packagePath
 *     Package path used for the default configuration location.
 * @param  {string[]}  argumentsList
 *     Arguments after the package path.
 * @returns  {string}
 *     Absolute configuration path.
 */
function getSizeConfigPath(packagePath: string, argumentsList: string[]): string {
	let configPath: string | undefined;

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
 * Run the pkg-checks command line interface.
 *
 * @param  {string[]}  argumentsList
 *     Command-line arguments without the executable name.
 * @returns  {Promise<number>}
 *     Process exit code.
 */
export async function runCli(argumentsList: string[]): Promise<number> {
	const ui = createCliStyle({
		argv: argumentsList,
		env: process.env,
		stdout: process.stdout,
	});

	if (argumentsList.length === 0 || argumentsList.includes("--help") || argumentsList.includes("-h")) {
		console.log(usage);

		return 0;
	}

	const [command, packagePath, ...extraArguments] = argumentsList;

	if (command !== "exports" && command !== "size") {
		console.error(status("failed", "", { ...ui.options, label: `Unknown command: ${command}` }));
		console.error(`\n${usage}`);

		return 1;
	}

	if (!packagePath || packagePath.startsWith("-")) {
		console.error(
			status("failed", "", {
				...ui.options,
				label: `Expected one package directory after ${command}.`,
			}),
		);
		console.error(`\n${usage}`);

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
				console.error(`\n${usage}`);

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
