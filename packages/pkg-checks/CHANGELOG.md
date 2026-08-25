# Changelog

All notable changes to `@lewishowles/pkg-checks` are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.4] - 2026-08-25

### Fixed

- Kept the CLI's output formatting aligned with the latest shared `cli-style` release.
- Sent help text and successful check results to standard output so callers can capture normal CLI output separately from errors.

## [0.2.3] - 2026-08-04

### Changed

- Bumped `@lewishowles/cli-style` to `0.11.0` (workspace dependency refresh).
- Renamed the internal unit-test script from `test` to `test:unit`.

## [0.2.2] - 2026-07-22

### Fixed

- Resolved the default export condition in the exports check.

## [0.2.1] - 2026-07-20

### Fixed

- Made the `cli.js` entry point executable through the package `bin` entry.

## [0.2.0] - 2026-07-20

### Added

- Made exports-check exceptions configurable by callers.

## [0.1.0] - 2026-07-20

### Added

- Added checks for package exports, package size, runtime dependencies, type declarations and public exports with tests.
- Added the npm package and its CLI entry point.
