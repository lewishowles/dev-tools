# Image-for-agent benchmark harness

This package is an offline harness for measuring screenshot variants before any model-facing image tool is chosen. It makes no model, network, clipboard or MCP calls.

## Requirements

The harness is macOS-only because it shells out to the built-in `sips` utility. It deliberately does not add Pillow or another Python image dependency. The public `image-for-agent` CLI and backend remain out of scope.

## Run it

From the repository root:

```sh
image-for-agent-benchmark \
	packages/image-for-agent/benchmark/fixtures/synthetic-ui.png \
	--manifest packages/image-for-agent/benchmark/manifest.json \
	--output-dir packages/image-for-agent/benchmark/variants
```

The command writes generated images and `results.json` below the ignored output directory. The result is JSON-first and contains only stable fields, so two runs against the same input and manifest can be compared byte-for-byte. Output paths are relative to the output directory and source identity is based on the fixture reference and SHA-256, not an absolute local path.

Targets are aspect-preserving and bounded by the source region. A target that would upscale the source is recorded in `skipped_variants` and no image is written. The `text-crop-512` record is paired with the full-screen `512-long-edge` record for a task-relevant crop comparison.

## Result fields

Each generated record reports the output path, named variant, source identity, original and result dimensions, encoded byte counts, format, quality, applied crop, crop origin, x/y coordinate scale factors, a legibility or coordinate warning, and estimated visual patches.

Coordinate mapping is:

```text
source_x = coordinate_origin.x + variant_x * coordinate_scale_factor.x
source_y = coordinate_origin.y + variant_y * coordinate_scale_factor.y
```

Patch counts are estimates, not vendor billing or token measurements:

```text
Claude estimate = ceil(result_width / 28) * ceil(result_height / 28)
OpenAI estimate = ceil(result_width / 32) * ceil(result_height / 32)
```

The benchmark defines four task classes: `overview`, `ui`, `text` and `coordinates`. Fixed-question records carry `id`, `task_class`, `screenshot_ref`, `question`, `expected_answer` and `notes`. Edit `manifest.json` for a new synthetic or locally ignored input, keeping private screenshots outside tracked fixtures.

## Manual evaluation boundary

First generate the variants and inspect the dimensions, byte counts and warnings. Then paste selected files into separately approved agent sessions and record answers against the fixed questions. Model identity, latency and correctness belong in a later benchmark record. Do not add model calls, clipboard integration or MCP interception to this package without a separate scope decision.
