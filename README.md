# dev-tools

A workspace of small, independently versioned CLI tools for accessibility auditing, quality auditing, and content extraction. Each package is a separate tool with its own version and release schedule. This repo is a collection of independent tools sharing a workspace for maintenance convenience, not a single product with one CLI identity.

## Packages

- `packages/web-audit`: rendered-DOM accessibility auditing using TypeScript and Playwright.
- `packages/page-to-markdown`: URL/file/HTML to compact Markdown using Python.
- `packages/package-checks`: package validity checks using TypeScript.
- `packages/project-checks`: project-level diagnostics using Python.

## Workspaces

Two workspaces share this repo root:

- **Bun** (`package.json`) for the TypeScript packages.
- **uv** (`pyproject.toml`) for the Python packages.

Packages compose via stdin/stdout across the language boundary, not shared libraries.
