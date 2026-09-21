import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { chromium } from "playwright";

/**
 * Return an HTTP or HTTPS URL when source is a web address.
 *
 * @param  {string}  source
 *     The page address or local HTML path supplied by the user.
 *
 * @returns  {URL|null}
 *     The parsed HTTP(S) URL, or null for a local file path.
 */
function getWebUrl(source) {
	try {
		// The parsed source URL.
		const url = new URL(source);

		if (url.protocol === "http:" || url.protocol === "https:") {
			return url;
		}
	} catch {
		return null;
	}

	return null;
}

/**
 * Load a web page or static HTML file into a Playwright page.
 *
 * @param  {string}  source
 *     The HTTP(S) URL or local HTML file to load.
 *
 * @throws  {Error}
 *     When the source is not a reachable URL or existing HTML file.
 *
 * @returns  {Promise<LoadedPage>}
 *     The browser, page, and original source. The caller owns browser cleanup.
 */
export async function loadPage(source) {
	// The HTTP(S) URL, when the source is a web address.
	const webUrl = getWebUrl(source);
	// The browser used to load the source.
	const browser = await chromium.launch();

	try {
		// The isolated browser context.
		const context = await browser.newContext();
		// The page that receives the source content.
		const page = await context.newPage();

		if (webUrl) {
			await page.goto(webUrl.href, { waitUntil: "domcontentloaded" });
		} else {
			// The absolute local HTML path.
			const filePath = resolve(source);

			if (!existsSync(filePath)) {
				throw new Error(`Expected an HTTP(S) URL or an existing HTML file: ${source}`);
			}

			// The local HTML source.
			const html = await readFile(filePath, "utf8");

			await page.setContent(html, { waitUntil: "domcontentloaded" });
		}

		return { browser, page, source };
	} catch (error) {
		await browser.close();

		throw error;
	}
}
