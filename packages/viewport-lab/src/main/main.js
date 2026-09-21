import { BrowserWindow, app, ipcMain } from "electron";
import { checkUrl } from "../url.js";
import { fileURLToPath } from "node:url";

// The single page containing the URL bar and the scrolling pane grid.
const appPagePath = fileURLToPath(new URL("./index.html", import.meta.url));
// The bridge for URL submission and updates in the app page.
const appPreloadPath = fileURLToPath(new URL("./preload.cjs", import.meta.url));

// The address the app is showing. Invalid command-line input leaves the field
// empty.
let storedUrl = checkUrl(process.argv[2]).url ?? "";
// The app window, set when it is created so IPC handlers can verify their
// sender.
let activeMainWindow;

// Webview markup is supplied by the app renderer, so enforce safe defaults in
// the main process.
app.on("will-attach-webview", (_event, webPreferences) => {
	delete webPreferences.preload;

	webPreferences.contextIsolation = true;
	webPreferences.nodeIntegration = false;
	webPreferences.sandbox = true;
});

// Deny windows opened by the app page or any pane webview.
app.on("web-contents-created", (_event, contents) => {
	contents.setWindowOpenHandler(() => ({ action: "deny" }));
});

app.whenReady().then(createWindow);

ipcMain.on("viewport-lab:submit-url", handleUrlSubmission);

/**
 * Create the app window with one renderer for the URL bar and pane grid.
 */
function createWindow() {
	// The window that hosts the URL bar and pane grid.
	const mainWindow = new BrowserWindow({
		height: 800,
		minHeight: 400,
		minWidth: 640,
		title: "Viewport Lab",
		width: 1280,
		webPreferences: {
			contextIsolation: true,
			nodeIntegration: false,
			preload: appPreloadPath,
			sandbox: true,
			webviewTag: true,
		},
	});

	activeMainWindow = mainWindow;

	mainWindow.webContents.on("did-finish-load", sendStoredUrl);

	mainWindow.on("closed", () => {
		activeMainWindow = undefined;

		app.quit();
	});

	void mainWindow.loadFile(appPagePath);
}

/**
 * Tell the app page which address to show in the URL bar and every pane.
 */
function sendStoredUrl() {
	if (!activeMainWindow) {
		return;
	}

	activeMainWindow.webContents.send("viewport-lab:load-url", storedUrl);
}

/**
 * Store an address submitted by the URL bar and load it in every pane. Invalid
 * addresses and messages from any other page are ignored.
 *
 * @param  {object}  event
 *     Message event from the app page.
 * @param  {unknown}  nextUrl
 *     Address submitted by the URL bar.
 */
function handleUrlSubmission(event, nextUrl) {
	if (!activeMainWindow || event.sender !== activeMainWindow.webContents) {
		return;
	}

	// The validation result for the submitted address.
	const nextUrlResult = checkUrl(nextUrl);

	if ("error" in nextUrlResult) {
		return;
	}

	storedUrl = nextUrlResult.url;

	sendStoredUrl();
}
