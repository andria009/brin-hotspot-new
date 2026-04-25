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
    parse_modis_converted_csv_file,
    parse_modis_file,
    parse_modis_observed_at,
    parse_modis_records,
    scene_id_from_modis_path,
    settings_from_modis_filename,
)


def test_parse_modis_observed_at_and_satellite_from_filename():
    path = Path("tests/fixtures/aqua/a1.26115.0530.mod14.hdf")

    assert parse_modis_observed_at(path).isoformat() == "2026-04-25T05:30:00"
    assert parse_modis_observed_at("a1.26115.0530.mod14.hotspots.csv").isoformat() == (
        "2026-04-25T05:30:00"
    )
    assert scene_id_from_modis_path("a1.26115.0530.mod14.hotspots.csv") == (
        "a1.26115.0530.mod14"
    )
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


def test_find_modis_files_prefers_converted_csv(tmp_path):
    hdf = tmp_path / "a1.26115.0530.mod14.hdf"
    converted = tmp_path / "a1.26115.0530.mod14.hotspots.csv"
    other_hdf = tmp_path / "a1.26116.0530.mod14.hdf"
    for path in (hdf, converted, other_hdf):
        path.write_text("", encoding="utf-8")

    assert find_aqua_files(tmp_path) == [converted, other_hdf]


def test_parse_modis_converted_csv_file(tmp_path):
    path = tmp_path / "a1.26115.0530.mod14.hotspots.csv"
    path.write_text(
        "\n".join(
            [
                "latitude,longitude,confidence,observed_at,scene_id,source_file",
                "-2.5,120.5,10,2026-04-25T05:31:00,a1.26115.0530.mod14,raw.hdf",
                "-2.5002,120.5002,60,,,",
                "-5.8,107.0,0,,,",
            ]
        ),
        encoding="utf-8",
    )

    detections = parse_modis_converted_csv_file(path, AQUA_SETTINGS)

    assert len(detections) == 2
    assert detections[0].latitude == -2.5
    assert detections[0].longitude == 120.5
    assert detections[0].confidence == 7
    assert detections[0].observed_at == datetime(2026, 4, 25, 5, 31)
    assert detections[0].source_file == Path("raw.hdf")
    assert detections[1].confidence == 8
    assert detections[1].observed_at == datetime(2026, 4, 25, 5, 30)
    assert detections[1].source_file == path


def test_parse_modis_file_dispatches_converted_csv(tmp_path):
    path = tmp_path / "t1.26115.0530.mod14.hotspots.csv"
    path.write_text(
        "\n".join(
            [
                "latitude,longitude,confidence",
                "-2.5,120.5,90",
            ]
        ),
        encoding="utf-8",
    )

    detections = parse_modis_file(path)

    assert len(detections) == 1
    assert detections[0].satellite == "terra"
    assert detections[0].confidence == 9


def test_modis_source_item_accepts_single_file():
    path = Path("a1.26115.0530.mod14.hdf")
    source = SourceItem.single(path)

    assert source.path == path
    assert source.files == (path,)
