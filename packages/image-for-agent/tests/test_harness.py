"""Focused tests for the offline image variant benchmark contract."""

from copy import deepcopy
from pathlib import Path

import pytest

from image_for_agent.cli import main
from image_for_agent.harness import (
	Crop,
	HarnessError,
	VariantSpec,
	_validate_manifest,
	estimate_patches,
	load_manifest,
	plan_variant,
	run_benchmark,
)


def test_estimate_patches_uses_fixed_vendor_estimates() -> None:
	assert estimate_patches(512, 384) == {
		"claude_estimated_28x28_patches": 19 * 14,
		"openai_estimated_32x32_patches": 16 * 12,
	}


def test_long_edge_target_preserves_aspect_ratio_without_upscaling() -> None:
	spec = VariantSpec(
		name="512-long-edge",
		target={"kind": "long_edge", "value": 512},
		output_format="png",
		quality=None,
		crop=None,
		pair_with=None,
	)

	plan = plan_variant(spec, 2048, 1536)

	assert plan.should_render is True
	assert (plan.result_width, plan.result_height) == (512, 384)


def test_target_larger_than_source_is_skipped() -> None:
	spec = VariantSpec(
		name="1080p",
		target={"kind": "bounding_box", "max_width": 1920, "max_height": 1080},
		output_format="png",
		quality=None,
		crop=None,
		pair_with=None,
	)

	plan = plan_variant(spec, 1280, 720)

	assert plan.should_render is False
	assert plan.reason == "target is not smaller than the source region"
	assert (plan.result_width, plan.result_height) == (1280, 720)


def test_crop_can_render_without_resizing_and_keeps_source_origin() -> None:
	spec = VariantSpec(
		name="text-crop-native",
		target={"kind": "long_edge", "value": 1024},
		output_format="png",
		quality=None,
		crop=Crop(x=256, y=192, width=1024, height=768),
		pair_with="1024-long-edge",
	)

	plan = plan_variant(spec, 2048, 1536)

	assert plan.should_render is True
	assert (plan.region_width, plan.region_height) == (1024, 768)
	assert (plan.result_width, plan.result_height) == (1024, 768)


def test_invalid_crop_is_rejected() -> None:
	spec = VariantSpec(
		name="outside",
		target={"kind": "long_edge", "value": 512},
		output_format="png",
		quality=None,
		crop=Crop(x=1800, y=0, width=512, height=384),
		pair_with=None,
	)

	with pytest.raises(HarnessError, match="within the source image"):
		plan_variant(spec, 2048, 1536)


def test_crop_and_resize_compose_in_source_pixel_space(tmp_path: Path) -> None:
	package_root = Path(__file__).parents[1]
	manifest = load_manifest(package_root / "benchmark/manifest.json")

	result = run_benchmark(
		package_root / "benchmark/fixtures/synthetic-ui.png",
		manifest,
		tmp_path,
	)

	text_crop = next(
		variant
		for variant in result["variants"]
		if variant["named_variant"] == "text-crop-512"
	)

	assert (text_crop["result_width"], text_crop["result_height"]) == (512, 384)
	assert text_crop["coordinate_origin"] == {"x": 256, "y": 192}


def test_retina_target_uses_source_scale(tmp_path: Path) -> None:
	package_root = Path(__file__).parents[1]
	manifest = load_manifest(package_root / "benchmark/manifest.json")
	manifest = deepcopy(manifest)
	manifest["source"]["retina_scale"] = 4
	manifest["variants"] = [manifest["variants"][0]]
	manifest["variants"][0]["crop"] = {
		"x": 512,
		"y": 384,
		"width": 512,
		"height": 384,
	}

	with pytest.raises(HarnessError, match="within the source image"):
		run_benchmark(
			package_root / "benchmark/fixtures/synthetic-ui.png",
			manifest,
			tmp_path / "out-of-bounds",
		)

	manifest["variants"][0]["crop"] = {
		"x": 0,
		"y": 0,
		"width": 512,
		"height": 384,
	}
	result = run_benchmark(
		package_root / "benchmark/fixtures/synthetic-ui.png",
		manifest,
		tmp_path / "in-bounds",
	)

	assert (
		result["variants"][0]["result_width"],
		result["variants"][0]["result_height"],
	) == (
		512,
		384,
	)
	assert result["variants"][0]["result_encoded_bytes"] > 3000


def test_manifest_rejects_missing_required_field() -> None:
	package_root = Path(__file__).parents[1]
	manifest = deepcopy(load_manifest(package_root / "benchmark/manifest.json"))
	manifest.pop("schema_version")

	with pytest.raises(HarnessError, match="missing 'schema_version'"):
		_validate_manifest(manifest, package_root / "benchmark/manifest.json")


def test_manifest_rejects_empty_questions() -> None:
	package_root = Path(__file__).parents[1]
	manifest = deepcopy(load_manifest(package_root / "benchmark/manifest.json"))
	manifest["questions"] = []

	with pytest.raises(HarnessError, match="at least one question"):
		_validate_manifest(manifest, package_root / "benchmark/manifest.json")


def test_manifest_rejects_unknown_question_task_class() -> None:
	package_root = Path(__file__).parents[1]
	manifest = deepcopy(load_manifest(package_root / "benchmark/manifest.json"))
	manifest["questions"][0]["task_class"] = "unknown"

	with pytest.raises(HarnessError, match="unknown task class"):
		_validate_manifest(manifest, package_root / "benchmark/manifest.json")


def test_manifest_rejects_invalid_variant_name() -> None:
	package_root = Path(__file__).parents[1]
	manifest = deepcopy(load_manifest(package_root / "benchmark/manifest.json"))
	manifest["variants"][0]["name"] = "not valid"

	with pytest.raises(HarnessError, match="variant names"):
		_validate_manifest(manifest, package_root / "benchmark/manifest.json")


def test_manifest_rejects_unsupported_target_kind() -> None:
	package_root = Path(__file__).parents[1]
	manifest = deepcopy(load_manifest(package_root / "benchmark/manifest.json"))
	manifest["variants"][0]["target"] = {"kind": "unknown"}

	with pytest.raises(HarnessError, match="unsupported target"):
		_validate_manifest(manifest, package_root / "benchmark/manifest.json")


def test_manifest_rejects_non_positive_crop() -> None:
	package_root = Path(__file__).parents[1]
	manifest = deepcopy(load_manifest(package_root / "benchmark/manifest.json"))
	manifest["variants"][-1]["crop"]["width"] = 0

	with pytest.raises(HarnessError, match="width/height must be positive"):
		_validate_manifest(manifest, package_root / "benchmark/manifest.json")


def test_cli_reports_input_errors(
	tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
	package_root = Path(__file__).parents[1]

	exit_code = main(
		[
			str(tmp_path / "missing.png"),
			"--manifest",
			str(package_root / "benchmark/manifest.json"),
			"--output-dir",
			str(tmp_path / "output"),
		]
	)

	captured = capsys.readouterr()

	assert exit_code == 2
	assert "input image does not exist" in captured.err
