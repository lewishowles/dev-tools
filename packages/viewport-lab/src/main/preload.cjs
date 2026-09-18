// Electron APIs used to connect the app page to the main process.
const { contextBridge, ipcRenderer } = require("electron");

/**
 * Register a callback for addresses accepted by the main process.
 *
 * @param  {Function}  callback
 *     Function that receives the validated address to load.
 */
function onUrl(callback) {
	if (typeof callback !== "function") {
		return;
	}

	ipcRenderer.on("viewport-lab:load-url", (event, url) => callback(url));
}

/**
 * Send an address typed in the URL bar to the main process for validation.
 *
 * @param  {string}  url
 *     Address submitted by the URL bar.
 */
function submitUrl(url) {
	ipcRenderer.send("viewport-lab:submit-url", url);
}

// The page can submit addresses and receive validated updates only.
contextBridge.exposeInMainWorld("viewportLab", {
	onUrl,
	submitUrl,
});
