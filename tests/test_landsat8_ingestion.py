from pathlib import Path

from brin_hotspot.config import PathSettings, Settings
from brin_hotspot.ingestion.landsat8 import ingest_landsat8
from brin_hotspot.satellites.landsat8 import (
    find_landsat8_sources,
    parse_landsat8_firepixels_file,
)

FIXTURE_DIR = Path("tests/fixtures/landsat8")


def test_parse_landsat8_firepixels_file():
    file_path = sorted(FIXTURE_DIR.glob("*firepixels.txt"))[0]
    detections = parse_landsat8_firepixels_file(file_path)

    assert len(detections) == 2
    assert detections[0].satellite == "landsat8"
    assert detections[0].confidence == 9
    assert detections[0].observed_at.isoformat() == "2026-04-24T00:39:08"


def test_find_landsat8_sources_groups_by_date_and_path():
    sources = find_landsat8_sources(FIXTURE_DIR)

    assert len(sources) == 1
    assert sources[0].path == Path("landsat8/20260424_099")
    assert len(sources[0].files) == 2


def test_ingest_landsat8_writes_outputs(tmp_path):
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summary = ingest_landsat8(settings, input_dir=FIXTURE_DIR)

    assert summary.satellite == "landsat8"
    assert summary.parsed_count == 3
    assert summary.cluster_count == 2
    assert len(summary.output_files) == 2
    for output_file in summary.output_files:
        assert output_file.exists()


def test_ingest_landsat8_can_persist_via_repository(tmp_path, monkeypatch):
    calls = {}

    class FakeRepository:
        def __init__(self, database):
            calls["database"] = database

        def source_file_completed(self, satellite, path):
            calls.setdefault("source_file_checks", []).append((satellite, path))
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

    summary = ingest_landsat8(settings, input_dir=FIXTURE_DIR, persist=True)

    assert summary.persisted_cluster_count == 2
    assert summary.persisted_pixel_count == 3
    assert "failure" not in calls
    assert calls["persist_kwargs"]["satellite"] == "landsat8"
    assert len(calls["persist_kwargs"]["source_files"]) == 2
