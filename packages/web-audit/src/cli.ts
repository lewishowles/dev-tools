import { loadPage } from "./load.ts";

const usage = [
	"Usage: web-audit scan-site <url-or-html-file>",
	"",
	"Load a page and confirm its DOM can be read.",
	"",
	"Examples:",
	"  web-audit scan-site https://example.com",
	"  web-audit scan-site ./fixtures/sample.html",
].join("\n");

/**
 * Run the web-audit command line interface.
 *
 * @param  {string[]}  argumentsList
 *     Command-line arguments without the executable name.
 * @returns  {Promise<number>}
 *     Process exit code.
 */
export async function runCli(argumentsList: string[]): Promise<number> {
	if (argumentsList.length === 0 || argumentsList.includes("--help") || argumentsList.includes("-h")) {
		console.log(usage);

		return 0;
	}

	const [command, source, ...extraArguments] = argumentsList;

	if (command !== "scan-site") {
		console.error(`Unknown command: ${command}\n\n${usage}`);

		return 1;
	}

	if (!source || extraArguments.length > 0) {
		console.error(`Expected one URL or HTML file after scan-site.\n\n${usage}`);

		return 1;
	}

	try {
		const loadedPage = await loadPage(source);

		try {
			const elementCount = await loadedPage.page.locator("*").count();

			console.log(`Loaded DOM: ${source} (${elementCount} elements)`);
		} finally {
			await loadedPage.browser.close();
		}

		return 0;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);

		console.error(`web-audit: ${message}`);

		return 1;
	}
}

if (import.meta.main) {
	process.exit(await runCli(process.argv.slice(2)));
}
