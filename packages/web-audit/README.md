# web-audit

Load a page in a real browser (or run a static HTML file) and check it for accessibility issues. Uses Playwright so JS-rendered content works, not just static markup.

## Requirements

- Bun
- Chromium, installed once via Playwright.

## Getting started

Run from the `dev-tools` workspace root:

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
```

Output confirms the page loaded, then reports any accessibility violations found by [axe-core](https://github.com/dequelabs/axe-core):

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
