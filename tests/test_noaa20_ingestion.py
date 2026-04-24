from pathlib import Path

from brin_hotspot.config import PathSettings, Settings
from brin_hotspot.ingestion.noaa20 import ingest_noaa20
from brin_hotspot.satellites.noaa20 import find_noaa20_files, parse_noaa20_file

FIXTURE_DIR = Path("tests/fixtures/noaa20")


def test_parse_noaa20_file():
    file_path = find_noaa20_files(FIXTURE_DIR)[0]
    detections = parse_noaa20_file(file_path)

    assert len(detections) == 3
    assert detections[0].satellite == "noaa20"
    assert detections[0].confidence == 8


def test_ingest_noaa20_writes_outputs(tmp_path):
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summary = ingest_noaa20(settings, input_dir=FIXTURE_DIR)

    assert summary.satellite == "noaa20"
    assert summary.parsed_count == 3
    assert summary.cluster_count == 2
    assert len(summary.output_files) == 2
    for output_file in summary.output_files:
        assert output_file.exists()


def test_ingest_noaa20_can_persist_via_repository(tmp_path, monkeypatch):
    calls = {}

    class FakeRepository:
        def __init__(self, database):
            calls["database"] = database

        def source_file_completed(self, satellite, path):
            return False

        def persist_ingestion(self, **kwargs):
            calls["persist_kwargs"] = kwargs
            return 2, 3

        def mark_run_failed(self, run_id, satellite, message):
            calls["failure"] = (run_id, satellite, message)

    monkeypatch.setattr("brin_hotspot.ingestion.hotspot.HotspotRepository", FakeRepository)
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summary = ingest_noaa20(settings, input_dir=FIXTURE_DIR, persist=True)

    assert summary.persisted_cluster_count == 2
    assert summary.persisted_pixel_count == 3
    assert "failure" not in calls
    assert calls["persist_kwargs"]["satellite"] == "noaa20"
