import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { findBarrelCategories } from "./exports.js";

/**
 * Read the names exported from a category barrel.
 *
 * @param  {string}  barrelPath
 *     Category barrel file to inspect.
 * @returns  {Promise<Set<string>>}
 *     Exported names.
 */
async function readBarrelExportNames(barrelPath) {
	const barrelSource = await readFile(barrelPath, "utf8");
	const exportBracePattern = /export\s*\{([^}]*)\}/g;
	const exportedNames = new Set();

	for (const match of barrelSource.matchAll(exportBracePattern)) {
		for (const name of match[1].split(",")) {
			const trimmedName = name.trim();

			if (trimmedName) {
				exportedNames.add(trimmedName);
			}
		}
	}

	return exportedNames;
}

/**
 * Read the names declared in a category's type declarations file.
 *
 * @param  {string}  typesPath
 *     Type declarations file to inspect.
 * @returns  {Promise<Set<string>>}
 *     Declared names.
 */
async function readDeclaredNames(typesPath) {
	const typesSource = await readFile(typesPath, "utf8");
	const declaredNamePattern = /^export declare (?:function|class|const) ([a-zA-Z_][a-zA-Z0-9_]*)/gm;
	const declaredNames = new Set();

	for (const match of typesSource.matchAll(declaredNamePattern)) {
		declaredNames.add(match[1]);
	}

	return declaredNames;
}

/**
 * Check a category's barrel exports against its type declarations.
 *
 * @param  {string}  packageRoot
 *     Package directory to inspect.
 * @param  {string}  category
 *     Category name to check.
 * @returns  {Promise<{checked: number, failures: object[]}>}
 *     Names checked and any missing declarations.
 */
async function checkCategory(packageRoot, category) {
	const typesPath = join(packageRoot, "types", `${category}.d.ts`);

	if (!existsSync(typesPath)) {
		return {
			checked: 0,
			failures: [{ target: `types/${category}.d.ts`, reason: "does not exist" }],
		};
	}

	const barrelPath = join(packageRoot, "lib", category, `${category}.js`);
	const exportedNames = await readBarrelExportNames(barrelPath);
	const declaredNames = await readDeclaredNames(typesPath);

	const failures = [...exportedNames]
		.filter((name) => !declaredNames.has(name))
		.map((name) => ({
			target: name,
			reason: `is exported from lib/${category}/${category}.js but has no declaration in types/${category}.d.ts`,
		}));

	return { checked: exportedNames.size, failures };
}

/**
 * Check that public exports have matching type declarations.
 *
 * @param  {string}  packagePath
 *     Package directory path supplied by the caller.
 * @returns  {Promise<object>}
 *     Type declaration check result.
 */
export async function runTypeDeclarationsCheck(packagePath) {
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
		mode: "type-declarations",
	};

	return {
		failures,
		packageRoot,
		results: [result],
	};
}
