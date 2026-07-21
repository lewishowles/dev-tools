import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { chromium } from "playwright";

/**
 * Return an HTTP or HTTPS URL when source is a web address.
 *
 * @param  {string}  source
 *     The page address or local HTML path supplied by the user.
 */
function getWebUrl(source) {
	try {
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
 * @returns  {Promise<LoadedPage>}
 *     The browser, page, and original source. The caller owns browser cleanup.
 */
export async function loadPage(source) {
	const webUrl = getWebUrl(source);
	const browser = await chromium.launch();

	try {
		const context = await browser.newContext();
		const page = await context.newPage();

		if (webUrl) {
			await page.goto(webUrl.href, { waitUntil: "domcontentloaded" });
		} else {
			const filePath = resolve(source);

			if (!existsSync(filePath)) {
				throw new Error(`Expected an HTTP(S) URL or an existing HTML file: ${source}`);
			}

			const html = await readFile(filePath, "utf8");

			await page.setContent(html, { waitUntil: "domcontentloaded" });
		}

		return { browser, page, source };
	} catch (error) {
		await browser.close();

		throw error;
	}
}
