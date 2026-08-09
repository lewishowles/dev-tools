# Changelog

All notable changes to `project-checks` are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Checked Markdown path references separately from script commands, with explicit planned and historical markers.
- Accepted source-location suffixes and matched globs in current path claims.
- Removed command checks inferred from Markdown examples; missing scripts remain covered as path references.

## [0.2.4] - 2026-08-04

### Added

- Added `--test-match` for selecting targetable test files by a case-insensitive path pattern.
- Added regression coverage for Python pytest check discovery and fuzzy test matching.
- Added `test:unit` discovery for Python projects that contain pytest test files.

## [0.2.3] - 2026-07-22

### Fixed

- Allowed the Markdown claims check to accept Markdown fragments and Python script references.

## [0.2.2] - 2026-07-22

### Changed

- Made the generated-file guard configuration-driven.
- Applied Ruff formatting across the package.

## [0.2.0] - 2026-07-22

### Fixed

- Made the Markdown claims check repository-agnostic.

## [0.1.0] - 2026-07-22

### Added

- Added project diagnostics, generated-file, change-impact and Markdown claims checks.
- Added the repository context briefing command and global console scripts for each check.
- Added the initial PyPI publishing workflow.
