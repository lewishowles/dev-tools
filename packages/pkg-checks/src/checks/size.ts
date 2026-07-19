import { existsSync } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import { join, relative, resolve, sep } from "node:path";

export interface SizeFileBudget {
	globs: string[];
	maxBytes: number;
}

export interface SizeTotalBudget {
	name: string;
	globs: string[];
	maxBytes: number;
}

export interface SizeBudgetConfig {
	sizeBudgets: {
		perFile: SizeFileBudget;
		total: SizeTotalBudget[];
	};
}

export type SizeBudgetKind = "per-file" | "total";

export interface SizeCheckFailure {
	target: string;
	reason: string;
}

export interface SizeBudgetResult {
	name: string;
	kind: SizeBudgetKind;
	checked: number;
	actualBytes?: number;
	maxBytes: number;
	failures: SizeCheckFailure[];
}

export interface SizeCheckResult {
	packageRoot: string;
	results: SizeBudgetResult[];
	failures: SizeCheckFailure[];
}

interface FileSize {
	path: string;
	bytes: number;
}

interface ParsedBudget {
	globs: string[];
	maxBytes: number;
}

/**
 * Read a JSON size budget configuration.
 *
 * @param  {string}  configPath
 *     Path to the JSON configuration file.
 * @returns  {Promise<unknown>}
 *     Parsed configuration awaiting runtime validation by the check.
 */
export async function readSizeConfig(configPath: string): Promise<unknown> {
	if (typeof configPath !== "string" || !configPath.trim()) {
		throw new Error("Expected a size budget configuration path.");
	}

	const source = await readFile(configPath, "utf8");

	try {
		return JSON.parse(source) as unknown;
	} catch (error) {
		const reason = error instanceof Error ? error.message : String(error);

		throw new Error(`Invalid JSON in size budget configuration: ${reason}`, { cause: error });
	}
}

/**
 * Check whether a value is a non-null object with string keys.
 *
 * @param  {unknown}  value
 *     Value to inspect.
 * @returns  {boolean}
 *     Whether the value can be read as a record.
 */
function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Parse and normalise package-relative glob patterns.
 *
 * @param  {unknown}  value
 *     Raw glob list from the configuration.
 * @param  {string}  label
 *     Configuration label used in validation errors.
 * @returns  {string[]}
 *     Normalised slash-separated glob patterns.
 */
function parseGlobs(value: unknown, label: string): string[] {
	if (
		!Array.isArray(value) ||
		value.length === 0 ||
		value.some((glob) => typeof glob !== "string" || !glob.trim())
	) {
		throw new Error(`${label}.globs must contain one or more non-empty strings.`);
	}

	return value.map((glob) => {
		const normalisedGlob = glob.replaceAll("\\", "/").replace(/^\.\/+/, "");
		const segments = normalisedGlob.split("/");

		if (!normalisedGlob || normalisedGlob.startsWith("/") || segments.includes("..")) {
			throw new Error(`${label}.globs must contain package-relative paths.`);
		}

		return normalisedGlob;
	});
}

/**
 * Parse a byte budget definition.
 *
 * @param  {unknown}  value
 *     Raw budget from the configuration.
 * @param  {string}  label
 *     Configuration label used in validation errors.
 * @param  {boolean}  requiresName
 *     Whether the budget must include a display name.
 * @returns  {SizeFileBudget | SizeTotalBudget}
 *     Validated budget.
 */
function parseBudget(value: unknown, label: string): ParsedBudget {
	if (!isRecord(value)) {
		throw new Error(`${label} must be an object.`);
	}

	const globs = parseGlobs(value.globs, label);
	const maxBytes = value.maxBytes;

	if (typeof maxBytes !== "number" || !Number.isInteger(maxBytes) || maxBytes < 0) {
		throw new Error(`${label}.maxBytes must be a non-negative integer.`);
	}

	return { globs, maxBytes };
}

/**
 * Parse a per-file budget.
 *
 * @param  {unknown}  value
 *     Raw budget from the configuration.
 * @param  {string}  label
 *     Configuration label used in validation errors.
 * @returns  {SizeFileBudget}
 *     Validated per-file budget.
 */
function parseFileBudget(value: unknown, label: string): SizeFileBudget {
	return parseBudget(value, label);
}

/**
 * Parse a named total budget.
 *
 * @param  {unknown}  value
 *     Raw budget from the configuration.
 * @param  {string}  label
 *     Configuration label used in validation errors.
 * @returns  {SizeTotalBudget}
 *     Validated total budget.
 */
function parseTotalBudget(value: unknown, label: string): SizeTotalBudget {
	const budget = parseBudget(value, label);
	const name = isRecord(value) ? value.name : undefined;

	if (typeof name !== "string" || !name.trim()) {
		throw new Error(`${label}.name must be a non-empty string.`);
	}

	return { ...budget, name };
}

/**
 * Validate the external size budget configuration shape.
 *
 * @param  {unknown}  value
 *     Raw configuration value.
 * @returns  {SizeBudgetConfig}
 *     Validated size budget configuration.
 */
function parseConfig(value: unknown): SizeBudgetConfig {
	if (!isRecord(value) || !isRecord(value.sizeBudgets)) {
		throw new Error("Configuration must contain a sizeBudgets object.");
	}

	const perFile = parseFileBudget(value.sizeBudgets.perFile, "sizeBudgets.perFile");
	const total = value.sizeBudgets.total;

	if (!Array.isArray(total) || total.length === 0) {
		throw new Error("sizeBudgets.total must contain one or more budgets.");
	}

	return {
		sizeBudgets: {
			perFile,
			total: total.map((budget, index) =>
				parseTotalBudget(budget, `sizeBudgets.total[${index}]`),
			),
		},
	};
}

/**
 * Convert a glob pattern into a slash-separated path matcher.
 *
 * @param  {string}  glob
 *     Package-relative glob pattern.
 * @returns  {RegExp}
 *     Anchored regular expression for the glob.
 */
function globToRegExp(glob: string): RegExp {
	let pattern = "^";

	for (let index = 0; index < glob.length; index += 1) {
		const character = glob[index];

		if (character === "*" && glob[index + 1] === "*") {
			if (glob[index + 2] === "/") {
				pattern += "(?:.*/)?";
				index += 2;
			} else {
				pattern += ".*";
				index += 1;
			}

			continue;
		}

		if (character === "*") {
			pattern += "[^/]*";

			continue;
		}

		if (character === "?") {
			pattern += "[^/]";

			continue;
		}

		pattern += character.replace(/[.+^${}()|[\]\\]/g, "\\$&");
	}

	return new RegExp(`${pattern}$`);
}

/**
 * Collect files below a package root as slash-separated relative paths.
 *
 * @param  {string}  directory
 *     Directory currently being traversed.
 * @param  {string}  packageRoot
 *     Absolute package root used to calculate relative paths.
 * @returns  {Promise<string[]>}
 *     Sorted package-relative file paths.
 */
async function collectFiles(directory: string, packageRoot: string): Promise<string[]> {
	const entries = await readdir(directory, { withFileTypes: true });
	const files: string[] = [];

	for (const entry of entries) {
		const absolutePath = join(directory, entry.name);

		if (entry.isDirectory()) {
			files.push(...(await collectFiles(absolutePath, packageRoot)));

			continue;
		}

		if (entry.isFile()) {
			files.push(relative(packageRoot, absolutePath).split(sep).join("/"));
		}
	}

	return files.sort();
}

/**
 * Find unique files matched by one or more package-relative globs.
 *
 * @param  {string[]}  files
 *     Package-relative files available for matching.
 * @param  {string[]}  globs
 *     Package-relative glob patterns.
 * @returns  {string[]}
 *     Sorted matching files without duplicate paths.
 */
function matchFiles(files: string[], globs: string[]): string[] {
	const matchers = globs.map((glob) => globToRegExp(glob));

	return files.filter((file) => matchers.some((matcher) => matcher.test(file)));
}

/**
 * Read file sizes for matched package files.
 *
 * @param  {string}  packageRoot
 *     Absolute package root.
 * @param  {string[]}  files
 *     Package-relative files to measure.
 * @returns  {Promise<FileSize[]>}
 *     Measured files in the requested order.
 */
async function readFileSizes(packageRoot: string, files: string[]): Promise<FileSize[]> {
	return Promise.all(
		files.map(async (file) => ({
			bytes: (await stat(join(packageRoot, file))).size,
			path: file,
		})),
	);
}

/**
 * Format bytes using the package-size check's kilobyte display.
 *
 * @param  {number}  bytes
 *     Byte count to format.
 * @returns  {string}
 *     One-decimal kilobyte display.
 */
function formatBytes(bytes: number): string {
	return `${(bytes / 1024).toFixed(1)} KB`;
}

/**
 * Create a standard over-budget failure row.
 *
 * @param  {string}  target
 *     File or named total budget that exceeded its limit.
 * @param  {number}  actualBytes
 *     Measured bytes.
 * @param  {number}  maxBytes
 *     Allowed bytes.
 * @returns  {SizeCheckFailure}
 *     Failure suitable for CLI reporting.
 */
function createOverBudgetFailure(
	target: string,
	actualBytes: number,
	maxBytes: number,
): SizeCheckFailure {
	return {
		reason: `is ${formatBytes(actualBytes)}, above the ${formatBytes(maxBytes)} budget`,
		target,
	};
}

/**
 * Check every file matched by the per-file budget.
 *
 * @param  {SizeFileBudget} budget
 *     Per-file budget to apply.
 * @param  {FileSize[]}  fileSizes
 *     All files available in the package.
 * @returns  {SizeBudgetResult}
 *     Per-file budget verdict.
 */
function checkPerFileBudget(budget: SizeFileBudget, fileSizes: FileSize[]): SizeBudgetResult {
	const matchedFiles = fileSizes.filter((file) => matchFiles([file.path], budget.globs).length > 0);
	const failures: SizeCheckFailure[] = [];

	if (matchedFiles.length === 0) {
		failures.push({
			reason: `no files matched ${budget.globs.join(", ")}`,
			target: budget.globs.join(", "),
		});
	}

	for (const file of matchedFiles) {
		if (file.bytes > budget.maxBytes) {
			failures.push(createOverBudgetFailure(file.path, file.bytes, budget.maxBytes));
		}
	}

	return {
		checked: matchedFiles.length,
		failures,
		kind: "per-file",
		maxBytes: budget.maxBytes,
		name: "Per-file size",
	};
}

/**
 * Check the combined size of files matched by a named total budget.
 *
 * @param  {SizeTotalBudget} budget
 *     Named total budget to apply.
 * @param  {FileSize[]}  fileSizes
 *     All files available in the package.
 * @returns  {SizeBudgetResult}
 *     Total budget verdict.
 */
function checkTotalBudget(budget: SizeTotalBudget, fileSizes: FileSize[]): SizeBudgetResult {
	const matchedFiles = fileSizes.filter((file) => matchFiles([file.path], budget.globs).length > 0);
	const actualBytes = matchedFiles.reduce((total, file) => total + file.bytes, 0);

	const failures = actualBytes > budget.maxBytes
		? [createOverBudgetFailure(budget.name, actualBytes, budget.maxBytes)]
		: [];

	return {
		actualBytes,
		checked: matchedFiles.length,
		failures,
		kind: "total",
		maxBytes: budget.maxBytes,
		name: budget.name,
	};
}

/**
 * Run configured package size budgets.
 *
 * @param  {string}  packagePath
 *     Package directory supplied by the caller.
 * @param  {unknown}  rawConfig
 *     JSON configuration containing sizeBudgets.
 * @returns  {Promise<SizeCheckResult>}
 *     Combined verdict and flattened failures.
 */
export async function runSizeCheck(
	packagePath: string,
	rawConfig: unknown,
): Promise<SizeCheckResult> {
	if (typeof packagePath !== "string" || !packagePath.trim()) {
		throw new Error("Expected a package directory path.");
	}

	const packageRoot = resolve(packagePath);

	if (!existsSync(packageRoot)) {
		throw new Error(`Package directory not found: ${packagePath}`);
	}

	const config = parseConfig(rawConfig);
	const files = await collectFiles(packageRoot, packageRoot);
	const fileSizes = await readFileSizes(packageRoot, files);

	const results = [
		checkPerFileBudget(config.sizeBudgets.perFile, fileSizes),
		...config.sizeBudgets.total.map((budget) => checkTotalBudget(budget, fileSizes)),
	];

	return {
		failures: results.flatMap(({ failures }) => failures),
		packageRoot,
		results,
	};
}
