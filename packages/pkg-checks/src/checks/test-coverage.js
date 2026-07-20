import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { findBarrelCategories, readBarrelExports } from "./exports.js";

/**
 * Check a category's barrel-exported files for a colocated test file.
 *
 * @param  {string}  packageRoot
 *     Package directory to inspect.
 * @param  {string}  category
 *     Category name to check.
 * @returns  {Promise<{checked: number, failures: object[]}>}
 *     Files checked and any missing test files.
 */
async function checkCategory(packageRoot, category) {
	const barrelPath = join(packageRoot, "lib", category, `${category}.js`);
	const exportedFiles = await readBarrelExports(barrelPath, category);

	const failures = [...exportedFiles]
		.filter((filePath) => !existsSync(join(packageRoot, filePath.replace(/\.js$/, ".test.js"))))
		.map((filePath) => ({ target: filePath, reason: "has no test file" }));

	return { checked: exportedFiles.size, failures };
}

/**
 * Check that public exports have colocated test files.
 *
 * @param  {string}  packagePath
 *     Package directory path supplied by the caller.
 * @returns  {Promise<object>}
 *     Test coverage check result.
 */
export async function runTestCoverageCheck(packagePath) {
	if (typeof packagePath !== "string" || !packagePath.trim()) {
		throw new Error("Expected a package directory path.");
	}

	const packageRoot = resolve(packagePath);

	if (!existsSync(packageRoot)) {
		throw new Error(`Package directory not found: ${packagePath}`);
	}

	const categories = await findBarrelCategories(packageRoot);

	let checked = 0;

	const failures = [];

	for (const category of categories) {
		const categoryResult = await checkCategory(packageRoot, category);

		checked += categoryResult.checked;
		failures.push(...categoryResult.failures);
	}

	const result = {
		checked,
		failures,
		mode: "test-coverage",
	};

	return {
		failures,
		packageRoot,
		results: [result],
	};
}
