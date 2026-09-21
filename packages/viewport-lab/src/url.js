import { isNonEmptyString } from "@lewishowles/helpers/string";

// URL protocols that the app can open.
const SUPPORTED_PROTOCOLS = ["http:", "https:"];

/**
 * Check that an address is one the app can open.
 *
 * A missing value is allowed and means "no starting address"; the URL bar then
 * starts empty. Empty and non-string values are rejected. An address without a
 * scheme, such as example.com, is treated as https.
 *
 * @param  {unknown}  value
 *     Address to check, usually from the command line or the URL bar.
 *
 * @returns  {{url: string}|{error: string}}
 *     The address to open (empty when no value is given), otherwise a message
 *     explaining the problem.
 */
export function checkUrl(value) {
	if (value === undefined) {
		return { url: "" };
	}

	if (!isNonEmptyString(value)) {
		return { error: "Enter a web address." };
	}

	// A colon followed by a digit is a port, as in localhost:3000, not a
	// scheme.
	const hasExplicitProtocol = /^[a-z][a-z\d+.-]*:(?!\d)/i.test(value);
	// The address to parse, with https added when no scheme was given.
	const address = hasExplicitProtocol ? value : `https://${value}`;

	if (!URL.canParse(address)) {
		return { error: "Enter a web address like example.com." };
	}

	// The parsed address, whose standard form is what the app opens.
	const parsedUrl = new URL(address);

	if (!SUPPORTED_PROTOCOLS.includes(parsedUrl.protocol)) {
		// Protocol names as people type them, without the trailing colon.
		const supportedProtocols = SUPPORTED_PROTOCOLS.map((protocol) => protocol.slice(0, -1)).join(
			" and ",
		);

		return { error: `Only ${supportedProtocols} addresses are supported.` };
	}

	return { url: parsedUrl.toString() };
}
