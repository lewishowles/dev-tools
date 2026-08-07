# Changelog

All notable changes to `image-for-agent` are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-08-07

### Added

- Added the `image-for-agent` CLI, producing agent-ready image variants (overview, ui, text, coordinates presets) with deterministic crop, resize and format handling, backed by Pillow.
- Added the offline image variant benchmark harness, with deterministic presets, crop and coordinate metadata, byte measurements and estimated model patch counts.
