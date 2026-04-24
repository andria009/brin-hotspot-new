from datetime import datetime
from pathlib import Path

from brin_hotspot.domain import HotspotDetection
from brin_hotspot.ingestion.sources import SourceItem
from brin_hotspot.satellites.modis import (
    AQUA_SETTINGS,
    TERRA_SETTINGS,
    find_aqua_files,
    find_terra_files,
    normalize_modis_confidence,
    parse_modis_observed_at,
    parse_modis_records,
    settings_from_modis_filename,
)


def test_parse_modis_observed_at_and_satellite_from_filename():
    path = Path("tests/fixtures/aqua/a1.26115.0530.mod14.hdf")

    assert parse_modis_observed_at(path).isoformat() == "2026-04-25T05:30:00"
    assert settings_from_modis_filename(path) == AQUA_SETTINGS
    assert settings_from_modis_filename("t1.26115.0530.mod14.hdf") == TERRA_SETTINGS


def test_normalize_modis_confidence():
    assert normalize_modis_confidence(10) == 7
    assert normalize_modis_confidence(31) == 8
    assert normalize_modis_confidence(81) == 9


def test_parse_modis_records():
    source_file = Path("a1.26115.0530.mod14.hdf")
    detections = parse_modis_records(
        latitudes=[-2.5, -2.5002, -5.8],
        longitudes=[120.5, 120.5002, 107.0],
        confidences=[10, 60, 90],
        observed_at=datetime(2026, 4, 25, 5, 30),
        source_file=source_file,
        scene_id="a1.26115.0530.mod14",
        settings=AQUA_SETTINGS,
    )

    assert detections == [
        HotspotDetection(
            latitude=-2.5,
            longitude=120.5,
            confidence=7,
            observed_at=datetime(2026, 4, 25, 5, 30),
            satellite="aqua",
            source_file=source_file,
            scene_id="a1.26115.0530.mod14",
            source_station="Parepare",
        ),
        HotspotDetection(
            latitude=-2.5002,
            longitude=120.5002,
            confidence=8,
            observed_at=datetime(2026, 4, 25, 5, 30),
            satellite="aqua",
            source_file=source_file,
            scene_id="a1.26115.0530.mod14",
            source_station="Parepare",
        ),
        HotspotDetection(
            latitude=-5.8,
            longitude=107.0,
            confidence=9,
            observed_at=datetime(2026, 4, 25, 5, 30),
            satellite="aqua",
            source_file=source_file,
            scene_id="a1.26115.0530.mod14",
            source_station="Parepare",
        ),
    ]


def test_find_modis_files(tmp_path):
    aqua = tmp_path / "a1.26115.0530.mod14.hdf"
    terra = tmp_path / "t1.26115.0530.mod14.hdf"
    ignored = tmp_path / "a1.26115.0530.other.hdf"
    for path in (aqua, terra, ignored):
        path.write_text("", encoding="utf-8")

    assert find_aqua_files(tmp_path) == [aqua]
    assert find_terra_files(tmp_path) == [terra]


def test_modis_source_item_accepts_single_file():
    path = Path("a1.26115.0530.mod14.hdf")
    source = SourceItem.single(path)

    assert source.path == path
    assert source.files == (path,)
