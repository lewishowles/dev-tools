// The bridge between the URL bar page and the app.
const { contextBridge, ipcRenderer } = require("electron");

/**
 * Send an address typed in the URL bar to the app, which checks it before storing it.
 *
 * @param  {string}  url
 *     Address submitted by the URL bar.
 */
function submitUrl(url) {
	ipcRenderer.send("viewport-lab:submit-url", url);
}

// The page can only send an address; no other Electron API is reachable from it.
contextBridge.exposeInMainWorld("viewportLab", { submitUrl });
