/**
 * Run custom ARIA label validity checks against an already-loaded page.
 *
 * @param  {Page}  page
 *     Playwright page containing the document to audit.
 * @param  {string[]}  axeTargets
 *     Selectors already reported by axe, used to avoid duplicate missing-name findings.
 * @returns  {Promise<AriaLabelViolation[]>}
 *     Custom violations with rule IDs, impacts, and affected selectors.
 */
export async function runAriaLabelChecks(page, axeTargets = []) {
	return page.evaluate(
		({ axeTargets: coveredTargets }) => {
			const prohibitedNameRoles = new Set([
				"caption",
				"code",
				"deletion",
				"emphasis",
				"generic",
				"insertion",
				"paragraph",
				"presentation",
				"strong",
				"subscript",
				"superscript",
			]);

			const requiredNameRoles = new Set([
				"alertdialog",
				"application",
				"button",
				"checkbox",
				"columnheader",
				"combobox",
				"dialog",
				"grid",
				"heading",
				"img",
				"link",
				"listbox",
				"meter",
				"marquee",
				"menuitem",
				"menuitemcheckbox",
				"menuitemradio",
				"option",
				"progressbar",
				"radio",
				"radiogroup",
				"region",
				"rowheader",
				"searchbox",
				"slider",
				"spinbutton",
				"switch",
				"table",
				"tabpanel",
				"textbox",
				"tooltip",
				"tree",
				"treegrid",
				"treeitem",
			]);

			const contentNameRoles = new Set([
				"button",
				"cell",
				"checkbox",
				"columnheader",
				"gridcell",
				"heading",
				"link",
				"menuitem",
				"menuitemcheckbox",
				"menuitemradio",
				"option",
				"radio",
				"row",
				"rowheader",
				"switch",
				"tab",
				"tooltip",
				"treeitem",
			]);

			const implicitRoles = {
				caption: "caption",
				code: "code",
				del: "deletion",
				div: "generic",
				em: "emphasis",
				figcaption: "caption",
				ins: "insertion",
				p: "paragraph",
				span: "generic",
				strong: "strong",
				sub: "subscript",
				sup: "superscript",
			};

			const violations = [];

			const getRole = (element) => {
				const explicitRole = element.getAttribute("role")?.trim().split(/\s+/)[0];

				return (
					explicitRole?.toLowerCase() ||
					implicitRoles[element.tagName.toLowerCase()] ||
					null
				);
			};

			const getSelector = (element) => {
				const id = element.getAttribute("id");

				if (id) {
					return `#${CSS.escape(id)}`;
				}

				const tagName = element.tagName.toLowerCase();
				const parent = element.parentElement;

				if (!parent) {
					return tagName;
				}

				const sameTagSiblings = Array.from(parent.children).filter(
					(sibling) => sibling.tagName === element.tagName,
				);

				if (sameTagSiblings.length === 1) {
					return tagName;
				}

				return `${tagName}:nth-of-type(${sameTagSiblings.indexOf(element) + 1})`;
			};

			const addViolation = (id, element) => {
				violations.push({
					id,
					impact: "serious",
					target: getSelector(element),
				});
			};

			const getLabelledbyReferences = (element) => {
				const labelledby = element.getAttribute("aria-labelledby") ?? "";

				return labelledby
					.trim()
					.split(/\s+/)
					.filter(Boolean)
					.map((id) => document.getElementById(id))
					.filter((referencedElement) => referencedElement !== null);
			};

			const hasAccessibleName = (element, role) => {
				if (element.getAttribute("aria-label")?.trim()) {
					return true;
				}

				if (
					getLabelledbyReferences(element).some((referencedElement) =>
						referencedElement.textContent?.trim(),
					)
				) {
					return true;
				}

				if (element.getAttribute("title")?.trim()) {
					return true;
				}

				if (role === "img" && element.getAttribute("alt")?.trim()) {
					return true;
				}

				return contentNameRoles.has(role) && Boolean(element.textContent?.trim());
			};

			const isCoveredByAxe = (element) =>
				coveredTargets.some((selector) => {
					try {
						return element.matches(selector);
					} catch {
						return false;
					}
				});

			for (const element of Array.from(document.querySelectorAll("*"))) {
				const role = getRole(element);
				const ariaLabel = element.getAttribute("aria-label");
				const ariaLabelledby = element.getAttribute("aria-labelledby");

				if (
					role &&
					prohibitedNameRoles.has(role) &&
					(ariaLabel !== null || ariaLabelledby !== null)
				) {
					addViolation("aria-prohibited-name", element);
				}

				if (ariaLabel !== null && !ariaLabel.trim()) {
					addViolation("aria-empty-label", element);
				}

				if (ariaLabelledby !== null) {
					const referencedIds = ariaLabelledby.trim().split(/\s+/).filter(Boolean);

					if (referencedIds.some((id) => !document.getElementById(id))) {
						addViolation("aria-labelledby-missing-target", element);
					}

					if (
						referencedIds.some((id) => {
							const referencedElement = document.getElementById(id);

							return referencedElement !== null && !referencedElement.textContent?.trim();
						})
					) {
						addViolation("aria-labelledby-empty-text", element);
					}
				}

				const explicitRole = element.getAttribute("role")?.trim();

				if (
					explicitRole &&
					role &&
					requiredNameRoles.has(role) &&
					!isCoveredByAxe(element) &&
					!hasAccessibleName(element, role)
				) {
					addViolation("aria-missing-name", element);
				}
			}

			return violations;
		},
		{ axeTargets },
	);
}
