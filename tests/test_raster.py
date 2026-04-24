from pathlib import Path

from brin_hotspot.raster import (
    find_raster_files,
    gdal2tiles_command,
    parse_raster_filename,
    tile_output_dir,
)


def test_parse_viirs_raster_filename():
    metadata = parse_raster_filename(Path("SNPP_20260424_054359_FI.tif"))

    assert metadata.satellite == "snpp"
    assert metadata.observed_at.isoformat() == "2026-04-24T05:43:59"
    assert metadata.infox == "SNPP_20260424054359"
    assert metadata.raster_type == "FI"


def test_parse_landsat8_raster_filename():
    metadata = parse_raster_filename(Path("L8_099064_20260424_003908_FI.tif"))

    assert metadata.satellite == "landsat8"
    assert metadata.observed_at.isoformat() == "2026-04-24T00:39:08"
    assert metadata.infox == "L8_099064"


def test_find_raster_files(tmp_path):
    keep = tmp_path / "SNPP_20260424_054359_FI.tif"
    nested = tmp_path / "nested"
    nested.mkdir()
    keep_nested = nested / "NOAA20_20260424_040125_FI.tif"
    ignored = tmp_path / "SNPP_20260424_054359_TC.tif"
    for path in (keep, keep_nested, ignored):
        path.write_text("", encoding="utf-8")

    assert find_raster_files(tmp_path) == [keep, keep_nested]


def test_tile_output_dir():
    metadata = parse_raster_filename(Path("NOAA20_20260424_040125_FI.tif"))

    assert tile_output_dir(Path("tiles"), metadata) == Path(
        "tiles/noaa20/2026/04/24/040125/FI"
    )


def test_gdal2tiles_command():
    assert gdal2tiles_command(
        Path("input.tif"),
        Path("tiles"),
        zoom="5-8",
        processes=2,
    ) == [
        "gdal2tiles.py",
        "--xyz",
        "--resume",
        "--webviewer=none",
        "--processes",
        "2",
        "-z",
        "5-8",
        "input.tif",
        "tiles",
    ]
