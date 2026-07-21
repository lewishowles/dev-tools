# web-audit

Load a page in a real browser (or run a static HTML file) and check it for accessibility issues. Uses Playwright so JS-rendered content works, not just static markup.

## Requirements

- Bun
- Chromium, installed once via Playwright.

## Getting started

Not yet published. To use it from another project, link it globally during development:

```bash
cd packages/web-audit
bun install
bun link
```

`web-audit` is then available globally for as long as the link is active.

To work on it from within the `dev-tools` workspace itself, run it from the workspace root:

```bash
bun --filter web-audit web-audit scan-site <url-or-file>
```

Or from inside `packages/web-audit`:

```bash
bun web-audit scan-site <url-or-file>
```

The first run needs Chromium installed for Playwright:

```bash
bunx playwright install chromium
```

## Basic usage

```bash
# A live URL: loads in a real browser
web-audit scan-site https://example.com

# A static HTML file, relative or absolute: no browser rendering needed
web-audit scan-site ./page.html

# Print the rendered HTML of a JS-heavy page, e.g. to pipe into page-to-markdown
web-audit render https://example.com
web-audit render https://example.com --selector "main"
```

`scan-site` output confirms the page loaded, then reports any accessibility violations found by [axe-core](https://github.com/dequelabs/axe-core):

```
Loaded DOM: https://example.com (42 elements)
image-alt (critical): img[src$="logo.png"]
aria-meter-name (serious): [role="meter"]
```

Each violation is one line: `<rule-id> (<severity>): <selector>`. Multiple elements failing the same rule each get their own line. A clean page prints:

```
Loaded DOM: ./page.html (12 elements)
No accessibility violations found.
```

The command exits `0` whether or not violations are found. This is a reporting tool, not a pass/fail gate; it only exits non-zero if the page itself fails to load.

`render` prints the rendered HTML of a page to stdout instead of checking it, useful for feeding a JS-rendered page into `page-to-markdown --stdin`. Add `--selector <css-selector>` to print only a matching element's HTML.
