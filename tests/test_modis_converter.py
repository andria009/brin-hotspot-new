import importlib.util
import sys
from pathlib import Path

_CONVERTER_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "modis_converter" / "convert_modis_hdf.py"
)
_SPEC = importlib.util.spec_from_file_location("convert_modis_hdf", _CONVERTER_PATH)
assert _SPEC and _SPEC.loader
converter = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = converter
_SPEC.loader.exec_module(converter)


def test_modis_converter_derives_scene_and_observation_time():
    path = Path("aqua/2026/115/a1.26115.0530.mod14.hdf")

    assert converter.scene_id_from_path(path) == "a1.26115.0530.mod14"
    assert converter.parse_observed_at(path).isoformat() == "2026-04-25T05:30:00"


def test_modis_converter_preserves_relative_output_tree():
    input_dir = Path("/input")
    output_dir = Path("/output")
    path = input_dir / "aqua" / "2026" / "115" / "a1.26115.0530.mod14.hdf"

    assert converter.converted_output_path(path, input_dir=input_dir, output_dir=output_dir) == (
        output_dir / "aqua" / "2026" / "115" / "a1.26115.0530.mod14.hotspots.csv"
    )


def test_modis_converter_treats_zero_length_sds_as_empty():
    class FakeDataset:
        def info(self):
            return ("FP_latitude", 1, (0,), "", ())

        def __getitem__(self, item):
            raise AssertionError("empty SDS should not be read")

    assert converter.read_sds_values(FakeDataset()) == ()


def test_modis_converter_wraps_scalar_sds_value():
    class FakeDataset:
        def info(self):
            return ("FP_confidence", 1, 1, "", ())

        def __getitem__(self, item):
            return 87

    assert converter.read_sds_values(FakeDataset()) == (87,)


def test_modis_converter_can_skip_up_to_date_output(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = input_dir / "aqua" / "a1.26115.0530.mod14.hdf"
    output = output_dir / "aqua" / "a1.26115.0530.mod14.hotspots.csv"
    source.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    source.write_text("hdf", encoding="utf-8")
    output.write_text("csv", encoding="utf-8")

    result = converter.convert_file(
        source,
        input_dir=input_dir,
        output_dir=output_dir,
        skip_existing=True,
    )

    assert result.status == "skipped"
    assert result.output == output
