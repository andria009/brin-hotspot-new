from datetime import datetime
from pathlib import Path

from brin_hotspot.satellites.snpp import find_snpp_files, parse_snpp_file

FIXTURE_DIR = Path("tests/fixtures/snpp")


def test_find_snpp_files():
    files = find_snpp_files(FIXTURE_DIR)

    assert len(files) == 1
    assert files[0].name.startswith("AFIMG_npp")


def test_parse_snpp_file():
    file_path = find_snpp_files(FIXTURE_DIR)[0]
    detections = parse_snpp_file(file_path)

    assert len(detections) == 3
    assert detections[0].latitude == -2.1
    assert detections[0].longitude == 120.1
    assert detections[0].confidence == 8
    assert detections[0].observed_at == datetime(2026, 4, 24, 5, 43, 59)
    assert detections[0].satellite == "snpp"

