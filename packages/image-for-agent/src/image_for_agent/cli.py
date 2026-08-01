"""Command-line entry point for the offline image variant harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from image_for_agent.harness import (
	HarnessError,
	load_manifest,
	run_benchmark,
	write_result,
)


def build_parser() -> argparse.ArgumentParser:
	"""Build the benchmark command parser."""
	parser = argparse.ArgumentParser(
		prog="image-for-agent-benchmark",
		description=(
			"Generate deterministic macOS sips image variants without model or network calls."
		),
	)
	parser.add_argument("input", type=Path, help="Source screenshot to benchmark.")
	parser.add_argument(
		"--manifest",
		type=Path,
		required=True,
		help="Benchmark manifest containing task classes, questions and variants.",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		required=True,
		help="Directory for generated variant images.",
	)
	parser.add_argument(
		"--result",
		type=Path,
		default=None,
		help="Result JSON path. Defaults to OUTPUT_DIR/results.json.",
	)
	return parser


def main(argv: list[str] | None = None) -> int:
	"""Generate the requested variants and write a JSON-first summary."""
	args = build_parser().parse_args(argv)
	result_path = args.result or args.output_dir / "results.json"

	try:
		result = run_benchmark(
			args.input,
			load_manifest(args.manifest),
			args.output_dir,
		)
		write_result(result_path, result)
	except HarnessError as error:
		print(f"error: {error}", file=sys.stderr)
		return 2

	print(
		json.dumps(
			{
				"result": str(result_path),
				"generated": len(result["variants"]),
				"skipped": len(result["skipped_variants"]),
			},
			sort_keys=True,
		)
	)
	return 0
