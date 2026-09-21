/**
 * Run custom ARIA label validity checks against an already-loaded page.
 *
 * @param  {Page}  page
 *     Playwright page containing the document to audit.
 * @param  {string[]}  axeTargets
 *     Selectors already reported by axe, used to avoid duplicate missing-name
 *     findings.
 *
 * @returns  {Promise<AriaLabelViolation[]>}
 *     Custom violations with rule IDs, impacts, and affected selectors.
 */
export async function runAriaLabelChecks(page, axeTargets = []) {
	return page.evaluate(
		({ axeTargets: coveredTargets }) => {
			// Roles that must not receive an accessible name.
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

			// Roles that require an accessible name.
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

			// Roles that may use their text content as an accessible name.
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

			// Implicit roles for elements without an explicit role attribute.
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

			// The custom violations found in the document.
			const violations = [];

			/**
			 * Return the explicit or implicit role for an element.
			 *
			 * @param  {Element}  element
			 *     Element whose role should be read.
			 *
			 * @returns  {string|null}
			 *     The resolved role, or null when the element has none.
			 */
			const getRole = (element) => {
				// The explicit role, when one is present.
				const explicitRole = element.getAttribute("role")?.trim().split(/\s+/)[0];

				return (
					explicitRole?.toLowerCase() ||
					implicitRoles[element.tagName.toLowerCase()] ||
					null
				);
			};

			/**
			 * Return a stable CSS selector for an element.
			 *
			 * @param  {Element}  element
			 *     Element to select.
			 *
			 * @returns  {string}
			 *     A selector that identifies the element.
			 */
			const getSelector = (element) => {
				// The element ID, when one is present.
				const id = element.getAttribute("id");

				if (id) {
					return `#${CSS.escape(id)}`;
				}

				// The element's lower-case tag name.
				const tagName = element.tagName.toLowerCase();
				// The element's parent, used to find sibling positions.
				const parent = element.parentElement;

				if (!parent) {
					return tagName;
				}

				// Siblings with the same tag name.
				const sameTagSiblings = Array.from(parent.children).filter(
					(sibling) => sibling.tagName === element.tagName,
				);

				if (sameTagSiblings.length === 1) {
					return tagName;
				}

				return `${tagName}:nth-of-type(${sameTagSiblings.indexOf(element) + 1})`;
			};

			/**
			 * Add a custom violation for an element.
			 *
			 * @param  {string}  id
			 *     Rule identifier for the violation.
			 * @param  {Element}  element
			 *     Element that caused the violation.
			 */
			const addViolation = (id, element) => {
				violations.push({
					id,
					impact: "serious",
					target: getSelector(element),
				});
			};

			/**
			 * Return elements referenced by aria-labelledby.
			 *
			 * @param  {Element}  element
			 *     Element whose references should be read.
			 *
			 * @returns  {Element[]}
			 *     Referenced elements that exist in the document.
			 */
			const getLabelledbyReferences = (element) => {
				// The space-separated reference IDs.
				const labelledby = element.getAttribute("aria-labelledby") ?? "";

				return labelledby
					.trim()
					.split(/\s+/)
					.filter(Boolean)
					.map((id) => document.getElementById(id))
					.filter((referencedElement) => referencedElement !== null);
			};

			/**
			 * Return whether an element has an accessible name.
			 *
			 * @param  {Element}  element
			 *     Element whose name should be checked.
			 * @param  {string}  role
			 *     Resolved role for the element.
			 *
			 * @returns  {boolean}
			 *     Whether the element has a usable accessible name.
			 */
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

			/**
			 * Return whether axe already reported an element selector.
			 *
			 * @param  {Element}  element
			 *     Element to compare with the axe selectors.
			 *
			 * @returns  {boolean}
			 *     Whether axe already covers the element.
			 */
			const isCoveredByAxe = (element) =>
				coveredTargets.some((selector) => {
					try {
						return element.matches(selector);
					} catch {
						return false;
					}
				});

			for (const element of Array.from(document.querySelectorAll("*"))) {
				// The element's resolved role.
				const role = getRole(element);
				// The element's aria-label value.
				const ariaLabel = element.getAttribute("aria-label");
				// The element's aria-labelledby value.
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
					// The referenced IDs from aria-labelledby.
					const referencedIds = ariaLabelledby.trim().split(/\s+/).filter(Boolean);

					if (referencedIds.some((id) => !document.getElementById(id))) {
						addViolation("aria-labelledby-missing-target", element);
					}

					if (
						referencedIds.some((id) => {
							// The element referenced by the current ID.
							const referencedElement = document.getElementById(id);

							return referencedElement !== null && !referencedElement.textContent?.trim();
						})
					) {
						addViolation("aria-labelledby-empty-text", element);
					}
				}

				// The explicit role attribute, when one is present.
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
