import { PANE_DEFINITIONS } from "../panes.js";
import { PANE_LABEL_HEIGHT, createGridLayout } from "../layout.js";

// The form sends page addresses to the main process for validation.
const urlForm = document.querySelector("#url-form");
// The field shows the current page address.
const urlInput = document.querySelector("#url-input");
// The scrolling region contains the complete grid.
const scrollRegion = document.querySelector("#scroll-region");
// The positioned container owns every pane label and webview.
const gridContent = document.querySelector("#grid-content");
// Pane elements keyed by their stable definition ID.
const paneElements = new Map();

/**
 * Recalculate positions from the available scrolling width.
 */
function updateGrid() {
	// Use the layout to size and position the scrolling grid.
	const layout = createGridLayout(PANE_DEFINITIONS, scrollRegion.clientWidth);

	gridContent.style.height = `${layout.contentHeight}px`;
	gridContent.style.width = `${layout.contentWidth}px`;

	for (const cell of layout.cells) {
		// Reuse the pane elements so loaded pages survive layout updates.
		let paneState = paneElements.get(cell.id);

		if (!paneState) {
			paneState = createPaneElements(cell);

			paneElements.set(cell.id, paneState);
			gridContent.append(paneState.cell);
		}

		updatePaneElements(paneState, cell);
	}
}

/**
 * Create one label and webview pair for a pane.
 *
 * @param  {object}  cell
 *     Pane definition and CSS position.
 *
 * @returns  {object}
 *     Object containing the `cell`, `error`, `name`, `size`, and `view`
 *     elements.
 */
function createPaneElements(cell) {
	// The pane cell container.
	const paneCell = document.createElement("section");
	// The label strip above the webview.
	const paneLabel = document.createElement("div");
	// The pane name element.
	const paneName = document.createElement("span");
	// The pane size element.
	const paneSize = document.createElement("span");
	// The pane load-error element.
	const paneError = document.createElement("span");
	// The page webview.
	const paneView = document.createElement("webview");
	// The stable ID used to label the pane.
	const paneNameId = `${cell.id}-name`;

	paneCell.className = "pane-cell";

	paneCell.setAttribute("aria-labelledby", paneNameId);

	paneLabel.className = "pane-label";
	paneLabel.style.height = `${PANE_LABEL_HEIGHT}px`;
	paneName.className = "pane-name";
	paneName.id = paneNameId;
	paneSize.className = "pane-size";
	paneError.className = "pane-error";

	paneError.setAttribute("aria-live", "polite");

	paneView.className = "pane-view";

	paneView.setAttribute("webpreferences", "contextIsolation=yes,sandbox=yes");
	paneView.addEventListener("did-fail-load", (event) => {
		// Code -3 means the load was cancelled, such as when a new address
		// replaces it.
		if (!event.isMainFrame || event.errorCode === -3) {
			return;
		}

		showPaneFailure(cell.id, event.errorDescription);
	});

	paneLabel.append(paneName, paneSize, paneError);
	paneCell.append(paneLabel, paneView);

	paneView.src = "about:blank";

	return {
		cell: paneCell,
		error: paneError,
		name: paneName,
		size: paneSize,
		view: paneView,
	};
}

/**
 * Update one pane's CSS geometry while preserving its loaded page.
 *
 * @param  {object}  paneState
 *     Object containing the `cell`, `error`, `name`, `size`, and `view`
 *     elements.
 * @param  {object}  cell
 *     Pane definition and CSS position.
 */
function updatePaneElements(paneState, cell) {
	paneState.cell.style.height = `${cell.height + PANE_LABEL_HEIGHT}px`;
	paneState.cell.style.left = `${cell.left}px`;
	paneState.cell.style.top = `${cell.top}px`;
	paneState.cell.style.width = `${cell.width}px`;
	paneState.name.textContent = cell.label;
	paneState.size.textContent = `${cell.width} × ${cell.height}`;
	paneState.view.style.height = `${cell.height}px`;
	paneState.view.style.width = `${cell.width}px`;

	paneState.view.setAttribute(
		"aria-label",
		`${cell.label}, ${cell.width} by ${cell.height} pixels`,
	);
}

/**
 * Show one pane's main-frame load failure in its label strip.
 *
 * @param  {string}  paneId
 *     Identifier of the pane that failed.
 * @param  {unknown}  errorDescription
 *     Human-readable webview load error.
 */
function showPaneFailure(paneId, errorDescription) {
	// Show the failure in the matching pane's label.
	const paneState = paneElements.get(paneId);

	if (!paneState) {
		return;
	}

	// The user-facing failure message.
	const message =
		typeof errorDescription === "string" && errorDescription
			? errorDescription
			: "The page could not be loaded.";

	paneState.error.textContent = `Could not load page: ${message}`;
}

/**
 * Remove all pane load failures after a new address is submitted.
 */
function clearPaneFailures() {
	for (const paneState of paneElements.values()) {
		paneState.error.textContent = "";
	}
}

/**
 * Load a validated address into every pane without linking their navigation.
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

updateGrid();
window.addEventListener("resize", updateGrid);
window.viewportLab.onUrl(loadPaneUrl);
urlForm.addEventListener("submit", submitUrl);
