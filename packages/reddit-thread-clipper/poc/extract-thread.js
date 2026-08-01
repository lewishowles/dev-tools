/**
 * Expand and extract the currently rendered Reddit thread.
 *
 * This disposable proof of concept is DOM-only. It makes no request to Reddit
 * and is intended to be pasted into the DevTools console on an open thread.
 */
(async () => {
	// Keep the browser-console timing and expansion limits easy to adjust.
	const settings = {
		expandControlPattern:
			/\b(?:load\s+more\s+comments?|view\s+more\s+replies?|continue\s+this\s+thread)\b/i,
		expandControlSelector: 'button, a, [role="button"], summary',
		maxExpansionPasses: 20,
		renderWaitMs: 1000,
		threadElementSelector: "shreddit-post, shreddit-comment",
	};

	/**
	 * Walk light DOM children and every open shadow root below the given root.
	 *
	 * @param  {Document|DocumentFragment|Element}  root
	 *     The rendered DOM root to walk.
	 * @yields {Element}
	 *     Each descendant element in rendered-tree order.
	 */
	function* walkRenderedTree(root) {
		// Convert the live HTMLCollection into a stable list before walking.
		const childElements = root.children ? Array.from(root.children) : [];

		for (const childElement of childElements) {
			yield childElement;

			if (childElement.shadowRoot) {
				yield* walkRenderedTree(childElement.shadowRoot);
			}

			yield* walkRenderedTree(childElement);
		}
	}

	/**
	 * Read visible text from light DOM and open shadow roots.
	 *
	 * @param  {Document|DocumentFragment|Element}  root
	 *     The rendered DOM root whose text should be read.
	 * @returns {string}
	 *     Normalised rendered text.
	 */
	function getRenderedText(root) {
		// Collect separate pieces so text from shadow roots remains readable.
		const textParts = [];

		// Read text and nested rendered elements from the light DOM.
		const childNodes = root.childNodes ? Array.from(root.childNodes) : [];
		for (const childNode of childNodes) {
			if (childNode.nodeType === Node.TEXT_NODE) {
				textParts.push(childNode.nodeValue || "");
				continue;
			}

			if (childNode.nodeType === Node.ELEMENT_NODE) {
				textParts.push(getRenderedText(childNode));
			}
		}

		// Open shadow roots are separate trees and need an explicit traversal.
		if (root.shadowRoot) {
			textParts.push(getRenderedText(root.shadowRoot));
		}

		return textParts.join(" ").replace(/\s+/g, " ").trim();
	}

	/**
	 * Read an element's own rendered text without nested posts or comments.
	 *
	 * @param  {Document|DocumentFragment|Element}  root
	 *     The rendered DOM root whose own text should be read.
	 * @returns {string}
	 *     Normalised text excluding nested thread items.
	 */
	function getOwnRenderedText(root) {
		// Collect only content belonging to this item, not nested thread items.
		const textParts = [];

		// Walk light DOM nodes while skipping nested post and comment hosts.
		const childNodes = root.childNodes ? Array.from(root.childNodes) : [];
		for (const childNode of childNodes) {
			if (childNode.nodeType === Node.TEXT_NODE) {
				textParts.push(childNode.nodeValue || "");
				continue;
			}

			if (childNode.nodeType !== Node.ELEMENT_NODE) {
				continue;
			}

			if (childNode.matches(settings.threadElementSelector)) {
				continue;
			}

			textParts.push(getOwnRenderedText(childNode));
		}

		// Shadow-root content follows the same nested-item rule.
		if (root.shadowRoot) {
			textParts.push(getOwnRenderedText(root.shadowRoot));
		}

		return textParts.join(" ").replace(/\s+/g, " ").trim();
	}

	/**
	 * Find the first descendant matching one of the supplied selectors.
	 *
	 * @param  {Document|DocumentFragment|Element}  root
	 *     The rendered DOM root to search.
	 * @param  {string[]}  selectors
	 *     Selectors ordered from most specific to least specific.
	 * @returns {Element|null}
	 *     The first matching rendered element, if found.
	 */
	function findRenderedElement(root, selectors) {
		// Try selectors in priority order so known Reddit slots win over fallbacks.
		for (const selector of selectors) {
			for (const element of walkRenderedTree(root)) {
				if (element.matches(selector)) {
					return element;
				}
			}
		}

		return null;
	}

	/**
	 * Read the first non-empty attribute from an element.
	 *
	 * @param  {Element}  element
	 *     The element whose attributes should be read.
	 * @param  {string[]}  attributeNames
	 *     Attribute names ordered from most specific to least specific.
	 * @returns {string|null}
	 *     The first non-empty attribute value, if found.
	 */
	function readAttributeValue(element, attributeNames) {
		// Try known Reddit attribute names without assuming one stable schema.
		for (const attributeName of attributeNames) {
			const attributeValue = element.getAttribute(attributeName);

			if (attributeValue && attributeValue.trim()) {
				return attributeValue.trim();
			}
		}

		return null;
	}

	/**
	 * Read a text field from attributes or rendered descendants.
	 *
	 * @param  {Element}  element
	 *     The post or comment element to inspect.
	 * @param  {string[]}  attributeNames
	 *     Attribute names ordered from most specific to least specific.
	 * @param  {string[]}  selectors
	 *     Descendant selectors ordered from most specific to least specific.
	 * @returns {string|null}
	 *     The extracted text, if found.
	 */
	function readTextField(element, attributeNames, selectors) {
		// Reddit exposes some fields directly on its custom elements.
		const attributeValue = readAttributeValue(element, attributeNames);
		if (attributeValue) {
			return attributeValue;
		}

		// Other fields are rendered into slots or ordinary descendants.
		const matchingElement = findRenderedElement(element, selectors);
		if (matchingElement) {
			const renderedText = getRenderedText(matchingElement);
			if (renderedText) {
				return renderedText;
			}
		}

		return null;
	}

	/**
	 * Read and normalise a permalink from an element or descendant link.
	 *
	 * @param  {Element}  element
	 *     The post or comment element to inspect.
	 * @param  {string[]}  attributeNames
	 *     Direct permalink attribute names.
	 * @param  {string[]}  selectors
	 *     Descendant link selectors ordered by specificity.
	 * @returns {string|null}
	 *     An absolute permalink when available.
	 */
	function readPermalink(element, attributeNames, selectors) {
		// Prefer direct custom-element attributes before searching rendered links.
		const directValue = readAttributeValue(element, attributeNames);
		if (directValue) {
			return normalisePermalink(directValue);
		}

		// Link attributes provide a fallback when Reddit omits the custom attribute.
		const linkElement = findRenderedElement(element, selectors);
		if (!linkElement) {
			return null;
		}

		// Read href and permalink-style attributes from the matching link.
		const linkValue = readAttributeValue(linkElement, [
			"content-href",
			"href",
			"permalink",
		]);
		return linkValue ? normalisePermalink(linkValue) : null;
	}

	/**
	 * Resolve a DOM link without fetching it.
	 *
	 * @param  {string}  value
	 *     The relative or absolute DOM value.
	 * @returns {string}
	 *     The resolved URL, or the original value if it is not a valid URL.
	 */
	function normalisePermalink(value) {
		// URL construction resolves a relative link locally and performs no request.
		try {
			return new URL(value, document.baseURI).href;
		} catch (error) {
			return value;
		}
	}

	/**
	 * Convert a Reddit score to a number when possible.
	 *
	 * @param  {string|null}  value
	 *     The raw score value from an attribute or rendered text.
	 * @returns {number|string|null}
	 *     A numeric score, the unparsed value, or null when absent.
	 */
	function normaliseScore(value) {
		// A missing score is represented explicitly so partial captures stay visible.
		if (!value) {
			return null;
		}

		// Remove display punctuation before trying numeric forms.
		const scoreText = String(value).replace(/,/g, "").trim();
		const plainScore = Number(scoreText);
		if (Number.isFinite(plainScore)) {
			return plainScore;
		}

		// Support compact displays such as 1.2k while preserving unknown text.
		const scoreMatch = scoreText.match(/^(-?\d+(?:\.\d+)?)\s*([kmb])?/i);
		if (!scoreMatch) {
			return scoreText;
		}

		// Use browser-native arithmetic because this file has no dependencies.
		const scoreMultipliers = {
			b: 1000000000,
			k: 1000,
			m: 1000000,
		};
		const suffix = scoreMatch[2] ? scoreMatch[2].toLowerCase() : "";
		return Number(scoreMatch[1]) * (scoreMultipliers[suffix] || 1);
	}

	/**
	 * Find currently rendered controls that expand the thread.
	 *
	 * @returns {Element[]}
	 *     Clickable expansion controls currently present in the rendered tree.
	 */
	function findExpandControls() {
		// Snapshot controls once per pass so each lazy-loading wave is rescanned.
		const controls = [];

		for (const element of walkRenderedTree(document)) {
			if (!element.matches(settings.expandControlSelector)) {
				continue;
			}

			if (
				element.hasAttribute("disabled") ||
				element.getAttribute("aria-disabled") === "true"
			) {
				continue;
			}

			// Include visible text and accessibility labels in the unstable selector.
			const controlLabel = [
				element.getAttribute("aria-label"),
				element.getAttribute("title"),
				getRenderedText(element),
			]
				.filter(Boolean)
				.join(" ")
				.replace(/\s+/g, " ")
				.trim();

			if (settings.expandControlPattern.test(controlLabel)) {
				controls.push(element);
			}
		}

		return controls;
	}

	/**
	 * Wait briefly for a clicked Reddit control to render its next wave.
	 *
	 * @returns {Promise<void>}
	 *     Resolves after the render wait has elapsed.
	 */
	function waitForRenderedContent() {
		// A fixed wait keeps this console snippet dependency-free and predictable.
		return new Promise((resolve) => {
			window.setTimeout(resolve, settings.renderWaitMs);
		});
	}

	/**
	 * Click all controls in one expansion pass.
	 *
	 * @param  {Element[]}  controls
	 *     Controls captured by the current scan.
	 * @returns {number}
	 *     Number of controls whose click was dispatched.
	 */
	function clickExpandControls(controls) {
		// Count successful dispatches for useful diagnostics if a node disappears.
		let clickedCount = 0;

		for (const control of controls) {
			if (!control.isConnected) {
				continue;
			}

			try {
				control.click();
				clickedCount += 1;
			} catch (error) {
				console.warn(
					"[reddit-thread-clipper] Could not click an expansion control.",
					error,
				);
			}
		}

		return clickedCount;
	}

	/**
	 * Expand lazy-loaded controls until none remain or the cap is reached.
	 *
	 * @param  {number}  maxPasses
	 *     Maximum number of expand-and-rescan passes.
	 * @returns {Promise<{passes: number, stopReason: string}>}
	 *     The pass count and explicit reason expansion stopped.
	 */
	async function expandThread(maxPasses = settings.maxExpansionPasses) {
		// Track passes so a capped partial capture is reported rather than hidden.
		let passes = 0;

		while (passes < maxPasses) {
			// Rescan after every render wait because Reddit loads comments in waves.
			const controls = findExpandControls();
			if (controls.length === 0) {
				return {
					passes,
					stopReason: "no more controls",
				};
			}

			// Start waiting before clicks so synchronous DOM changes are covered too.
			const renderWait = waitForRenderedContent();
			clickExpandControls(controls);
			passes += 1;
			await renderWait;
		}

		// Rescan after the final wait so an empty final wave reports accurately.
		const remainingControls = findExpandControls();
		if (remainingControls.length === 0) {
			return {
				passes,
				stopReason: "no more controls",
			};
		}

		return {
			passes,
			stopReason: "safety cap reached",
		};
	}

	/**
	 * Read the body belonging to one post or comment.
	 *
	 * @param  {Element}  element
	 *     The post or comment element to inspect.
	 * @param  {string[]}  selectors
	 *     Body selectors ordered from most specific to least specific.
	 * @returns {string|null}
	 *     The extracted body text, if found.
	 */
	function readBody(element, selectors) {
		// Prefer known body slots, then exclude nested thread items from the fallback.
		return (
			readTextField(element, [], selectors) ||
			getOwnRenderedText(element) ||
			null
		);
	}

	/**
	 * Read a comment's declared or inferred nesting depth.
	 *
	 * @param  {Element}  commentElement
	 *     The comment custom element.
	 * @returns {number}
	 *     The rendered comment depth.
	 */
	function readCommentDepth(commentElement) {
		// Reddit may expose depth directly, but the attribute is not stable.
		const declaredDepth = readAttributeValue(commentElement, [
			"comment-depth",
			"depth",
			"depth-level",
		]);
		const numericDepth = Number.parseInt(declaredDepth, 10);
		if (Number.isInteger(numericDepth)) {
			return numericDepth;
		}

		// Count comment hosts through light DOM and open shadow-root boundaries.
		let depth = 0;
		let currentElement = commentElement;
		while (currentElement) {
			let parentElement = currentElement.parentElement;

			if (!parentElement) {
				const rootNode = currentElement.getRootNode();
				parentElement = rootNode && rootNode.host ? rootNode.host : null;
			}

			if (!parentElement) {
				break;
			}

			if (parentElement.matches("shreddit-comment")) {
				depth += 1;
			}

			currentElement = parentElement;
		}

		return depth;
	}

	/**
	 * Extract the structured post fields from a Reddit post host.
	 *
	 * @param  {Element}  postElement
	 *     The post custom element.
	 * @returns {{title: string|null, author: string|null, score: number|string|null, body: string|null, permalink: string|null}}
	 *     The structured post object.
	 */
	function extractPost(postElement) {
		// These selectors cover Reddit custom-element attributes and common slots.
		const title = readTextField(
			postElement,
			["post-title", "title"],
			['[slot="title"]', "h1", '[data-testid="post-title"]'],
		);
		const author = readTextField(
			postElement,
			["post-author", "author", "author-name"],
			[
				'[slot="author"]',
				'[data-testid="post-author"]',
				'a[href^="/user/"]',
				'a[href^="/u/"]',
			],
		);
		const rawScore = readTextField(
			postElement,
			["post-score", "score"],
			['[data-testid="post-score"]', '[aria-label*="point"]'],
		);
		const body = readBody(postElement, [
			'[slot="text-body"]',
			'[slot="post-content"]',
			'[data-testid="post-text"]',
			".md",
		]);
		const permalink = readPermalink(
			postElement,
			["permalink", "content-href"],
			['a[href*="/comments/"]', 'a[href*="/comment/"]'],
		);

		return {
			author: author || null,
			body,
			permalink,
			score: normaliseScore(rawScore),
			title: title || null,
		};
	}

	/**
	 * Extract the structured fields from a Reddit comment host.
	 *
	 * @param  {Element}  commentElement
	 *     The comment custom element.
	 * @returns {{author: string|null, score: number|string|null, body: string|null, permalink: string|null, depth: number}}
	 *     The structured comment object.
	 */
	function extractComment(commentElement) {
		// Reddit's comment host exposes similar fields with comment-specific slots.
		const author = readTextField(
			commentElement,
			["comment-author", "author", "author-name"],
			[
				'[slot="author"]',
				'[data-testid="comment_author_link"]',
				'a[href^="/user/"]',
				'a[href^="/u/"]',
			],
		);
		const rawScore = readTextField(
			commentElement,
			["comment-score", "score"],
			['[data-testid="comment-score"]', '[aria-label*="point"]'],
		);
		const body = readBody(commentElement, [
			'[slot="comment"]',
			'[slot="text-body"]',
			'[data-testid="comment"]',
			".md",
		]);
		const permalink = readPermalink(
			commentElement,
			["permalink", "comment-href", "content-href"],
			['a[href*="/comments/"]', 'a[href*="/comment/"]'],
		);
		const depth = readCommentDepth(commentElement);

		return {
			author: author || null,
			body,
			depth,
			permalink,
			score: normaliseScore(rawScore),
		};
	}

	/**
	 * Extract the first rendered post and every rendered comment.
	 *
	 * @returns {{post: object, comments: object[]}}
	 *     The structured thread object.
	 */
	function extractThread() {
		// Walk once so post and comment hosts include open shadow-root content.
		const renderedElements = Array.from(walkRenderedTree(document));
		const postElement = renderedElements.find((element) =>
			element.matches("shreddit-post"),
		);
		const commentElements = renderedElements.filter((element) =>
			element.matches("shreddit-comment"),
		);

		// Keep missing post fields explicit if Reddit's DOM changes under the POC.
		const post = postElement
			? extractPost(postElement)
			: {
					author: null,
					body: null,
					permalink: null,
					score: null,
					title: null,
				};
		const comments = commentElements.map((commentElement) =>
			extractComment(commentElement),
		);

		return {
			comments,
			post,
		};
	}

	// Expand first, then extract only what Reddit rendered in the current tab.
	const expansionResult = await expandThread();
	const thread = extractThread();
	const serialisedThread = JSON.stringify(thread, null, 2);

	// Attempt DevTools clipboard copy while always retaining a visible console output.
	let copiedToClipboard = false;
	if (typeof copy === "function") {
		try {
			copy(serialisedThread);
			copiedToClipboard = true;
		} catch (error) {
			console.warn(
				"[reddit-thread-clipper] Clipboard copy failed; use the logged JSON.",
				error,
			);
		}
	} else {
		console.warn(
			"[reddit-thread-clipper] DevTools copy() is unavailable; use the logged JSON.",
		);
	}

	// Report both capture size and the exact expansion stop condition.
	const copyStatus = copiedToClipboard
		? "JSON copied to the clipboard"
		: "JSON logged below";
	console.info(
		"[reddit-thread-clipper] Captured " +
			thread.comments.length +
			" comments. Expansion stopped: " +
			expansionResult.stopReason +
			". " +
			copyStatus +
			".",
	);
	console.log("[reddit-thread-clipper] JSON output:\n" + serialisedThread);

	return thread;
})();
