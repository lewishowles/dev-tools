# Changelog

All notable changes to `@lewishowles/web-audit` are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/).

## [0.2.1] - 2026-08-30

### Fixed

- CLI report output now goes through the configured `ui` object, so `cli-style` settings apply to audit results and the help text instead of being bypassed by raw `console.log`.

### Changed

- Bumped `@lewishowles/cli-style` to `0.12.1`.

## [0.2.0] - 2026-07-25

### Added

- Added spinner output for browser audit progress.

### Changed

- Bumped `@lewishowles/cli-style` to `0.11.0`.

## [0.1.0] - 2026-07-22

### Added

- Added browser and static HTML audit modes with an axe-core accessibility baseline.
- Added custom ARIA label validity checks and a `render` subcommand for piping rendered HTML to other tools.
- Added fixture-based checks and the npm package release.
