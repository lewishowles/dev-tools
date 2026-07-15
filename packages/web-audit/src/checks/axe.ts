import AxeBuilder from "@axe-core/playwright";
import type { Page } from "playwright";

export interface AxeViolation {
	id: string;
	impact: string;
	target: string;
}

/**
 * Run the axe-core baseline against an already-loaded page.
 *
 * @param  {Page}  page
 *     Playwright page containing the document to audit.
 * @returns  {Promise<AxeViolation[]>}
 *     Violations with their rule IDs, impacts, and affected selectors.
 */
export async function runAxe(page: Page): Promise<AxeViolation[]> {
	const results = await new AxeBuilder({ page }).analyze();

	return results.violations.flatMap((violation) =>
		violation.nodes.map((node) => ({
			id: violation.id,
			impact: violation.impact ?? "unknown",
			// Axe targets can contain nested arrays for shadow-DOM or iframe selectors; toString() comma-joins them silently for now.
			target: node.target.map((target) => target.toString()).join(" "),
		})),
	);
}
