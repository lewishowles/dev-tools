import { PANE_DEFINITIONS } from "../panes.js";

// The form sends page addresses to the main process for validation.
const urlForm = document.querySelector("#url-form");
// The field shows the current page address.
const urlInput = document.querySelector("#url-input");
// The button reloads every pane without changing the current address.
const reloadAllButton = document.querySelector("#reload-all");
// The markup for one pane: its label strip and its webview.
const paneTemplate = document.querySelector("#pane-template");
// The container that CSS lays out as a wrapping grid of panes.
const gridContent = document.querySelector("#grid-content");
// The scrolling region that contains the complete grid.
const scrollRegion = document.querySelector("#scroll-region");
// The cell, size label, error, webview and control buttons of each pane, keyed
// by pane ID.
const paneElements = new Map();

// The grid scroll position to return to when a maximised pane is restored.
let maximisedScrollPosition;

/**
 * Build a pane from the template, size it and add it to the grid.
 *
 * @param  {object}  pane
 *     Pane definition containing its ID, label, width, and height.
 */
function createPane(pane) {
	// The new pane, copied from the template.
	const paneCell = paneTemplate.content.firstElementChild.cloneNode(true);
	// The pane's name in its label.
	const paneName = paneCell.querySelector(".pane-name");
	// The place in the label where the pane size is shown.
	const paneSize = paneCell.querySelector(".pane-size");
	// The place in the label where a load failure is shown.
	const paneError = paneCell.querySelector(".pane-error");
	// The button that reloads this pane.
	const paneReloadButton = paneCell.querySelector(".pane-reload");
	// The button that swaps this pane's dimensions.
	const paneRotateButton = paneCell.querySelector(".pane-rotate");
	// The button that maximises or restores this pane.
	const paneMaximiseButton = paneCell.querySelector(".pane-maximise");
	// The webview that shows the page.
	const paneView = paneCell.querySelector(".pane-view");
	// The ID that links the pane to its name.
	const paneNameId = `${pane.id}-name`;

	paneCell.setAttribute("aria-labelledby", paneNameId);

	paneName.id = paneNameId;
	paneName.textContent = pane.label;

	paneReloadButton.addEventListener("click", () => reloadPane(pane.id));
	paneRotateButton.addEventListener("click", () => rotatePane(pane.id));
	paneMaximiseButton.addEventListener("click", () =>
		togglePaneMaximise(pane.id),
	);

	paneView.addEventListener("did-fail-load", (event) => {
		// Code -3 means the load was cancelled, such as when a new address
		// replaces it.
		if (!event.isMainFrame || event.errorCode === -3) {
			return;
		}

		showPaneFailure(pane.id, event.errorDescription);
	});

	paneElements.set(pane.id, {
		cell: paneCell,
		error: paneError,
		maximise: paneMaximiseButton,
		reload: paneReloadButton,
		rotate: paneRotateButton,
		size: paneSize,
		view: paneView,
	});
	gridContent.append(paneCell);
	updatePane(pane);
}

/**
 * Apply a pane's current dimensions and control state to its elements.
 *
 * @param  {object}  pane
 *     The pane to redraw, with its current size and whether it is maximised.
 */
function updatePane(pane) {
	// The elements belonging to the pane being updated.
	const paneState = paneElements.get(pane.id);

	if (!paneState) {
		return;
	}

	// The accessible name for the reload action.
	const reloadLabel = `Reload ${pane.label} pane`;
	// The accessible name for the rotate action.
	const rotateLabel = `Rotate ${pane.label} pane`;

	// The accessible name for the maximise or restore action.
	const maximiseLabel = pane.maximised
		? `Restore ${pane.label} pane`
		: `Maximise ${pane.label} pane`;

	// The size text reflects whether the pane has its true viewport size.
	const sizeLabel = pane.maximised
		? "Fills window"
		: `${pane.width} × ${pane.height}`;

	// The webview name reflects whether the pane has its true viewport size.
	const viewLabel = pane.maximised
		? `${pane.label}, filling the window`
		: `${pane.label}, ${pane.width} by ${pane.height} pixels`;

	paneState.cell.hidden = hasMaximisedPane() && !pane.maximised;
	paneState.size.textContent = sizeLabel;

	paneState.view.setAttribute("aria-label", viewLabel);
	paneState.reload.setAttribute("aria-label", reloadLabel);
	paneState.rotate.setAttribute("aria-label", rotateLabel);
	paneState.maximise.setAttribute("aria-label", maximiseLabel);

	paneState.reload.title = reloadLabel;
	paneState.rotate.title = rotateLabel;
	paneState.maximise.title = maximiseLabel;

	paneState.cell.style.setProperty("--pane-width", `${pane.width}px`);
	paneState.cell.style.setProperty("--pane-height", `${pane.height}px`);
}

/**
 * Return whether the grid currently has a maximised pane.
 *
 * @returns  {boolean}
 *     True when one pane is marked as maximised.
 */
function hasMaximisedPane() {
	return PANE_DEFINITIONS.some((pane) => pane.maximised);
}

/**
 * Redraw every pane and switch the grid between its normal and maximised
 * layouts.
 */
function updateGrid() {
	gridContent.classList.toggle("is-maximised", hasMaximisedPane());

	for (const pane of PANE_DEFINITIONS) {
		updatePane(pane);
	}
}

/**
 * Reload one pane without changing its current page or dimensions.
 *
 * @param  {string}  paneId
 *     Identifier of the pane to reload.
 */
function reloadPane(paneId) {
	// The elements belonging to the pane being reloaded.
	const paneState = paneElements.get(paneId);

	if (!paneState) {
		return;
	}

	paneState.view.reload();
}

/**
 * Reload every pane without changing the current address or dimensions.
 */
function reloadAllPanes() {
	for (const pane of PANE_DEFINITIONS) {
		reloadPane(pane.id);
	}
}

/**
 * Swap a pane's width and height, then apply the new layout.
 *
 * @param  {string}  paneId
 *     Identifier of the pane to rotate.
 */
function rotatePane(paneId) {
	// The pane whose dimensions are being swapped.
	const pane = PANE_DEFINITIONS.find((candidate) => candidate.id === paneId);

	if (!pane) {
		return;
	}

	// Keep the old width before the dimensions are exchanged.
	const previousWidth = pane.width;

	pane.width = pane.height;
	pane.height = previousWidth;

	updateGrid();
}

/**
 * Maximise one pane or restore the grid to its previous scroll position.
 *
 * @param  {string}  paneId
 *     Identifier of the pane whose maximised state is changing.
 */
function togglePaneMaximise(paneId) {
	// The pane whose maximised state is changing.
	const pane = PANE_DEFINITIONS.find((candidate) => candidate.id === paneId);

	if (!pane) {
		return;
	}

	if (pane.maximised) {
		pane.maximised = false;

		updateGrid();

		if (maximisedScrollPosition) {
			// The grid position from before the pane was maximised.
			const { left, top } = maximisedScrollPosition;

			scrollRegion.scrollTo(left, top);
		}

		maximisedScrollPosition = undefined;

		return;
	}

	// Remember the grid position before the other panes are hidden.
	maximisedScrollPosition = {
		left: scrollRegion.scrollLeft,
		top: scrollRegion.scrollTop,
	};

	for (const candidate of PANE_DEFINITIONS) {
		candidate.maximised = candidate.id === paneId;
	}

	updateGrid();
	scrollRegion.scrollTo(0, 0);
}

/**
 * Show why a pane's page failed to load.
 *
 * @param  {string}  paneId
 *     Identifier of the pane that failed.
 * @param  {unknown}  errorDescription
 *     Human-readable webview load error.
 */
function showPaneFailure(paneId, errorDescription) {
	// The elements of the pane that failed.
	const paneState = paneElements.get(paneId);

	if (!paneState) {
		return;
	}

	// The browser's reason, or a general message when it gives none.
	const message =
		typeof errorDescription === "string" && errorDescription.trim() !== ""
		? errorDescription
		: "The page could not be loaded.";

	paneState.error.textContent = `Could not load page: ${message}`;
}

/**
 * Clear the load failure message from every pane.
 */
function clearPaneFailures() {
	for (const paneState of paneElements.values()) {
		paneState.error.textContent = "";
	}
}

/**
 * Load an address into every pane.
 *
 * Each pane loads the address once. After that, navigating inside one pane
 * leaves the others where they are.
 *
 * @param  {unknown}  url
 *     Address received from the main process.
 */
function loadPaneUrl(url) {
	clearPaneFailures();

	urlInput.value = url;

	for (const paneState of paneElements.values()) {
		paneState.view.src = url || "about:blank";
	}
}

/**
 * Send the submitted address to the main process.
 *
 * @param  {SubmitEvent}  event
 *     Form submission from the URL bar.
 */
function submitUrl(event) {
	event.preventDefault();

	window.viewportLab.submitUrl(urlInput.value.trim());
}

// Build one pane for each viewport size.
for (const pane of PANE_DEFINITIONS) {
	createPane(pane);
}

// Load each address the main process accepts into every pane.
window.viewportLab.onUrl(loadPaneUrl);

// Send the address bar's value to the main process to be checked.
urlForm.addEventListener("submit", submitUrl);

// Reload every pane without changing the address bar or page locations.
reloadAllButton.addEventListener("click", reloadAllPanes);
