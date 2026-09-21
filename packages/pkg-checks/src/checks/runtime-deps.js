import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";

/**
 * Read a runtime dependency policy configuration file.
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
export async function readRuntimeDependencyConfig(configPath) {
	if (typeof configPath !== "string" || !configPath.trim()) {
		throw new Error("Expected a runtime dependency policy configuration path.");
	}

	// The configuration file contents.
	const source = await readFile(configPath, "utf8");

	try {
		return JSON.parse(source);
	} catch (error) {
		// The parsing failure message.
		const reason = error instanceof Error ? error.message : String(error);

		throw new Error(`Invalid JSON in runtime dependency policy configuration: ${reason}`, {
			cause: error,
		});
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
 * Validate and prepare the runtime dependency policy.
 *
 * @param  {unknown}  value
 *     Configuration value to validate.
 *
 * @throws  {Error}
 *     When the configuration shape is invalid.
 *
 * @returns  {Set<string>}
 *     Allowed dependency names.
 */
function parseConfig(value) {
	if (!isRecord(value) || !isRecord(value.runtimeDependencyPolicy)) {
		throw new Error("Configuration must contain a runtimeDependencyPolicy object.");
	}

	// The configured dependency allow-list.
	const allowed = value.runtimeDependencyPolicy.allowed;

	if (
		!Array.isArray(allowed) ||
		allowed.some((dependency) => typeof dependency !== "string" || !dependency.trim())
	) {
		throw new Error("runtimeDependencyPolicy.allowed must contain dependency names.");
	}

	return new Set(allowed);
}

/**
 * Read and validate a package manifest.
 *
 * @param  {string}  packageRoot
 *     Package directory containing package.json.
 *
 * @throws  {Error}
 *     When package.json is missing or invalid.
 *
 * @returns  {Promise<object>}
 *     Parsed package manifest.
 */
async function readPackageManifest(packageRoot) {
	// The package manifest path.
	const packageJsonPath = join(packageRoot, "package.json");

	if (!existsSync(packageJsonPath)) {
		throw new Error(`package.json not found: ${packageRoot}`);
	}

	// The parsed package manifest.
	const parsed = JSON.parse(await readFile(packageJsonPath, "utf8"));

	if (!isRecord(parsed)) {
		throw new Error("package.json must contain a JSON object.");
	}

	return parsed;
}

/**
 * Find dependencies that are absent from the configured allow-list.
 *
 * @param  {string[]}  dependencies
 *     Dependency names declared by the package.
 * @param  {Set<string>}  allowedDependencies
 *     Approved dependency names.
 *
 * @returns  {object[]}
 *     Failures for every unexpected dependency.
 */
function findUnexpectedDependencies(dependencies, allowedDependencies) {
	return dependencies
		.filter((dependency) => !allowedDependencies.has(dependency))
		.map((dependency) => ({
			reason: "is listed in dependencies but is not allowlisted",
			target: dependency,
		}));
}

/**
 * Check a package's runtime dependencies against its configured policy.
 *
 * @param  {string}  packagePath
 *     Package directory path supplied by the caller.
 * @param  {unknown}  rawConfig
 *     Unvalidated runtime dependency policy configuration.
 *
 * @throws  {Error}
 *     When the package path, policy configuration, package.json, or
 *     dependencies value is invalid.
 *
 * @returns  {Promise<object>}
 *     Combined runtime dependency results.
 */
export async function runRuntimeDependencyCheck(packagePath, rawConfig) {
	if (typeof packagePath !== "string" || !packagePath.trim()) {
		throw new Error("Expected a package directory path.");
	}

	// The absolute package directory.
	const packageRoot = resolve(packagePath);

	if (!existsSync(packageRoot)) {
		throw new Error(`Package directory not found: ${packagePath}`);
	}

	// The approved dependency names.
	const allowedDependencies = parseConfig(rawConfig);
	// Use the package manifest to inspect the declared dependencies.
	const manifest = await readPackageManifest(packageRoot);
	// The package's declared runtime dependencies.
	const dependencies = manifest.dependencies ?? {};

	if (!isRecord(dependencies)) {
		throw new Error("package.json dependencies must contain an object.");
	}

	// Compare the declared names with the approved allow-list.
	const dependencyNames = Object.keys(dependencies);
	// The dependencies outside the approved allow-list.
	const failures = findUnexpectedDependencies(dependencyNames, allowedDependencies);

	// The summary for this package.
	const result = {
		checked: dependencyNames.length,
		failures,
		mode: "runtime-dependencies",
	};

	return {
		failures,
		packageRoot,
		results: [result],
	};
}
