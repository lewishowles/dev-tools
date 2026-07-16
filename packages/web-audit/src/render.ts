import type { LoadedPage } from "./load.ts";
import { loadPage } from "./load.ts";

export interface RenderOptions {
	selector?: string;
}

/**
 * Return a page's post-load document HTML.
 *
 * @param  {string}  source
 *     The HTTP(S) URL to render.
 * @param  {RenderOptions}  options
 *     Optional selector that signals render completion.
 * @returns  {Promise<string>}
 *     The document element's serialised HTML.
 */
export async function renderPage(source: string, options: RenderOptions = {}): Promise<string> {
	const loadedPage: LoadedPage = await loadPage(source);

	try {
		if (options.selector) {
			await loadedPage.page.waitForSelector(options.selector);
		} else {
			await loadedPage.page.waitForLoadState("networkidle");
		}

		return await loadedPage.page.evaluate(() => document.documentElement.outerHTML);
	} finally {
		await loadedPage.browser.close();
	}
}
