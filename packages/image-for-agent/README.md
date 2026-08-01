# image-for-agent

Generate deterministic image variants for agent input experiments. The harness is offline and macOS-only, using the built-in `sips` utility without model or network calls.

## Requirements

- macOS
- Python 3.11+
- `sips`

## Usage

From the repository root, run the benchmark CLI with a source screenshot and manifest:

```sh
image-for-agent-benchmark \
	packages/image-for-agent/benchmark/fixtures/synthetic-ui.png \
	--manifest packages/image-for-agent/benchmark/manifest.json \
	--output-dir packages/image-for-agent/benchmark/variants
```

The command writes generated images and a stable `results.json` below the output directory. See [benchmark/README.md](benchmark/README.md) for the result fields and manual evaluation boundary.

## Key files

- `src/image_for_agent/harness.py`: manifest validation, variant planning and `sips` rendering.
- `src/image_for_agent/cli.py`: command-line entry point.
- `benchmark/manifest.json`: task questions and variant definitions.
- `benchmark/fixtures/synthetic-ui.png`: tracked fixture used by the benchmark.
