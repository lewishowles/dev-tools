"""Focused tests for the public Pillow image preparation contract."""

from pathlib import Path
import json

from PIL import Image
import pytest

from image_for_agent.processor import (
	Crop,
	ImageForAgentError,
	calculate_result_dimensions,
	detect_retina_scale,
	estimate_patches,
	parse_crop,
	process_image,
)
from image_for_agent.public_cli import main


FIXTURE_DIRECTORY = Path(__file__).parents[1] / "benchmark" / "fixtures"


def _write_image(
	path: Path,
	*,
	size: tuple[int, int] = (800, 600),
	dpi: tuple[int, int] | None = None,
) -> None:
	"""Create a deterministic real Pillow image fixture."""
	image = Image.new("RGB", size, (240, 240, 240))
	image.save(path, dpi=dpi) if dpi is not None else image.save(path)


def test_presets_use_their_approved_scale_floor(tmp_path: Path) -> None:
	source = tmp_path / "source.png"
	_write_image(source)

	expected_dimensions = {
		"overview": (200, 150),
		"ui": (800, 600),
		"text": (800, 600),
		"coordinates": (800, 600),
	}

	for preset, expected in expected_dimensions.items():
		report = process_image(
			source,
			preset=preset,
			output_path=tmp_path / f"{preset}.png",
		)

		assert (report["result_width"], report["result_height"]) == expected


def test_retina_metadata_is_detected_and_missing_metadata_defaults_to_one() -> None:
	assert detect_retina_scale({"dpi": (144, 144)}) == 2.0
	assert detect_retina_scale({}) == 1.0
	assert detect_retina_scale({"dpi": (150, 150)}) == 1.0


def test_retina_metadata_scales_ui_without_assuming_missing_metadata(tmp_path: Path) -> None:
	retina_source = tmp_path / "retina.png"
	plain_source = tmp_path / "plain.png"
	_write_image(retina_source, size=(800, 600), dpi=(144, 144))
	_write_image(plain_source, size=(800, 600))

	retina_report = process_image(
		retina_source,
		output_path=tmp_path / "retina-output.png",
	)
	plain_report = process_image(
		plain_source,
		output_path=tmp_path / "plain-output.png",
	)

	assert retina_report["detected_retina_scale"] == 2.0
	assert retina_report["retina_scale_source"] == "metadata"
	assert (retina_report["result_width"], retina_report["result_height"]) == (400, 300)
	assert plain_report["detected_retina_scale"] == 1.0
	assert plain_report["retina_scale_source"] == "assumed"
	assert (plain_report["result_width"], plain_report["result_height"]) == (800, 600)


def test_retina_crop_mapping_reports_source_pixels_and_coordinate_scale(
	tmp_path: Path,
) -> None:
	source = tmp_path / "source.png"
	_write_image(source, size=(800, 600))

	report = process_image(
		source,
		preset="coordinates",
		crop=Crop(x=20, y=10, width=200, height=100),
		retina_scale=2,
		output_path=tmp_path / "coordinates.png",
	)

	assert report["applied_crop"] == {
		"requested": {"height": 100, "width": 200, "x": 20, "y": 10},
		"source_pixels": {"height": 200, "width": 400, "x": 40, "y": 20},
	}
	assert report["coordinate_origin"] == {"x": 40, "y": 20}
	assert report["coordinate_scale_factor"] == {"x": 2.0, "y": 2.0}
	assert (report["result_width"], report["result_height"]) == (200, 100)


def test_fixture_crop_maps_the_central_panel_border(
	tmp_path: Path,
) -> None:
	report = process_image(
		FIXTURE_DIRECTORY / "synthetic-ui.png",
		preset="coordinates",
		crop=Crop(x=352, y=102, width=320, height=300),
		retina_scale=2,
		output_path=tmp_path / "coordinates.png",
	)

	assert report["applied_crop"] == {
		"requested": {"height": 300, "width": 320, "x": 352, "y": 102},
		"source_pixels": {"height": 600, "width": 640, "x": 704, "y": 204},
	}

	with Image.open(tmp_path / "coordinates.png") as image:
		rgb_image = image.convert("RGB")

		assert rgb_image.size == (320, 300)
		assert rgb_image.getpixel((0, 0)) == (90, 220, 150)
		assert rgb_image.getpixel((50, 50)) == (48, 68, 88)


def test_fixture_text_edges_survive_the_text_preset(
	tmp_path: Path,
) -> None:
	output_path = tmp_path / "text.png"
	process_image(
		FIXTURE_DIRECTORY / "dev-tool-panel.png",
		preset="text",
		retina_scale=4,
		output_path=output_path,
	)

	with Image.open(output_path) as image:
		rgb_image = image.convert("RGB")
		# The fixture's "Orbit card" heading is at this region after the 4x reduction.
		bright_pixels = [
			(x, y)
			for y in range(140, 160)
			for x in range(265, 325)
			if min(rgb_image.getpixel((x, y))) >= 200
		]

	assert len(bright_pixels) >= 50
	assert max(x for x, _ in bright_pixels) - min(x for x, _ in bright_pixels) >= 40
	assert max(y for _, y in bright_pixels) - min(y for _, y in bright_pixels) >= 5


def test_patch_estimates_match_the_benchmark_formulas() -> None:
	assert estimate_patches(512, 384) == {
		"claude_estimated_28x28_patches": 19 * 14,
		"openai_estimated_32x32_patches": 16 * 12,
	}


def test_crop_parser_and_bounds_validation_are_explicit(tmp_path: Path) -> None:
	assert parse_crop("10,20,300,200") == Crop(x=10, y=20, width=300, height=200)
	with pytest.raises(ValueError, match="X,Y,WIDTH,HEIGHT"):
		parse_crop("10,20,300")

	source = tmp_path / "source.png"
	_write_image(source, size=(100, 100))

	with pytest.raises(ImageForAgentError, match="within the source image bounds"):
		process_image(
			source,
			crop=Crop(x=80, y=0, width=30, height=20),
			output_path=tmp_path / "invalid-crop.png",
		)


def test_json_report_has_a_stable_shape_and_exact_coordinate_mapping(tmp_path: Path) -> None:
	source = tmp_path / "source.png"
	_write_image(source, size=(400, 200))

	report = process_image(
		source,
		preset="coordinates",
		crop=Crop(x=20, y=10, width=200, height=100),
		retina_scale=1,
		output_path=tmp_path / "coordinates.png",
	)

	expected_keys = {
		"applied_crop",
		"applied_resize",
		"claude_estimated_28x28_patches",
		"coordinate_origin",
		"coordinate_scale_factor",
		"detected_retina_scale",
		"format",
		"legibility_coordinate_warning",
		"openai_estimated_32x32_patches",
		"original_encoded_bytes",
		"original_height",
		"original_width",
		"output_path",
		"preset",
		"quality",
		"result_encoded_bytes",
		"result_height",
		"result_width",
		"retina_scale",
		"retina_scale_source",
		"warnings",
	}

	assert set(report) == expected_keys
	assert report["coordinate_scale_factor"] == {"x": 1.0, "y": 1.0}
	assert report["coordinate_origin"] == {"x": 20, "y": 10}
	assert json.loads(json.dumps(report, sort_keys=True)) == report


def test_corrupt_input_fails_before_creating_output(tmp_path: Path) -> None:
	input_path = tmp_path / "corrupt.png"
	output_path = tmp_path / "output.png"
	input_path.write_bytes(b"not an image")

	with pytest.raises(ImageForAgentError, match="unsupported or corrupt"):
		process_image(input_path, output_path=output_path)

	assert not output_path.exists()


def test_existing_output_is_refused_without_changing_it(tmp_path: Path) -> None:
	source = tmp_path / "source.png"
	output_path = tmp_path / "output.png"
	_write_image(source)
	output_path.write_bytes(b"keep this")

	with pytest.raises(ImageForAgentError, match="already exists"):
		process_image(source, output_path=output_path)

	assert output_path.read_bytes() == b"keep this"


def test_presets_never_upscale_small_images() -> None:
	assert calculate_result_dimensions(2, 2, "overview", 1) == (1, 1)
	assert calculate_result_dimensions(2, 2, "ui", 1) == (2, 2)


def test_explicit_extra_retina_reduction_warns_for_text_safe_presets(
	tmp_path: Path,
) -> None:
	source = tmp_path / "source.png"
	_write_image(source)

	report = process_image(
		source,
		preset="text",
		retina_scale=4,
		output_path=tmp_path / "text.png",
	)

	assert (report["result_width"], report["result_height"]) == (200, 150)
	assert any("below its detected floor" in warning for warning in report["warnings"])


def test_public_cli_defaults_to_ui_and_emits_json(
	tmp_path: Path,
	capsys: pytest.CaptureFixture[str],
) -> None:
	source = tmp_path / "source.png"
	output = tmp_path / "prepared.png"
	_write_image(source)

	exit_code = main([str(source), "--output", str(output), "--json"])
	payload = json.loads(capsys.readouterr().out)

	assert exit_code == 0
	assert payload["preset"] == "ui"
	assert payload["output_path"] == str(output)
	assert output.exists()


@pytest.mark.parametrize("preset", ("ui", "text", "coordinates"))
def test_lossless_presets_reject_non_png_format(
	preset: str,
	tmp_path: Path,
	capsys: pytest.CaptureFixture[str],
) -> None:
	source = tmp_path / "source.png"
	output = tmp_path / f"{preset}.jpg"
	_write_image(source)

	exit_code = main(
		[
			str(source),
			"--preset",
			preset,
			"--output",
			str(output),
			"--format",
			"jpeg",
		]
	)
	captured = capsys.readouterr()

	assert exit_code == 2
	assert f"{preset} preset always writes lossless PNG" in captured.err
	assert not output.exists()
