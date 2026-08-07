"""Command-line entry point for preparing an image for agent input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from image_for_agent import style
from image_for_agent.processor import (
	PRESETS,
	Crop,
	ImageForAgentError,
	parse_crop,
	process_image,
)


def build_parser() -> argparse.ArgumentParser:
	"""Build the public image preparation command parser."""
	parser = argparse.ArgumentParser(
		prog="image-for-agent",
		description=(
			"Prepare a local image for manual agent input and report bytes, patches and coordinates."
		),
		epilog=(
			"Example: image-for-agent screenshot.png --preset text "
			"--crop 100,80,800,600 --json"
		),
	)
	parser.add_argument("input", type=Path, help="Source image to prepare.")
	parser.add_argument(
		"--preset",
		choices=PRESETS,
		default="ui",
		help="Preparation policy. Defaults to ui.",
	)
	parser.add_argument(
		"--crop",
		type=_crop_argument,
		default=None,
		metavar="X,Y,WIDTH,HEIGHT",
		help="Optional crop in logical source-image coordinates.",
	)
	parser.add_argument(
		"--output",
		type=Path,
		default=None,
		metavar="PATH",
		help="Destination path. Existing files are never overwritten.",
	)
	parser.add_argument(
		"--format",
		choices=("png", "jpeg", "jpg", "webp"),
		default=None,
		help="Output format override. Lossy formats are available for overview only.",
	)
	parser.add_argument(
		"--retina-scale",
		type=_retina_scale_argument,
		default=None,
		metavar="N",
		help="Manual source-to-logical Retina scale override, at least 1.",
	)
	parser.add_argument(
		"--json",
		action="store_true",
		help="Print the complete machine-readable report as JSON.",
	)
	return parser


def main(argv: list[str] | None = None) -> int:
	"""Prepare one image and report failures without touching the input.

	Args:
		argv: Optional command-line arguments, excluding the executable name.

	Returns:
		0 when the output and report are written, or 2 when preparation fails.
	"""
	args = build_parser().parse_args(argv)

	try:
		report = process_image(
			args.input,
			preset=args.preset,
			crop=args.crop,
			output_path=args.output,
			retina_scale=args.retina_scale,
			output_format=args.format,
		)
	except ImageForAgentError as error:
		if args.json:
			print(json.dumps({"error": str(error)}, sort_keys=True))
		else:
			print(style.status("failed", "Error", str(error)), file=sys.stderr)
		return 2

	if args.json:
		print(json.dumps(report, sort_keys=True))
		return 0

	print(style.status("success", "Created", report["output_path"]))
	print(
		style.row_group(
			[
				{
					"label": "Dimensions",
					"value": (
						f"{report['original_width']}x{report['original_height']} -> "
						f"{report['result_width']}x{report['result_height']}"
					),
				},
				{
					"label": "Bytes",
					"value": (
						f"{report['original_encoded_bytes']} -> "
						f"{report['result_encoded_bytes']}"
					),
				},
				{
					"label": "Coordinate scale",
					"value": json.dumps(
						report["coordinate_scale_factor"], sort_keys=True
					),
				},
				{
					"label": "Patch estimates",
					"value": (
						f"Claude 28x28: {report['claude_estimated_28x28_patches']}; "
						f"OpenAI 32x32: {report['openai_estimated_32x32_patches']}"
					),
				},
			]
		)
	)
	for warning in report["warnings"]:
		print(style.status("warning", "Warning", warning), file=sys.stderr)

	return 0


def _crop_argument(value: str) -> Crop:
	"""Adapt crop validation errors for argparse."""
	try:
		return parse_crop(value)
	except ValueError as error:
		raise argparse.ArgumentTypeError(str(error)) from error


def _retina_scale_argument(value: str) -> float:
	"""Adapt Retina scale validation errors for argparse."""
	try:
		retina_scale = float(value)
	except ValueError as error:
		raise argparse.ArgumentTypeError(
			"retina scale must be a number at least 1"
		) from error

	if retina_scale < 1:
		raise argparse.ArgumentTypeError("retina scale must be a number at least 1")

	return retina_scale
