import { expect, test } from "bun:test";
import { resolve } from "node:path";
import { runExportsCheck } from "../src/checks/exports.js";

/**
 * Resolve a checked-in pkg-checks fixture package directory by name.
 *
 * @param  {string}  packageName
 *     Fixture package directory name relative to the package fixtures directory.
 * @returns  {string}
 *     Absolute fixture package path.
 */
function fixturePackagePath(packageName) {
	return resolve(import.meta.dir, "../fixtures", packageName);
}

test("Resolves the default export condition", async () => {
	const result = await runExportsCheck(fixturePackagePath("default-export-package"), {});
	const exportsMapResult = result.results.find((entry) => entry.mode === "exports-map");

	expect(exportsMapResult.checked).toBe(1);
	expect(exportsMapResult.failures).toEqual([]);
});
