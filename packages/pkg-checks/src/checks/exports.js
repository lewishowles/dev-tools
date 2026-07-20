import { existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

/**
 * Read an exports policy configuration file.
 *
 * @param  {string}  configPath
 *     Configuration file path.
 * @returns  {Promise<unknown>}
 *     Parsed configuration value.
 */
export async function readExportsConfig(configPath) {
	if (typeof configPath !== "string" || !configPath.trim()) {
		throw new Error("Expected an exports policy configuration path.");
	}

	const source = await readFile(configPath, "utf8");

	try {
		return JSON.parse(source);
	} catch (error) {
		const reason = error instanceof Error ? error.message : String(error);

		throw new Error(`Invalid JSON in exports policy configuration: ${reason}`, {
			cause: error,
		});
	}
}

/**
 * Determine whether a value is a non-array object.
 *
 * @param  {unknown}  value
 *     Value to inspect.
 * @returns  {boolean}
 *     True when the value is an object record.
 */
function isRecord(value) {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Validate and prepare a configured string set.
 *
 * @param  {unknown}  value
 *     Configuration value to validate.
 * @param  {string}  label
 *     Configuration key used in validation errors.
 * @returns  {Set<string>}
 *     Configured string values.
 */
function parseStringSet(value, label) {
	const entries = value === undefined ? [] : value;

	if (!Array.isArray(entries) || entries.some((entry) => typeof entry !== "string" || !entry.trim())) {
		throw new Error(`${label} must contain non-empty strings.`);
	}

	return new Set(entries);
}

/**
 * Validate and prepare the exports policy configuration.
 *
 * @param  {unknown}  value
 *     Configuration value to validate.
 * @returns  {object}
 *     Validated exports policy configuration.
 */
function parseConfig(value) {
	if (!isRecord(value)) {
		throw new Error("Configuration must contain a JSON object.");
	}

	const exportsPolicy = value.exportsPolicy ?? {};

	if (!isRecord(exportsPolicy)) {
		throw new Error("exportsPolicy must contain an object.");
	}

	return {
		exportsPolicy: {
			fileOnlyEntrypoints: parseStringSet(
				exportsPolicy.fileOnlyEntrypoints,
				"exportsPolicy.fileOnlyEntrypoints",
			),
			internalOnly: parseStringSet(exportsPolicy.internalOnly, "exportsPolicy.internalOnly"),
		},
	};
}

/**
 * Find category directories with a matching barrel file.
 *
 * @param  {string}  packageRoot
 *     Package directory to inspect.
 * @returns  {Promise<string[]>}
 *     Sorted category names with barrel files.
 */
export async function findBarrelCategories(packageRoot) {
	const libRoot = join(packageRoot, "lib");

	if (!existsSync(libRoot)) {
		return [];
	}

	const entries = await readdir(libRoot, { withFileTypes: true });

	return entries
		.filter(
			(entry) => entry.isDirectory() && existsSync(join(libRoot, entry.name, `${entry.name}.js`)),
		)
		.map((entry) => entry.name)
		.sort();
}

/**
 * Read the helper paths re-exported by a category barrel.
 *
 * @param  {string}  barrelPath
 *     Category barrel file to inspect.
 * @param  {string}  category
 *     Category name used to build helper paths.
 * @returns  {Promise<Set<string>>}
 *     Exported helper paths.
 */
export async function readBarrelExports(barrelPath, category) {
	const barrelSource = await readFile(barrelPath, "utf8");
	const exportedHelpers = new Set();
	const reExportPattern = /from "\.\/([^"]+\.js)"/g;

	for (const match of barrelSource.matchAll(reExportPattern)) {
		exportedHelpers.add(`lib/${category}/${match[1]}`);
	}

	return exportedHelpers;
}

/**
 * Check that public helper files are covered by their category barrels.
 *
 * @param  {string}  packageRoot
 *     Package directory to inspect.
 * @param  {string[]}  categories
 *     Categories with barrel files.
 * @param  {object}  config
 *     Validated exports policy configuration.
 * @returns  {Promise<object>}
 *     Coverage result and any missing exports.
 */
async function runBarrelCoverage(packageRoot, categories, config) {
	const failures = [];

	let checked = 0;

	for (const category of categories) {
		const categoryRoot = join(packageRoot, "lib", category);
		const barrelPath = join(categoryRoot, `${category}.js`);
		const exportedHelpers = await readBarrelExports(barrelPath, category);
		const entries = await readdir(categoryRoot, { withFileTypes: true });

		for (const entry of entries) {
			const helperName = entry.name;

			if (
				!entry.isFile() ||
				!helperName.endsWith(".js") ||
				helperName === `${category}.js` ||
				helperName.endsWith(".test.js")
			) {
				continue;
			}

			const helperPath = `lib/${category}/${helperName}`;

			if (config.exportsPolicy.internalOnly.has(helperPath)) {
				continue;
			}

			checked += 1;

			if (!exportedHelpers.has(helperPath)) {
				failures.push({
					target: helperPath,
					reason: `is not exported from lib/${category}/${category}.js`,
				});
			}
		}
	}

	return { checked, failures, mode: "barrel-coverage" };
}

/**
 * Read and validate a package manifest when one exists.
 *
 * @param  {string}  packageRoot
 *     Package directory containing package.json.
 * @returns  {Promise<object|null>}
 *     Parsed manifest, or null when no manifest exists.
 */
async function readPackageManifest(packageRoot) {
	const packageJsonPath = join(packageRoot, "package.json");

	if (!existsSync(packageJsonPath)) {
		return null;
	}

	const parsed = JSON.parse(await readFile(packageJsonPath, "utf8"));

	if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
		throw new Error("package.json must contain a JSON object.");
	}

	return parsed;
}

/**
 * Select the import or require target from an export condition value.
 *
 * @param  {unknown}  conditions
 *     Export condition value from package.json.
 * @returns  {string|null}
 *     Resolved target path, or null when no supported target exists.
 */
function getExportPath(conditions) {
	if (typeof conditions === "string") {
		return conditions;
	}

	if (typeof conditions !== "object" || conditions === null || Array.isArray(conditions)) {
		return null;
	}

	const conditionMap = conditions;
	const importPath = conditionMap.import;

	if (typeof importPath === "string") {
		return importPath;
	}

	return typeof conditionMap.require === "string" ? conditionMap.require : null;
}

/**
 * Check that package export targets exist and expose named exports.
 *
 * @param  {string}  packageRoot
 *     Package directory containing package.json.
 * @param  {object}  manifest
 *     Parsed package manifest.
 * @param  {object}  config
 *     Validated exports policy configuration.
 * @returns  {Promise<object>}
 *     Export map result and any invalid targets.
 */
async function runExportsMap(packageRoot, manifest, config) {
	const exportMap = manifest.exports;

	if (typeof exportMap !== "object" || exportMap === null || Array.isArray(exportMap)) {
		throw new Error("package.json exports must contain an object map.");
	}

	const failures = [];

	let checked = 0;

	for (const [entrypoint, conditions] of Object.entries(exportMap)) {
		const filePath = getExportPath(conditions);

		if (!filePath) {
			continue;
		}

		const absolutePath = join(packageRoot, filePath);

		checked += 1;

		if (!existsSync(absolutePath)) {
			failures.push({ target: entrypoint, reason: `dist file not found: ${filePath}` });
			continue;
		}

		if (filePath.endsWith(".css") || config.exportsPolicy.fileOnlyEntrypoints.has(entrypoint)) {
			continue;
		}

		try {
			const loadedModule = await import(pathToFileURL(absolutePath).href);
			const namedExports = Object.keys(loadedModule).filter((name) => name !== "default");

			if (namedExports.length === 0) {
				failures.push({ target: entrypoint, reason: `no named exports in ${filePath}` });
			}
		} catch (error) {
			const reason = error instanceof Error ? error.message : String(error);

			failures.push({ target: entrypoint, reason });
		}
	}

	return { checked, failures, mode: "exports-map" };
}

/**
 * Run all supported export checks for a package.
 *
 * @param  {string}  packagePath
 *     Package directory path supplied by the caller.
 * @param  {unknown}  rawConfig
 *     Unvalidated exports policy configuration.
 * @returns  {Promise<object>}
 *     Combined export-check results.
 */
export async function runExportsCheck(packagePath, rawConfig) {
	if (typeof packagePath !== "string" || !packagePath.trim()) {
		throw new Error("Expected a package directory path.");
	}
	const packageRoot = resolve(packagePath);

	if (!existsSync(packageRoot)) {
		throw new Error(`Package directory not found: ${packagePath}`);
	}

	const config = parseConfig(rawConfig);
	const results = [];
	const categories = await findBarrelCategories(packageRoot);

	if (categories.length > 0) {
		results.push(await runBarrelCoverage(packageRoot, categories, config));
	}

	const manifest = await readPackageManifest(packageRoot);

	if (manifest?.exports !== undefined) {
		results.push(await runExportsMap(packageRoot, manifest, config));
	}

	if (results.length === 0) {
		throw new Error(`No barrel coverage or package.json exports map found: ${packagePath}`);
	}

	return {
		failures: results.flatMap(({ failures }) => failures),
		packageRoot,
		results,
	};
}
