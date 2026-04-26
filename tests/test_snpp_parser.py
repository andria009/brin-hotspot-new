from datetime import datetime
from pathlib import Path

from brin_hotspot.satellites.snpp import (
    find_snpp_files,
    parse_observed_at_from_path,
    parse_snpp_file,
)

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


def test_parse_observed_at_from_viirs_filename():
    path = (
        "/app/data/input/snpp/2025/snpp_20250101_0407/FIRE/"
        "AFIMG_npp_d20250101_t0407536_e0409177_b68295_c20250101065242479108_cspp_dev.txt"
    )

    assert parse_observed_at_from_path(path) == datetime(2025, 1, 1, 4, 7, 53, 600000)


def test_parse_observed_at_from_viirs_filename_with_six_fraction_digits():
    path = "AFIMG_j01_d20250718_t041802789_e0429258_b39708.txt"

    assert parse_observed_at_from_path(path) == datetime(2025, 7, 18, 4, 18, 2, 789000)
