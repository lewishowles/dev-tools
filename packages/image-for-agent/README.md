# image-for-agent

Prepare local images for manual agent input, and generate deterministic benchmark variants for image experiments. The public CLI uses Pillow and works anywhere Python and Pillow are available. The benchmark remains macOS-only and uses the built-in `sips` utility without model or network calls.

## Requirements

- Python 3.11+
- Pillow for the public CLI

The benchmark command additionally requires macOS and `sips`.

## Manual pre-paste use

Run `image-for-agent` before attaching a local screenshot to an agent:

```sh
image-for-agent screenshot.png --output screenshot.ui.png
```

The default `ui` preset removes a detected Retina scale and otherwise keeps the source dimensions. Use `overview` for a 25% native-size summary, `text` when text must stay lossless, or `coordinates` when the report's coordinate mapping matters:

```sh
image-for-agent screenshot.png --preset text --crop 100,80,800,600 --json
```

Crop values use logical source-image coordinates. The report includes the source-pixel crop origin and `coordinate_scale_factor`, so coordinate work can be mapped back to the original image. Retina DPI metadata is used when it is conclusive; missing metadata safely assumes a scale of 1. Use `--retina-scale N` when detection is wrong or absent. Existing output paths are refused rather than overwritten.

`--format jpeg` and `--format webp` are available for `overview`; `ui`, `text` and `coordinates` always write lossless PNG. The JSON report labels Claude 28x28 and OpenAI 32x32 visual patch counts as estimates. Encoded bytes and visual patches are different measures: fewer file bytes do not necessarily mean fewer patches, and neither estimate is vendor billing.

## Benchmark use

The existing benchmark CLI is separate from the public pre-paste command. From the repository root, run it with a source screenshot and manifest:

```sh
image-for-agent-benchmark \
	packages/image-for-agent/benchmark/fixtures/synthetic-ui.png \
	--manifest packages/image-for-agent/benchmark/manifest.json \
	--output-dir packages/image-for-agent/benchmark/variants
```

The command writes generated images and a stable `results.json` below the output directory. See [benchmark/README.md](benchmark/README.md) for the result fields and manual evaluation boundary.

## Key files

- `src/image_for_agent/processor.py`: Pillow processing, presets and report generation.
- `src/image_for_agent/public_cli.py`: public `image-for-agent` command-line entry point.
- `src/image_for_agent/harness.py`: benchmark manifest validation, variant planning and `sips` rendering.
- `src/image_for_agent/cli.py`: benchmark command-line entry point.
- `benchmark/manifest.json`: task questions and variant definitions.
- `benchmark/fixtures/synthetic-ui.png`: tracked fixture used by the benchmark.
