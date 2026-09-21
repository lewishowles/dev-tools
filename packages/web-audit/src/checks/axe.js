import AxeBuilder from "@axe-core/playwright";

/**
 * Run the axe-core baseline against an already-loaded page.
 *
 * @param  {Page}  page
 *     Playwright page containing the document to audit.
 *
 * @returns  {Promise<AxeViolation[]>}
 *     Violations with their rule IDs, impacts, and affected selectors.
 */
export async function runAxe(page) {
	// Use the axe-core results to report each affected node.
	const results = await new AxeBuilder({ page }).analyze();

	return results.violations.flatMap((violation) =>
		violation.nodes.map((node) => ({
			id: violation.id,
			impact: violation.impact ?? "unknown",
			// Axe targets can hold nested arrays for shadow-DOM or iframe
			// selectors, and these are still comma-joined.
			target: node.target.map((target) => target.toString()).join(" "),
		})),
	);
}
