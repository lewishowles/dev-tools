import { expect, test } from "bun:test";
import { checkUrl } from "../src/url.js";

test("accepts an HTTP address", () => {
	const result = checkUrl("http://example.com");

	expect(result).toEqual({ url: "http://example.com/" });
});

test("accepts an HTTPS address", () => {
	const result = checkUrl("https://example.com");

	expect(result).toEqual({ url: "https://example.com/" });
});

test("accepts a bare host with an HTTPS default", () => {
	const result = checkUrl("example.com");

	expect(result).toEqual({ url: "https://example.com/" });
});

test("accepts a host with a path and an HTTPS default", () => {
	const result = checkUrl("example.com/path");

	expect(result).toEqual({ url: "https://example.com/path" });
});

test("accepts a host with a port and an HTTPS default", () => {
	const result = checkUrl("localhost:3000");

	expect(result).toEqual({ url: "https://localhost:3000/" });
});

test("keeps a port and path when adding an HTTPS default", () => {
	const result = checkUrl("example.com:8080/path");

	expect(result).toEqual({ url: "https://example.com:8080/path" });
});

test("rejects an empty address", () => {
	const result = checkUrl("");

	expect(result).toEqual({ error: "Enter a web address." });
});

test("accepts a missing address", () => {
	const result = checkUrl(undefined);

	expect(result).toEqual({ url: "" });
});

test("rejects an unparseable address", () => {
	const result = checkUrl("https://");

	expect(result).toEqual({
		error: "Enter a web address like example.com.",
	});
});

test("rejects an FTP address", () => {
	const result = checkUrl("ftp://example.com");

	expect(result).toEqual({
		error: "Only http and https addresses are supported.",
	});
});

test("rejects a file address", () => {
	const result = checkUrl("file:///tmp/example.html");

	expect(result).toEqual({
		error: "Only http and https addresses are supported.",
	});
});

test("rejects a JavaScript address", () => {
	const result = checkUrl("javascript:alert(1)");

	expect(result).toEqual({
		error: "Only http and https addresses are supported.",
	});
});

test("rejects non-string input", () => {
	const values = [null, 42, {}];

	for (const value of values) {
		const result = checkUrl(value);

		expect(result).toEqual({ error: "Enter a web address." });
	}
});
