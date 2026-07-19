import { expect, test } from "bun:test";
import { loadPage } from "../src/load.ts";
import { resolve } from "node:path";
import { runAriaLabelChecks } from "../src/checks/aria-labels.ts";
import { runCli } from "../src/cli.ts";

interface CapturedCliOutput {
	exitCode: number;
	stderr: string;
	stdout: string;
}

/**
 * Resolve a checked-in web-audit fixture by filename.
 *
 * @param  {string}  filename
 *     Fixture filename relative to the package fixtures directory.
 * @returns  {string}
 *     Absolute fixture path.
 */
function fixturePath(filename: string): string {
	return resolve(import.meta.dir, "../fixtures", filename);
}

/**
 * Run the CLI while capturing its stream output for assertions.
 *
 * @param  {string[]}  argumentsList
 *     Arguments passed to runCli.
 * @returns  {Promise<CapturedCliOutput>}
 *     Exit code and captured stdout/stderr.
 */
async function captureCli(argumentsList: string[]): Promise<CapturedCliOutput> {
	const stdout: string[] = [];
	const stderr: string[] = [];
	const originalStdoutWrite = process.stdout.write;
	const originalStderrWrite = process.stderr.write;
	const originalConsoleLog = console.log;
	const originalConsoleError = console.error;

	process.stdout.write = ((chunk: string | Uint8Array) => {
		stdout.push(typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk));

		return true;
	}) as typeof process.stdout.write;
	process.stderr.write = ((chunk: string | Uint8Array) => {
		stderr.push(typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk));

		return true;
	}) as typeof process.stderr.write;
	console.log = (...argumentsList: unknown[]) => {
		stdout.push(`${argumentsList.map(String).join(" ")}\n`);
	};
	console.error = (...argumentsList: unknown[]) => {
		stderr.push(`${argumentsList.map(String).join(" ")}\n`);
	};

	try {
		const exitCode = await runCli(argumentsList);

		return { exitCode, stderr: stderr.join(""), stdout: stdout.join("") };
	} finally {
		process.stdout.write = originalStdoutWrite;
		process.stderr.write = originalStderrWrite;
		console.log = originalConsoleLog;
		console.error = originalConsoleError;
	}
}

test("ARIA checks report prohibited labels on static text", async () => {
	const loadedPage = await loadPage(fixturePath("aria-label-wrong-element.html"));

	try {
		const violations = await runAriaLabelChecks(loadedPage.page);

		expect(violations).toEqual([
			{
				id: "aria-prohibited-name",
				impact: "serious",
				target: "span",
			},
		]);
	} finally {
		await loadedPage.browser.close();
	}
});

test("CLI reports axe findings, keeps documented exit codes, and renders JavaScript content", async () => {
	const missingAltText = await captureCli([
		"scan-site",
		fixturePath("missing-alt-text.html"),
	]);

	expect(missingAltText.exitCode).toBe(0);
	expect(missingAltText.stdout).toContain("image-alt");
	expect(missingAltText.stdout).toContain("(critical) img");

	const multipleMissingAltText = await captureCli([
		"scan-site",
		fixturePath("multiple-missing-alt-text.html"),
	]);

	expect(multipleMissingAltText.exitCode).toBe(0);
	expect(multipleMissingAltText.stdout.match(/image-alt/g)).toHaveLength(2);

	const cleanPage = await captureCli(["scan-site", fixturePath("sample.html")]);

	expect(cleanPage.exitCode).toBe(0);
	expect(cleanPage.stdout).toContain("No accessibility violations found.");

	const renderedPage = await captureCli([
		"render",
		fixturePath("js-rendered.html"),
		"--selector",
		"main",
	]);

	expect(renderedPage.exitCode).toBe(0);
	expect(renderedPage.stdout).toContain("<main>");
	expect(renderedPage.stdout).toContain("<h1>Rendered fixture</h1>");
	expect(renderedPage.stdout).not.toContain("Loading page content...");
});
