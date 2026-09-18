// The form sends the new address to the app.
const urlForm = document.querySelector("#url-form");
// The field shows the current address.
const urlInput = document.querySelector("#url-input");

urlInput.value = new URLSearchParams(window.location.search).get("url") ?? "";

/**
 * Send the submitted address to the app.
 *
 * @param  {SubmitEvent}  event
 *     Form submission from the URL bar.
 */
function submitUrl(event) {
	event.preventDefault();

	window.viewportLab.submitUrl(urlInput.value.trim());
}

urlForm.addEventListener("submit", submitUrl);
