import { existsSync } from "node:fs";
import { readFile, readdir, stat } from "node:fs/promises";
import { join, relative, resolve, sep } from "node:path";

/**
 * Read a size-budget configuration file.
 *
 * @param  {string}  configPath
 *     Configuration file path.
 *
 * @throws  {Error}
 *     When the path or file contents are invalid.
 *
 * @returns  {Promise<unknown>}
 *     Parsed configuration value.
 */
export async function readSizeConfig(configPath) {
	if (typeof configPath !== "string" || !configPath.trim()) {
		throw new Error("Expected a size budget configuration path.");
	}

	// The size-budget file contents.
	const source = await readFile(configPath, "utf8");

	try {
		return JSON.parse(source);
	} catch (error) {
		// The parsing failure message.
		const reason = error instanceof Error ? error.message : String(error);

		throw new Error(`Invalid JSON in size budget configuration: ${reason}`, { cause: error });
	}
}

/**
 * Determine whether a value is a non-array object.
 *
 * @param  {unknown}  value
 *     Value to inspect.
 *
 * @returns  {boolean}
 *     True when the value is an object record.
 */
function isRecord(value) {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Validate and normalise package-relative glob patterns.
 *
 * @param  {unknown}  value
 *     Glob collection to validate.
 * @param  {string}  label
 *     Configuration label used in validation errors.
 *
 * @throws  {Error}
 *     When the configured globs are invalid.
 *
 * @returns  {string[]}
 *     Normalised glob patterns.
 */
function parseGlobs(value, label) {
	if (
		!Array.isArray(value) ||
		value.length === 0 ||
		value.some((glob) => typeof glob !== "string" || !glob.trim())
	) {
		throw new Error(`${label}.globs must contain one or more non-empty strings.`);
	}

	return value.map((glob) => {
		// The normalised glob pattern.
		const normalisedGlob = glob.replaceAll("\\", "/").replace(/^\.\/+/, "");
		// The path segments used to validate the pattern.
		const segments = normalisedGlob.split("/");

		if (!normalisedGlob || normalisedGlob.startsWith("/") || segments.includes("..")) {
			throw new Error(`${label}.globs must contain package-relative paths.`);
		}

		return normalisedGlob;
	});
}

/**
 * Validate a per-file or total size budget.
 *
 * @param  {unknown}  value
 *     Budget value to validate.
 * @param  {string}  label
 *     Configuration label used in validation errors.
 *
 * @throws  {Error}
 *     When the budget shape is invalid.
 *
 * @returns  {object}
 *     Validated glob and byte limit.
 */
function parseBudget(value, label) {
	if (!isRecord(value)) {
		throw new Error(`${label} must be an object.`);
	}

	// The per-file budget globs.
	const globs = parseGlobs(value.globs, label);
	// The maximum allowed file size.
	const maxBytes = value.maxBytes;

	if (typeof maxBytes !== "number" || !Number.isInteger(maxBytes) || maxBytes < 0) {
		throw new Error(`${label}.maxBytes must be a non-negative integer.`);
	}

	return { globs, maxBytes };
}

/**
 * Validate a per-file size budget.
 *
 * @param  {unknown}  value
 *     Budget value to validate.
 * @param  {string}  label
 *     Configuration label used in validation errors.
 *
 * @returns  {object}
 *     Validated per-file budget.
 */
function parseFileBudget(value, label) {
	return parseBudget(value, label);
}

/**
 * Validate a named total size budget.
 *
 * @param  {unknown}  value
 *     Budget value to validate.
 * @param  {string}  label
 *     Configuration label used in validation errors.
 *
 * @throws  {Error}
 *     When the configuration shape is invalid.
 *
 * @returns  {object}
 *     Validated total budget.
 */
function parseTotalBudget(value, label) {
	// The validated total budget.
	const budget = parseBudget(value, label);
	// The configured total budget name.
	const name = isRecord(value) ? value.name : undefined;

	if (typeof name !== "string" || !name.trim()) {
		throw new Error(`${label}.name must be a non-empty string.`);
	}

	return { ...budget, name };
}

/**
 * Validate the supported size-budget configuration shape.
 *
 * @param  {unknown}  value
 *     Configuration value to validate.
 *
 * @throws  {Error}
 *     When the configuration shape is invalid.
 *
 * @returns  {object}
 *     Validated size-budget configuration.
 */
function parseConfig(value) {
	if (!isRecord(value) || !isRecord(value.sizeBudgets)) {
		throw new Error("Configuration must contain a sizeBudgets object.");
	}

	// The per-file budget.
	const perFile = parseFileBudget(value.sizeBudgets.perFile, "sizeBudgets.perFile");
	// The total budgets.
	const total = value.sizeBudgets.total;

	if (!Array.isArray(total) || total.length === 0) {
		throw new Error("sizeBudgets.total must contain one or more budgets.");
	}

	return {
		sizeBudgets: {
			perFile,
			total: total.map((budget, index) => parseTotalBudget(budget, `sizeBudgets.total[${index}]`)),
		},
	};
}

/**
 * Convert a supported glob pattern into a file-path matcher.
 *
 * @param  {string}  glob
 *     Glob pattern to convert.
 *
 * @returns  {RegExp}
 *     Regular expression matching the glob.
 */
function globToRegExp(glob) {
	// The regular expression under construction.
	let pattern = "^";

	for (let index = 0; index < glob.length; index += 1) {
		// The current glob character.
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
 * Collect files below a package directory as package-relative paths.
 *
 * @param  {string}  directory
 *     Directory to traverse.
 * @param  {string}  packageRoot
 *     Package root used for relative paths.
 *
 * @returns  {Promise<string[]>}
 *     Sorted package-relative file paths.
 */
async function collectFiles(directory, packageRoot) {
	// The directory entries.
	const entries = await readdir(directory, { withFileTypes: true });
	// The collected package-relative files.
	const files = [];

	for (const entry of entries) {
		// The absolute path for the current entry.
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
 * Return files matching at least one configured glob.
 *
 * @param  {string[]}  files
 *     Package-relative file paths.
 * @param  {string[]}  globs
 *     Glob patterns to apply.
 *
 * @returns  {string[]}
 *     Matching file paths.
 */
function matchFiles(files, globs) {
	// The compiled glob matchers.
	const matchers = globs.map((glob) => globToRegExp(glob));

	return files.filter((file) => matchers.some((matcher) => matcher.test(file)));
}

/**
 * Read byte sizes for selected package files.
 *
 * @param  {string}  packageRoot
 *     Package root containing the files.
 * @param  {string[]}  files
 *     Package-relative file paths.
 *
 * @returns  {Promise<object[]>}
 *     Files paired with their byte sizes.
 */
async function readFileSizes(packageRoot, files) {
	return Promise.all(
		files.map(async (file) => ({
			bytes: (await stat(join(packageRoot, file))).size,
			path: file,
		})),
	);
}

/**
 * Format a byte count for CLI output.
 *
 * @param  {number}  bytes
 *     Byte count to format.
 *
 * @returns  {string}
 *     Human-readable size.
 */
function formatBytes(bytes) {
	return `${(bytes / 1024).toFixed(1)} KB`;
}

/**
 * Build a failure for a budget that has been exceeded.
 *
 * @param  {string}  target
 *     File or budget name that exceeded its limit.
 * @param  {number}  actualBytes
 *     Measured byte count.
 * @param  {number}  maxBytes
 *     Allowed byte count.
 *
 * @returns  {object}
 *     Formatted budget failure.
 */
function createOverBudgetFailure(target, actualBytes, maxBytes) {
	return {
		reason: `is ${formatBytes(actualBytes)}, above the ${formatBytes(maxBytes)} budget`,
		target,
	};
}

/**
 * Check each file against a per-file byte budget.
 *
 * @param  {object}  budget
 *     Per-file budget to apply.
 * @param  {object[]}  fileSizes
 *     Measured package files.
 *
 * @returns  {object}
 *     Per-file budget result.
 */
function checkPerFileBudget(budget, fileSizes) {
	// The files matching the current budget.
	const matchedFiles = fileSizes.filter((file) => matchFiles([file.path], budget.globs).length > 0);
	// The budget failures.
	const failures = [];

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
 * Check the combined size of files against a total byte budget.
 *
 * @param  {object}  budget
 *     Total budget to apply.
 * @param  {object[]}  fileSizes
 *     Measured package files.
 *
 * @returns  {object}
 *     Total budget result.
 */
function checkTotalBudget(budget, fileSizes) {
	// The files matching the current budget.
	const matchedFiles = fileSizes.filter((file) => matchFiles([file.path], budget.globs).length > 0);
	// The combined size of the matching files.
	const actualBytes = matchedFiles.reduce((total, file) => total + file.bytes, 0);

	// The total-budget failures.
	const failures =
		actualBytes > budget.maxBytes
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
 * Run all configured package size checks.
 *
 * @param  {string}  packagePath
 *     Package directory path supplied by the caller.
 * @param  {unknown}  rawConfig
 *     Unvalidated size-budget configuration.
 *
 * @throws  {Error}
 *     When the package path or budget configuration is invalid.
 *
 * @returns  {Promise<object>}
 *     Combined size-check results.
 */
export async function runSizeCheck(packagePath, rawConfig) {
	if (typeof packagePath !== "string" || !packagePath.trim()) {
		throw new Error("Expected a package directory path.");
	}

	// The resolved package directory.
	const packageRoot = resolve(packagePath);

	if (!existsSync(packageRoot)) {
		throw new Error(`Package directory not found: ${packagePath}`);
	}

	// The validated size-budget configuration.
	const config = parseConfig(rawConfig);
	// The package-relative files.
	const files = await collectFiles(packageRoot, packageRoot);
	// The measured file sizes.
	const fileSizes = await readFileSizes(packageRoot, files);

	// The per-file and total budget results.
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
