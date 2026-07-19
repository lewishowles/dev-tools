import { createCliStyle, row, status } from "@lewishowles/cli-style";

import {
	runExportsCheck,
	type ExportCheckMode,
	type ExportModeResult,
} from "./checks/exports.ts";

const usage = [
	"Usage: pkg-checks <command> <package-path>",
	"",
	"Commands:",
	"  exports <package-path>  Check category barrels and package.json exports.",
	"",
	"Examples:",
	"  pkg-checks exports ./packages/helpers",
	"  pkg-checks exports ~/Dev/Repositories/Packages/components",
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

	if (command !== "exports") {
		console.error(status("failed", "", { ...ui.options, label: `Unknown command: ${command}` }));
		console.error(`\n${usage}`);

		return 1;
	}

	if (!packagePath || packagePath.startsWith("-") || extraArguments.length > 0) {
		console.error(status("failed", "", { ...ui.options, label: "Expected one package directory after exports." }));
		console.error(`\n${usage}`);

		return 1;
	}

	try {
		const result = await runExportsCheck(packagePath);

		for (const modeResult of result.results) {
			reportMode(modeResult, ui.options);
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
