#!/usr/bin/env node
import { createCliStyle, row, status } from "@lewishowles/cli-style";

import { runAriaLabelChecks } from "./checks/aria-labels.js";
import { runAxe } from "./checks/axe.js";
import { loadPage } from "./load.js";
import { renderPage } from "./render.js";

const usage = [
	"Usage: web-audit <command> <url-or-html-file>",
	"",
	"Commands:",
	"  scan-site <url-or-html-file>  Check a page for accessibility violations.",
	"  render <url> [--selector <css-selector>]  Print rendered HTML.",
	"",
	"Examples:",
	"  web-audit scan-site https://example.com",
	"  web-audit scan-site ./fixtures/sample.html",
	"  web-audit render https://example.com",
].join("\n");

/**
 * Map a violation's impact/severity to a cli-style result tone.
 *
 * @param  {string}  impact
 *     Violation impact, e.g. "critical", "serious", "moderate", "minor".
 */
function toneForImpact(impact) {
	return impact === "critical" || impact === "serious" ? "failed" : "warning";
}

/**
 * Run the render command and keep rendered HTML clean for stdout consumers.
 *
 * @param  {string[]}  argumentsList
 *     Command-line arguments after the render command.
 * @param  {object}  ui
 *     CLI styling instance.
 * @returns  {Promise<number>}
 *     Process exit code.
 */
async function runRender(argumentsList, ui) {
	const [source, ...options] = argumentsList;

	let selector;

	for (let index = 0; index < options.length; index += 1) {
		if (options[index] !== "--selector" || !options[index + 1]) {
			console.error(
				status("failed", "", { label: "Expected --selector followed by a CSS selector." }),
			);

			return 1;
		}

		selector = options[index + 1];
		index += 1;
	}

	if (!source || source.startsWith("-")) {
		console.error(status("failed", "", { label: "Expected one URL after render." }));

		return 1;
	}

	try {
		const renderedHtml = await ui.spinner.run("Rendering page", () =>
			renderPage(source, { selector }),
		);

		process.stdout.write(renderedHtml);

		return 0;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);

		console.error(status("failed", "", { label: `web-audit: ${message}` }));

		return 1;
	}
}

/**
 * Run the web-audit command line interface.
 *
 * @param  {string[]}  argumentsList
 *     Command-line arguments without the executable name.
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

	const [command, source, ...extraArguments] = argumentsList;

	if (command === "render") {
		return runRender(
			[source, ...extraArguments].filter((argument) => argument !== undefined),
			ui,
		);
	}

	if (command !== "scan-site") {
		console.error(status("failed", "", { ...ui.options, label: `Unknown command: ${command}` }));
		console.error(`\n${usage}`);

		return 1;
	}

	if (!source || extraArguments.length > 0) {
		console.error(
			status("failed", "", {
				...ui.options,
				label: "Expected one URL or HTML file after scan-site.",
			}),
		);
		console.error(`\n${usage}`);

		return 1;
	}

	try {
		const loadedPage = await ui.spinner.run("Loading page", () => loadPage(source));

		try {
			const elementCount = await loadedPage.page.locator("*").count();

			console.log(row("Loaded DOM", `${source} (${elementCount} elements)`, ui.options));

			const axeViolations = await runAxe(loadedPage.page);

			const customViolations = await runAriaLabelChecks(
				loadedPage.page,
				axeViolations.map(({ target }) => target),
			);

			const violations = [
				...axeViolations,
				...customViolations.map((violation) => ({
					...violation,
					id: `custom-${violation.id}`,
				})),
			];

			if (violations.length === 0) {
				console.log(
					status("success", "", { ...ui.options, label: "No accessibility violations found." }),
				);
			} else {
				for (const violation of violations) {
					console.log(
						row(violation.id, `(${violation.impact}) ${violation.target}`, {
							...ui.options,
							result: toneForImpact(violation.impact),
						}),
					);
				}
			}
		} finally {
			await loadedPage.browser.close();
		}

		return 0;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);

		console.error(status("failed", "", { ...ui.options, label: `web-audit: ${message}` }));

		return 1;
	}
}

if (import.meta.main) {
	process.exit(await runCli(process.argv.slice(2)));
}
