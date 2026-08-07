"""Prepare local images for manual agent input."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
import math
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


PRESETS = ("overview", "ui", "text", "coordinates")
LOSSLESS_PRESETS = ("ui", "text", "coordinates")
DEFAULT_LOSSY_QUALITY = 85
_DPI_PER_LOGICAL_INCH = 72
# Tight enough to reject common non-Retina DPI values (e.g. 150) while still matching exact device scales (72/144/216).
_DPI_TOLERANCE = 0.05


class ImageForAgentError(ValueError):
	"""Raised when an input or output cannot satisfy the CLI contract."""


@dataclass(frozen=True)
class Crop:
	"""Describe a crop in logical image coordinates."""

	x: int
	y: int
	width: int
	height: int

	def as_dict(self) -> dict[str, int]:
		"""Return the crop as JSON-compatible fields."""
		return {
			"height": self.height,
			"width": self.width,
			"x": self.x,
			"y": self.y,
		}


def parse_crop(value: str) -> Crop:
	"""Parse ``X,Y,WIDTH,HEIGHT`` into a crop.

	@param  {str}  value
		The comma-separated crop supplied by the caller.
	@returns  {Crop}
		The validated shape values. Bounds are checked against an image later.
	"""
	parts = value.split(",")

	if len(parts) != 4:
		raise ValueError("crop must use X,Y,WIDTH,HEIGHT")

	try:
		crop = Crop(*(int(part.strip()) for part in parts))
	except ValueError as error:
		raise ValueError("crop values must be integers") from error

	_validate_crop_positive(crop)
	return crop


def detect_retina_scale(image_info: Mapping[str, Any]) -> float:
	"""Infer an integer Retina scale from Pillow DPI metadata, defaulting safely."""
	return _detect_retina_scale_with_source(image_info)[0]


def estimate_patches(width: int, height: int) -> dict[str, int]:
	"""Estimate visual patch counts using the benchmark's fixed formulas."""
	return {
		"claude_estimated_28x28_patches": math.ceil(width / 28)
		* math.ceil(height / 28),
		"openai_estimated_32x32_patches": math.ceil(width / 32)
		* math.ceil(height / 32),
	}


def calculate_result_dimensions(
	width: int,
	height: int,
	preset: str,
	retina_scale: float,
) -> tuple[int, int]:
	"""Calculate aspect-preserving dimensions without ever upscaling."""
	_validate_preset(preset)
	_validate_retina_scale(retina_scale)

	if width <= 0 or height <= 0:
		raise ImageForAgentError("source dimensions must be positive")

	if preset == "overview":
		scale_factor = 0.25
	else:
		scale_factor = min(1.0, 1.0 / retina_scale)

	result_width = max(1, min(width, round(width * scale_factor)))
	result_height = max(1, min(height, round(height * scale_factor)))
	return result_width, result_height


def process_image(
	input_path: Path,
	*,
	preset: str = "ui",
	crop: Crop | None = None,
	output_path: Path | None = None,
	retina_scale: float | None = None,
	output_format: str | None = None,
) -> dict[str, Any]:
	"""Prepare an image, write one new output file, and return its report.

	The input is fully decoded and the output is encoded in memory before the
	collision-safe output write begins. Existing files are never overwritten.

	@param  {Path}  input_path
		The source image. It is read but never modified.
	@param  {str}  preset
		One of ``overview``, ``ui``, ``text`` or ``coordinates``.
	@param  {Crop|None}  crop
		Optional logical-coordinate crop.
	@param  {Path|None}  output_path
		Destination path. A preset-specific sibling path is chosen when omitted.
	@param  {float|None}  retina_scale
		Manual source-to-logical scale override.
	@param  {str|None}  output_format
		Optional ``png``, ``jpeg`` or ``webp`` override for ``overview``.
	@returns  {dict[str, Any]}
		The stable JSON report for the written output.
	"""
	_validate_preset(preset)

	input_path = Path(input_path)
	if not input_path.is_file():
		raise ImageForAgentError(f"input image does not exist: {input_path}")

	source_image, source_info, source_bytes = _load_image(input_path)
	detected_scale, detection_source = _detect_retina_scale_with_source(source_info)
	effective_scale = detected_scale if retina_scale is None else retina_scale
	_validate_retina_scale(effective_scale)

	if retina_scale is not None:
		detection_source = "override"

	resolved_format = _resolve_format(preset, output_path, output_format)
	resolved_output_path = _resolve_output_path(
		input_path,
		output_path,
		preset,
		resolved_format,
	)
	if resolved_output_path.exists() or resolved_output_path.is_symlink():
		raise ImageForAgentError(
			f"output path already exists and will not be overwritten: {resolved_output_path}"
		)

	source_crop = _scale_crop(crop, effective_scale)
	if source_crop is not None:
		_validate_crop_bounds(source_crop, *source_image.size)
		region_width = source_crop.width
		region_height = source_crop.height
	else:
		region_width, region_height = source_image.size

	result_width, result_height = calculate_result_dimensions(
		region_width,
		region_height,
		preset,
		effective_scale,
	)

	region = source_image.crop(
		_source_box(source_crop, source_image.size)
		if source_crop is not None
		else (0, 0, source_image.width, source_image.height)
	)
	result_image = region

	try:
		if (result_width, result_height) != region.size:
			result_image = region.resize(
				(result_width, result_height),
				resample=Image.Resampling.LANCZOS,
			)

		encoded, quality = _encode_image(result_image, resolved_format)
	finally:
		if result_image is not region:
			result_image.close()
		region.close()
		source_image.close()

	warnings = _build_warnings(
		preset,
		source_crop,
		detected_scale,
		effective_scale,
		retina_scale is not None,
	)
	_write_output(resolved_output_path, encoded)

	patch_estimates = estimate_patches(result_width, result_height)
	coordinate_scale_factor = {
		"x": _round_factor(region_width / result_width),
		"y": _round_factor(region_height / result_height),
	}
	resize_scale_factor = _round_factor(result_width / region_width)

	return {
		"applied_crop": (
			{
				"requested": crop.as_dict(),
				"source_pixels": source_crop.as_dict(),
			}
			if source_crop is not None
			else None
		),
		"applied_resize": {
			"from_height": region_height,
			"from_width": region_width,
			"scale_factor": resize_scale_factor,
			"to_height": result_height,
			"to_width": result_width,
		},
		**patch_estimates,
		"coordinate_origin": (
			{"x": source_crop.x, "y": source_crop.y}
			if source_crop is not None
			else {"x": 0, "y": 0}
		),
		"coordinate_scale_factor": coordinate_scale_factor,
		"detected_retina_scale": detected_scale,
		"format": resolved_format,
		"legibility_coordinate_warning": warnings[0] if warnings else None,
		"original_encoded_bytes": len(source_bytes),
		"original_height": source_image.height,
		"original_width": source_image.width,
		"output_path": str(resolved_output_path),
		"preset": preset,
		"quality": quality,
		"result_encoded_bytes": len(encoded),
		"result_height": result_height,
		"result_width": result_width,
		"retina_scale": effective_scale,
		"retina_scale_source": detection_source,
		"warnings": warnings,
	}


def _load_image(input_path: Path) -> tuple[Image.Image, dict[str, Any], bytes]:
	"""Decode an input image before any destination path is created."""
	try:
		source_bytes = input_path.read_bytes()
		with Image.open(BytesIO(source_bytes)) as source:
			source.load()
			image_info = dict(source.info)
			image = source.copy()
	except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
		raise ImageForAgentError(
			f"input is unsupported or corrupt: {input_path}"
		) from error

	return image, image_info, source_bytes


def _detect_retina_scale_with_source(
	image_info: Mapping[str, Any],
) -> tuple[float, str]:
	"""Return a metadata scale and whether it was detected or safely assumed."""
	dpi = image_info.get("dpi")
	if not isinstance(dpi, Sequence) or isinstance(dpi, (str, bytes)):
		return 1.0, "assumed"

	try:
		dpi_values = [float(value) for value in dpi[:2]]
	except (TypeError, ValueError):
		return 1.0, "assumed"

	if len(dpi_values) != 2 or any(
		not math.isfinite(value) or value <= 0 for value in dpi_values
	):
		return 1.0, "assumed"

	ratio = sum(dpi_values) / len(dpi_values) / _DPI_PER_LOGICAL_INCH
	nearest_scale = round(ratio)
	if nearest_scale < 1 or abs(ratio - nearest_scale) > _DPI_TOLERANCE:
		return 1.0, "assumed"

	return float(nearest_scale), "metadata"


def _validate_preset(preset: str) -> None:
	"""Reject unsupported preset names with the available values."""
	if preset not in PRESETS:
		raise ImageForAgentError(
			f"unsupported preset '{preset}'; choose one of {', '.join(PRESETS)}"
		)


def _validate_retina_scale(retina_scale: float) -> None:
	"""Reject scales that cannot describe a source image's logical pixels."""
	if not math.isfinite(retina_scale) or retina_scale < 1:
		raise ImageForAgentError("retina scale must be a finite number greater than or equal to 1")


def _validate_crop_positive(crop: Crop) -> None:
	"""Ensure crop coordinates and dimensions are usable."""
	if crop.x < 0 or crop.y < 0 or crop.width <= 0 or crop.height <= 0:
		raise ValueError(
			"crop x/y must be non-negative and width/height must be positive"
		)


def _validate_crop_bounds(crop: Crop, source_width: int, source_height: int) -> None:
	"""Ensure a source-pixel crop stays inside the image."""
	_validate_crop_positive(crop)
	if crop.x + crop.width > source_width or crop.y + crop.height > source_height:
		raise ImageForAgentError("crop must stay within the source image bounds")


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


def _source_box(crop: Crop, source_size: tuple[int, int]) -> tuple[int, int, int, int]:
	"""Build Pillow's right/bottom-exclusive crop box."""
	return (crop.x, crop.y, crop.x + crop.width, crop.y + crop.height)


def _resolve_format(
	preset: str,
	output_path: Path | None,
	output_format: str | None,
) -> str:
	"""Resolve an explicit format or a recognised overview output suffix."""
	if output_format is not None:
		resolved_format = output_format.lower()
	else:
		suffix = output_path.suffix.lower() if output_path is not None else ""
		resolved_format = {
			".jpg": "jpeg",
			".jpeg": "jpeg",
			".png": "png",
			".webp": "webp",
		}.get(suffix, "png")

	if resolved_format == "jpg":
		resolved_format = "jpeg"

	if resolved_format not in {"jpeg", "png", "webp"}:
		raise ImageForAgentError(
			f"unsupported output format '{resolved_format}'; choose png, jpeg or webp"
		)

	if preset in LOSSLESS_PRESETS and resolved_format != "png":
		raise ImageForAgentError(
			f"{preset} preset always writes lossless PNG; use --preset overview for {resolved_format}"
		)

	return resolved_format


def _resolve_output_path(
	input_path: Path,
	output_path: Path | None,
	preset: str,
	output_format: str,
) -> Path:
	"""Choose a readable sibling path when the caller omits ``--output``."""
	if output_path is not None:
		return Path(output_path)

	suffix = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}[output_format]
	return input_path.with_name(f"{input_path.stem}.{preset}{suffix}")


def _encode_image(image: Image.Image, output_format: str) -> tuple[bytes, int | None]:
	"""Encode a prepared image with deterministic, preset-safe defaults."""
	buffer = BytesIO()
	format_name = output_format.upper()
	quality: int | None = None

	if output_format == "jpeg":
		if image.mode not in {"L", "RGB"}:
			image = image.convert("RGB")

		quality = DEFAULT_LOSSY_QUALITY
		image.save(
			buffer,
			format=format_name,
			optimize=True,
			quality=quality,
		)
	elif output_format == "webp":
		quality = DEFAULT_LOSSY_QUALITY
		image.save(buffer, format=format_name, quality=quality)
	else:
		image.save(buffer, format=format_name, optimize=True)

	return buffer.getvalue(), quality


def _build_warnings(
	preset: str,
	source_crop: Crop | None,
	detected_scale: float,
	effective_scale: float,
	has_override: bool,
) -> list[str]:
	"""Describe reductions or coordinate handling that need human attention."""
	warnings: list[str] = []

	if preset == "overview":
		warnings.append(
			"Overview is reduced to 25% of native dimensions; small text may be illegible."
		)

	if (
		has_override
		and preset in LOSSLESS_PRESETS
		and effective_scale > detected_scale
	):
		warnings.append(
			f"Manual retina scale {effective_scale:g} reduces the {preset} image below its "
			f"detected floor of {detected_scale:g}; inspect text and coordinates before use."
		)

	if source_crop is not None:
		warnings.append(
			"Cropped output starts at coordinate_origin; map coordinates through the reported scale."
		)

	if preset == "coordinates":
		warnings.append(
			"Map output coordinates through coordinate_origin and coordinate_scale_factor before acting on the source."
		)

	return warnings


def _write_output(output_path: Path, encoded: bytes) -> None:
	"""Write encoded bytes exclusively, removing only a failed partial write."""
	try:
		output_path.parent.mkdir(parents=True, exist_ok=True)
		with output_path.open("xb") as output_file:
			output_file.write(encoded)
	except FileExistsError as error:
		raise ImageForAgentError(
			f"output path already exists and will not be overwritten: {output_path}"
		) from error
	except OSError as error:
		if output_path.is_file():
			output_path.unlink()
		raise ImageForAgentError(f"could not write output image: {output_path}") from error


def _round_factor(value: float) -> float:
	"""Keep scale metadata precise without exposing floating-point noise."""
	return round(value, 8)
