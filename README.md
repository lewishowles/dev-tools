# dev-tools

A workspace of small, independently versioned CLI tools for accessibility auditing, quality auditing, and content extraction. Each package is a separate tool with its own version and release schedule. This repo is a collection of independent tools sharing a workspace for maintenance convenience, not a single product with one CLI identity.

## Packages

- [`packages/web-audit`](packages/web-audit/README.md): rendered-DOM accessibility auditing using TypeScript and Playwright.
- [`packages/pkg-checks`](packages/pkg-checks/README.md): package validity checks using TypeScript.

## Workspace

The Bun workspace in `package.json` contains the packages in this repository.

Packages compose via stdin/stdout, not shared libraries.
