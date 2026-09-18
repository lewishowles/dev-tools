import { BrowserWindow, WebContentsView, app, ipcMain } from "electron";
import { checkUrl } from "../url.js";
import { fileURLToPath } from "node:url";

// The address the app is showing. It starts from the command-line argument; an invalid argument
// is ignored and the URL bar starts empty.
let storedUrl = checkUrl(process.argv[2]).url ?? "";

// The page that displays the URL bar.
const urlBarPagePath = fileURLToPath(new URL("../toolbar/index.html", import.meta.url));
// The script that lets the URL bar send an address to the app.
const urlBarPreloadPath = fileURLToPath(new URL("../toolbar/preload.cjs", import.meta.url));

/**
 * Keep the URL bar across the top of the window.
 *
 * A WebContentsView has no automatic layout, and the bar must be a child view because pane views
 * draw over the window's own page.
 *
 * @param  {BrowserWindow} mainWindow
 *     Window that contains the URL bar.
 * @param  {WebContentsView} toolbarView
 *     URL bar view to position.
 */
function updateToolbarBounds(mainWindow, toolbarView) {
	const [contentWidth] = mainWindow.getContentSize();

	toolbarView.setBounds({
		height: 64,
		width: contentWidth,
		x: 0,
		y: 0,
	});
}

/**
 * Store an address submitted by the URL bar. Invalid addresses are dropped, so the stored address
 * is always one the panes can open.
 *
 * @param  {object}  event
 *     Message event from Electron, unused.
 * @param  {unknown}  nextUrl
 *     Address submitted by the URL bar.
 */
function handleUrlSubmission(event, nextUrl) {
	const nextUrlResult = checkUrl(nextUrl);

	if ("error" in nextUrlResult) {
		return;
	}

	storedUrl = nextUrlResult.url;
}

/**
 * Create the app window and its URL bar.
 */
function createWindow() {
	const mainWindow = new BrowserWindow({
		height: 800,
		minHeight: 400,
		minWidth: 640,
		title: "Viewport Lab",
		width: 1280,
	});

	const toolbarView = new WebContentsView({
		webPreferences: {
			contextIsolation: true,
			nodeIntegration: false,
			preload: urlBarPreloadPath,
			sandbox: true,
		},
	});

	mainWindow.contentView.addChildView(toolbarView);

	updateToolbarBounds(mainWindow, toolbarView);

	mainWindow.on("resize", () => updateToolbarBounds(mainWindow, toolbarView));
	mainWindow.on("closed", () => app.quit());

	toolbarView.webContents.loadFile(urlBarPagePath, {
		query: {
			url: storedUrl,
		},
	});
}

ipcMain.on("viewport-lab:submit-url", handleUrlSubmission);

app.whenReady().then(createWindow);
