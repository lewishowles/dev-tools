"""Generate deterministic image variants with the macOS ``sips`` utility."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Callable


class HarnessError(Exception):
	"""Describe an input, image-processing, or output failure."""


@dataclass(frozen=True)
class Crop:
	"""Describe a source-image crop in pixels."""

	x: int
	y: int
	width: int
	height: int

	def as_dict(self) -> dict[str, int]:
		"""Return the crop using the manifest's stable field names."""
		return {
			"height": self.height,
			"width": self.width,
			"x": self.x,
			"y": self.y,
		}


@dataclass(frozen=True)
class VariantSpec:
	"""Describe one named target in the benchmark manifest."""

	name: str
	target: dict[str, Any]
	output_format: str
	quality: str | int | None
	crop: Crop | None
	pair_with: str | None


@dataclass(frozen=True)
class VariantPlan:
	"""Store the resolved dimensions and source region for one variant."""

	spec: VariantSpec
	source_crop: Crop | None
	region_width: int
	region_height: int
	result_width: int
	result_height: int
	should_render: bool
	reason: str | None = None


Runner = Callable[..., subprocess.CompletedProcess[str]]

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SUPPORTED_FORMATS = frozenset({"png"})
_REQUIRED_TASK_CLASSES = ("overview", "ui", "text", "coordinates")


def load_manifest(path: Path) -> dict[str, Any]:
	"""Load and validate a benchmark manifest without external dependencies."""
	try:
		with path.open(encoding="utf-8") as manifest_file:
			manifest = json.load(manifest_file)
	except FileNotFoundError as error:
		raise HarnessError(f"benchmark manifest does not exist: {path}") from error
	except json.JSONDecodeError as error:
		raise HarnessError(f"benchmark manifest is not valid JSON: {error}") from error

	_validate_manifest(manifest, path)
	return manifest


def build_variant_specs(manifest: dict[str, Any]) -> list[VariantSpec]:
	"""Convert manifest variant records into validated typed specifications."""
	specs = []
	for record in manifest["variants"]:
		crop_record = record.get("crop")
		crop = _parse_crop(crop_record) if crop_record is not None else None
		specs.append(
			VariantSpec(
				name=record["name"],
				target=record["target"],
				output_format=record["format"],
				quality=record.get("quality"),
				crop=crop,
				pair_with=record.get("pair_with"),
			)
		)

	return specs


def plan_variant(
	spec: VariantSpec,
	source_width: int,
	source_height: int,
	retina_scale: float = 1,
) -> VariantPlan:
	"""Resolve a target without ever selecting dimensions larger than its source."""
	source_crop = _scale_crop(spec.crop, retina_scale)
	if source_crop is not None:
		_validate_crop_bounds(source_crop, source_width, source_height)
		region_width = source_crop.width
		region_height = source_crop.height
	else:
		region_width = source_width
		region_height = source_height

	result_width, result_height = _target_dimensions(
		spec.target,
		region_width,
		region_height,
		retina_scale,
	)
	crop_changes_image = source_crop is not None and (
		source_crop.x != 0
		or source_crop.y != 0
		or region_width != source_width
		or region_height != source_height
	)
	should_render = crop_changes_image or (
		result_width < region_width or result_height < region_height
	)

	if should_render:
		reason = None
	else:
		reason = "target is not smaller than the source region"

	return VariantPlan(
		spec=spec,
		source_crop=source_crop,
		region_width=region_width,
		region_height=region_height,
		result_width=result_width,
		result_height=result_height,
		should_render=should_render,
		reason=reason,
	)


def estimate_patches(width: int, height: int) -> dict[str, int]:
	"""Estimate visual patch counts using the fixed benchmark formulas."""
	return {
		"claude_estimated_28x28_patches": math.ceil(width / 28)
		* math.ceil(height / 28),
		"openai_estimated_32x32_patches": math.ceil(width / 32)
		* math.ceil(height / 32),
	}


def run_benchmark(
	input_path: Path,
	manifest: dict[str, Any],
	output_dir: Path,
	runner: Runner = subprocess.run,
) -> dict[str, Any]:
	"""Render all eligible variants and return a deterministic JSON structure."""
	if not input_path.is_file():
		raise HarnessError(f"input image does not exist: {input_path}")

	output_dir.mkdir(parents=True, exist_ok=True)
	source_bytes = input_path.read_bytes()
	source_width, source_height = read_image_dimensions(input_path, runner)
	source_identity = {
		"screenshot_ref": manifest["source"]["screenshot_ref"],
		"sha256": hashlib.sha256(source_bytes).hexdigest(),
	}
	source_size = len(source_bytes)

	variants = []
	skipped_variants = []
	retina_scale = manifest["source"]["retina_scale"]
	for spec in build_variant_specs(manifest):
		plan = plan_variant(spec, source_width, source_height, retina_scale)
		if not plan.should_render:
			skipped_variants.append(
				{
					"name": spec.name,
					"reason": plan.reason,
				}
			)
			continue

		output_name = f"{spec.name}.{spec.output_format}"
		output_path = output_dir / output_name
		_render_variant(input_path, output_path, plan, runner)
		result_width, result_height = read_image_dimensions(output_path, runner)
		variants.append(
			_build_variant_result(
				spec,
				plan,
				output_name,
				result_width,
				result_height,
				output_path.stat().st_size,
				source_width,
				source_height,
				source_size,
				source_identity,
			)
		)

	return {
		"schema_version": manifest["schema_version"],
		"source": {
			"input_identity": source_identity,
			"original_encoded_bytes": source_size,
			"original_height": source_height,
			"original_width": source_width,
		},
		"task_classes": manifest["task_classes"],
		"questions": manifest["questions"],
		"variants": variants,
		"skipped_variants": skipped_variants,
	}


def write_result(path: Path, result: dict[str, Any]) -> None:
	"""Write a stable, timestamp-free benchmark result manifest."""
	try:
		path.parent.mkdir(parents=True, exist_ok=True)
		with path.open("w", encoding="utf-8", newline="\n") as result_file:
			json.dump(
				result,
				result_file,
				ensure_ascii=False,
				indent=2,
				sort_keys=True,
			)
			result_file.write("\n")
	except OSError as error:
		raise HarnessError(
			f"could not write result manifest {path}: {error}"
		) from error


def read_image_dimensions(path: Path, runner: Runner) -> tuple[int, int]:
	"""Read pixel dimensions from ``sips`` output."""
	try:
		completed = runner(
			[
				"sips",
				"-g",
				"pixelHeight",
				"-g",
				"pixelWidth",
				str(path),
			],
			check=True,
			capture_output=True,
			text=True,
		)
	except FileNotFoundError as error:
		raise HarnessError(
			"macOS 'sips' is required; this benchmark harness is macOS-only"
		) from error
	except subprocess.CalledProcessError as error:
		details = (error.stderr or error.stdout or "").strip()
		raise HarnessError(
			f"sips could not inspect {path}: {details or 'unknown error'}"
		) from error

	dimensions = {}
	for line in completed.stdout.splitlines():
		key, separator, value = line.partition(":")
		if separator and key.strip() in {"pixelWidth", "pixelHeight"}:
			try:
				dimensions[key.strip()] = int(value.strip())
			except ValueError as error:
				raise HarnessError(
					f"sips returned an invalid dimension for {path}: {line.strip()}"
				) from error

	try:
		return dimensions["pixelWidth"], dimensions["pixelHeight"]
	except KeyError as error:
		raise HarnessError(f"sips did not report dimensions for {path}") from error


def _render_variant(
	input_path: Path,
	output_path: Path,
	plan: VariantPlan,
	runner: Runner,
) -> None:
	"""Apply an optional crop and downsample one source image with ``sips``."""
	render_source = input_path
	if plan.source_crop is not None:
		crop_command = [
			"sips",
			"--cropToHeightWidth",
			str(plan.source_crop.height),
			str(plan.source_crop.width),
			"--cropOffset",
			str(plan.source_crop.y),
			str(plan.source_crop.x),
			"--setProperty",
			"format",
			plan.spec.output_format,
			"--out",
			str(output_path),
			str(input_path),
		]
		_run_sips(crop_command, plan.spec.name, runner)
		render_source = output_path

	if (plan.result_width, plan.result_height) != (
		plan.region_width,
		plan.region_height,
	):
		resize_command = [
			"sips",
			"--resampleHeightWidth",
			str(plan.result_height),
			str(plan.result_width),
			"--setProperty",
			"format",
			plan.spec.output_format,
			"--out",
			str(output_path),
			str(render_source),
		]
		_run_sips(resize_command, plan.spec.name, runner)


def _run_sips(command: list[str], variant_name: str, runner: Runner) -> None:
	"""Run one ``sips`` operation and translate failures to harness errors."""
	try:
		runner(command, check=True, capture_output=True, text=True)
	except FileNotFoundError as error:
		raise HarnessError(
			"macOS 'sips' is required; this benchmark harness is macOS-only"
		) from error
	except subprocess.CalledProcessError as error:
		details = (error.stderr or error.stdout or "").strip()
		raise HarnessError(
			f"sips could not render {variant_name}: {details or 'unknown error'}"
		) from error


def _build_variant_result(
	spec: VariantSpec,
	plan: VariantPlan,
	output_name: str,
	result_width: int,
	result_height: int,
	result_size: int,
	source_width: int,
	source_height: int,
	source_size: int,
	source_identity: dict[str, str],
) -> dict[str, Any]:
	"""Build the stable metadata record for one rendered image."""
	region_width = plan.region_width
	region_height = plan.region_height
	coordinate_scale_factor = {
		"x": _round_factor(region_width / result_width),
		"y": _round_factor(region_height / result_height),
	}
	coordinate_origin = {
		"x": plan.source_crop.x if plan.source_crop else 0,
		"y": plan.source_crop.y if plan.source_crop else 0,
	}

	return {
		"applied_crop": spec.crop.as_dict() if spec.crop else None,
		"coordinate_origin": coordinate_origin,
		"coordinate_scale_factor": coordinate_scale_factor,
		**estimate_patches(result_width, result_height),
		"format": spec.output_format,
		"legibility_coordinate_warning": _warning_for(spec),
		"named_variant": spec.name,
		"original_encoded_bytes": source_size,
		"original_height": source_height,
		"original_width": source_width,
		"output_path": output_name,
		"pair_with": spec.pair_with,
		"quality": spec.quality,
		"result_encoded_bytes": result_size,
		"result_height": result_height,
		"result_width": result_width,
		"source_identity": source_identity,
	}


def _target_dimensions(
	target: dict[str, Any],
	region_width: int,
	region_height: int,
	retina_scale: float,
) -> tuple[int, int]:
	"""Calculate a bounded, aspect-preserving target size."""
	kind = target["kind"]
	if kind == "logical_retina":
		return _bounded_dimensions(
			region_width / retina_scale,
			region_height / retina_scale,
		)
	if kind == "bounding_box":
		scale = min(
			target["max_width"] / region_width,
			target["max_height"] / region_height,
			1,
		)
		return _bounded_dimensions(region_width * scale, region_height * scale)
	if kind == "long_edge":
		scale = min(1, target["value"] / max(region_width, region_height))
		return _bounded_dimensions(region_width * scale, region_height * scale)

	raise HarnessError(f"unsupported target kind: {kind}")


def _bounded_dimensions(width: float, height: float) -> tuple[int, int]:
	"""Round dimensions while keeping both axes positive and bounded."""
	return max(1, round(width)), max(1, round(height))


def _parse_crop(record: dict[str, Any]) -> Crop:
	"""Convert one manifest crop object into a typed crop."""
	return Crop(
		x=record["x"],
		y=record["y"],
		width=record["width"],
		height=record["height"],
	)


def _scale_crop(crop: Crop | None, retina_scale: float) -> Crop | None:
	"""Convert logical crop coordinates into source-image pixels."""
	if crop is None:
		return None

	return Crop(
		x=round(crop.x * retina_scale),
		y=round(crop.y * retina_scale),
		width=round(crop.width * retina_scale),
		height=round(crop.height * retina_scale),
	)


def _validate_manifest(manifest: Any, path: Path) -> None:
	"""Raise a useful error for malformed benchmark input."""
	if not isinstance(manifest, dict):
		raise HarnessError(f"benchmark manifest must be an object: {path}")
	for field in ("schema_version", "source", "task_classes", "questions", "variants"):
		if field not in manifest:
			raise HarnessError(f"benchmark manifest is missing '{field}': {path}")

	task_class_ids = {record.get("id") for record in manifest["task_classes"]}
	missing_classes = set(_REQUIRED_TASK_CLASSES) - task_class_ids
	if missing_classes:
		raise HarnessError(
			"benchmark manifest is missing task classes: "
			+ ", ".join(sorted(missing_classes))
		)

	questions = manifest["questions"]
	if not questions:
		raise HarnessError("benchmark manifest must define at least one question")
	for question in questions:
		for field in (
			"id",
			"task_class",
			"screenshot_ref",
			"question",
			"expected_answer",
			"notes",
		):
			if field not in question:
				raise HarnessError(f"question record is missing '{field}'")
		if question["task_class"] not in task_class_ids:
			raise HarnessError(
				f"question '{question['id']}' uses an unknown task class"
			)

	for variant in manifest["variants"]:
		name = variant.get("name")
		if not isinstance(name, str) or not _NAME_PATTERN.fullmatch(name):
			raise HarnessError(
				f"variant names must contain only letters, numbers, '.', '_' or '-': {name}"
			)
		if variant.get("format") not in _SUPPORTED_FORMATS:
			raise HarnessError(f"unsupported output format for '{name}'; use: png")
		if variant.get("target", {}).get("kind") not in {
			"logical_retina",
			"bounding_box",
			"long_edge",
		}:
			raise HarnessError(f"variant '{name}' has an unsupported target")

	for spec in build_variant_specs_unchecked(manifest):
		if spec.crop is not None:
			_validate_crop_positive(spec.crop)


def build_variant_specs_unchecked(manifest: dict[str, Any]) -> list[VariantSpec]:
	"""Build specs during validation without recursively validating the manifest."""
	specs = []
	for record in manifest["variants"]:
		crop_record = record.get("crop")
		specs.append(
			VariantSpec(
				name=record["name"],
				target=record["target"],
				output_format=record["format"],
				quality=record.get("quality"),
				crop=_parse_crop(crop_record) if crop_record is not None else None,
				pair_with=record.get("pair_with"),
			)
		)
	return specs


def _validate_crop_positive(crop: Crop) -> None:
	"""Ensure crop dimensions can be passed safely to ``sips``."""
	if crop.x < 0 or crop.y < 0 or crop.width <= 0 or crop.height <= 0:
		raise HarnessError(
			"crop x/y must be non-negative and width/height must be positive"
		)


def _validate_crop_bounds(crop: Crop, source_width: int, source_height: int) -> None:
	"""Ensure a crop stays within the source image."""
	_validate_crop_positive(crop)
	if crop.x + crop.width > source_width or crop.y + crop.height > source_height:
		raise HarnessError("crop must stay within the source image bounds")


def _warning_for(spec: VariantSpec) -> str | None:
	"""Describe the known visual or coordinate caution for a variant."""
	if spec.crop is not None:
		return "Cropped output: add coordinate_origin before applying coordinate_scale_factor."
	if spec.name.startswith("512"):
		return "Small text may be illegible; use a text crop or a larger variant when text matters."
	if spec.name.startswith("coordinates"):
		return "Map coordinates through coordinate_scale_factor before acting on the source."
	return None


def _round_factor(value: float) -> float:
	"""Keep scale metadata precise without exposing floating-point noise."""
	return round(value, 8)
