import { existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const INTERNAL_HELPERS = new Set([
	"lib/object/path-traversal.js",
	"lib/string/tokenise-words.js",
]);

const FILE_CHECK_ONLY = new Set(["./resolver"]);

export type ExportCheckMode = "barrel-coverage" | "exports-map";

export interface ExportCheckFailure {
	target: string;
	reason: string;
}

export interface ExportModeResult {
	mode: ExportCheckMode;
	checked: number;
	failures: ExportCheckFailure[];
}

export interface ExportCheckResult {
	packageRoot: string;
	results: ExportModeResult[];
	failures: ExportCheckFailure[];
}

interface PackageManifest {
	exports?: unknown;
}

/**
 * Find category directories with a matching barrel file.
 *
 * @param  {string}  packageRoot
 *     Absolute package directory to inspect.
 * @returns  {Promise<string[]>}
 *     Category names with barrel files.
 */
async function findBarrelCategories(packageRoot: string): Promise<string[]> {
	const libRoot = join(packageRoot, "lib");

	if (!existsSync(libRoot)) {
		return [];
	}

	const entries = await readdir(libRoot, { withFileTypes: true });

	return entries
		.filter(
			(entry) =>
				entry.isDirectory() && existsSync(join(libRoot, entry.name, `${entry.name}.js`)),
		)
		.map((entry) => entry.name)
		.sort();
}

/**
 * Read the helper paths re-exported by a category barrel.
 *
 * @param  {string}  barrelPath
 *     Absolute path to a category barrel.
 * @param  {string}  category
 *     Helper category represented by the barrel.
 * @returns  {Promise<Set<string>>}
 *     Repo-relative helper paths re-exported by the barrel.
 */
async function readBarrelExports(barrelPath: string, category: string): Promise<Set<string>> {
	const barrelSource = await readFile(barrelPath, "utf8");
	const exportedHelpers = new Set<string>();
	const reExportPattern = /from "\.\/([^"]+\.js)"/g;

	for (const match of barrelSource.matchAll(reExportPattern)) {
		exportedHelpers.add(`lib/${category}/${match[1]}`);
	}

	return exportedHelpers;
}

/**
 * Check public helper files against their category barrels.
 *
 * @param  {string}  packageRoot
 *     Absolute package directory to inspect.
 * @param  {string[]}  categories
 *     Categories with matching barrel files.
 * @returns  {Promise<ExportModeResult>}
 *     Barrel coverage verdict and missing exports.
 */
async function runBarrelCoverage(
	packageRoot: string,
	categories: string[],
	): Promise<ExportModeResult> {
	const failures: ExportCheckFailure[] = [];

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

			if (INTERNAL_HELPERS.has(helperPath)) {
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
 * Read a package manifest when it exists.
 *
 * @param  {string}  packageRoot
 *     Absolute package directory to inspect.
 * @returns  {Promise<PackageManifest | null>}
 *     Parsed package manifest, or null when absent.
 */
async function readPackageManifest(packageRoot: string): Promise<PackageManifest | null> {
	const packageJsonPath = join(packageRoot, "package.json");

	if (!existsSync(packageJsonPath)) {
		return null;
	}

	const parsed: unknown = JSON.parse(await readFile(packageJsonPath, "utf8"));

	if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
		throw new Error("package.json must contain a JSON object.");
	}

	return parsed as PackageManifest;
}

/**
 * Select the first supported file path from an exports entry.
 *
 * @param  {unknown}  conditions
 *     String export path or one-level import/require condition object.
 * @returns  {string | null}
 *     Resolved package-relative file path, or null when unsupported.
 */
function getExportPath(conditions: unknown): string | null {
	if (typeof conditions === "string") {
		return conditions;
	}

	if (typeof conditions !== "object" || conditions === null || Array.isArray(conditions)) {
		return null;
	}

	const conditionMap = conditions as Record<string, unknown>;
	const importPath = conditionMap.import;

	if (typeof importPath === "string") {
		return importPath;
	}

	return typeof conditionMap.require === "string" ? conditionMap.require : null;
}

/**
 * Check package.json exports entries for files and named JavaScript exports.
 *
 * @param  {string}  packageRoot
 *     Absolute package directory to inspect.
 * @param  {PackageManifest}  manifest
 *     Parsed package manifest containing an exports map.
 * @returns  {Promise<ExportModeResult>}
 *     Exports-map verdict and failures.
 */
async function runExportsMap(
	packageRoot: string,
	manifest: PackageManifest,
): Promise<ExportModeResult> {
	const exportMap = manifest.exports;

	if (typeof exportMap !== "object" || exportMap === null || Array.isArray(exportMap)) {
		throw new Error("package.json exports must contain an object map.");
	}

	const failures: ExportCheckFailure[] = [];

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

		if (filePath.endsWith(".css") || FILE_CHECK_ONLY.has(entrypoint)) {
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
 * Run every export validity mode supported by a package.
 *
 * @param  {string}  packagePath
 *     Package directory supplied by the caller.
 * @returns  {Promise<ExportCheckResult>}
 *     Combined verdict for barrel coverage and exports-map checks.
 */
export async function runExportsCheck(packagePath: string): Promise<ExportCheckResult> {
	if (typeof packagePath !== "string" || !packagePath.trim()) {
		throw new Error("Expected a package directory path.");
	}

	const packageRoot = resolve(packagePath);

	if (!existsSync(packageRoot)) {
		throw new Error(`Package directory not found: ${packagePath}`);
	}

	const results: ExportModeResult[] = [];
	const categories = await findBarrelCategories(packageRoot);

	if (categories.length > 0) {
		results.push(await runBarrelCoverage(packageRoot, categories));
	}

	const manifest = await readPackageManifest(packageRoot);

	if (manifest?.exports !== undefined) {
		results.push(await runExportsMap(packageRoot, manifest));
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
