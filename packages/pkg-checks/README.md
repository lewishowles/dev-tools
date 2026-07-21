# pkg-checks

Checks a JavaScript package for common release problems: incorrect `package.json` exports, runtime dependencies that should be dev dependencies, size budgets, missing type declarations, and missing test coverage.

## Requirements

- Bun or Node

## Getting started

Published as [`@lewishowles/pkg-checks`](https://www.npmjs.com/package/@lewishowles/pkg-checks):

```bash
npm install --save-dev @lewishowles/pkg-checks
```

## Usage

```bash
pkg-checks exports ./packages/helpers
pkg-checks runtime-deps ./packages/helpers --config ./quality.config.json
pkg-checks size ./packages/helpers --config ./quality.config.json
pkg-checks type-declarations ./packages/helpers
pkg-checks test-coverage ./packages/helpers
```

- `exports <package-path>`: checks category barrels and `package.json` exports
- `runtime-deps <package-path>`: checks the configured runtime dependency policy
- `size <package-path>`: checks the configured package size budgets
- `type-declarations <package-path>`: checks that exports have matching type declarations
- `test-coverage <package-path>`: checks that exports have colocated test files

## Configuration

Each check reads its own top-level key from `<package-path>/quality.config.json` by default, or from the path passed to `--config`. You only need the keys for the checks you actually run:

```json
{
	"exportsPolicy": {
		"internalOnly": ["lib/object/path-traversal.js"],
		"fileOnlyEntrypoints": ["./resolver"]
	},
	"sizeBudgets": {
		"perFile": { "globs": ["dist/*.js"], "maxBytes": 12288 },
		"total": [{ "name": "dist total", "globs": ["dist/**"], "maxBytes": 122880 }]
	},
	"runtimeDependencyPolicy": {
		"allowed": ["dayjs"]
	}
}
```

- `exportsPolicy.internalOnly`: helper files that exist in the package but aren't part of its public export barrel, so the `exports` check doesn't flag them as missing
- `exportsPolicy.fileOnlyEntrypoints`: entrypoints (e.g. a CSS file or a resolver) that only need to exist as a file, skipping the barrel/type-declaration checks that apply to regular exports
- `sizeBudgets.perFile`: a `maxBytes` limit applied to every file matching `globs`
- `sizeBudgets.total`: one or more named groups, each with its own `maxBytes` limit across all its matching `globs`
- `runtimeDependencyPolicy.allowed`: dependency names allowed in `dependencies`; anything else there gets flagged (move it to `devDependencies`, or add it here)

## Other packages in this workspace

- [dev-tools](../../README.md)
