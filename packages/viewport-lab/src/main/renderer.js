import { isNonEmptyString } from "@lewishowles/helpers/string";
import { PANE_DEFINITIONS } from "../panes.js";

// The form sends page addresses to the main process for validation.
const urlForm = document.querySelector("#url-form");
// The field shows the current page address.
const urlInput = document.querySelector("#url-input");
// The markup for one pane: its label strip and its webview.
const paneTemplate = document.querySelector("#pane-template");
// The container that CSS lays out as a wrapping grid of panes.
const gridContent = document.querySelector("#grid-content");
// The error and webview elements of each pane, keyed by pane ID.
const paneElements = new Map();

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
	// The pane's size in its label.
	const paneSize = paneCell.querySelector(".pane-size");
	// The place in the label where a load failure is shown.
	const paneError = paneCell.querySelector(".pane-error");
	// The webview that shows the page.
	const paneView = paneCell.querySelector(".pane-view");
	// The ID that links the pane to its name.
	const paneNameId = `${pane.id}-name`;

	paneCell.setAttribute("aria-labelledby", paneNameId);

	paneName.id = paneNameId;
	paneName.textContent = pane.label;
	paneSize.textContent = `${pane.width} × ${pane.height}`;

	paneCell.style.setProperty("--pane-width", `${pane.width}px`);
	paneCell.style.setProperty("--pane-height", `${pane.height}px`);
	paneView.setAttribute(
		"aria-label",
		`${pane.label}, ${pane.width} by ${pane.height} pixels`,
	);

	paneView.addEventListener("did-fail-load", (event) => {
		// Code -3 means the load was cancelled, such as when a new address
		// replaces it.
		if (!event.isMainFrame || event.errorCode === -3) {
			return;
		}

		showPaneFailure(pane.id, event.errorDescription);
	});

	gridContent.append(paneCell);
	paneElements.set(pane.id, { error: paneError, view: paneView });
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
	const message = isNonEmptyString(errorDescription)
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
