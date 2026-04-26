from pathlib import Path

from brin_hotspot.config import PathSettings, Settings
from brin_hotspot.domain import AdminLocation
from brin_hotspot.ingestion.snpp import ingest_snpp


def test_ingest_snpp_writes_cluster_and_pixel_csv(tmp_path):
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summary = ingest_snpp(settings, input_dir=Path("tests/fixtures/snpp"))

    assert summary.satellite == "snpp"
    assert summary.parsed_count == 3
    assert summary.cluster_count == 2
    assert len(summary.output_files) == 2
    for output_file in summary.output_files:
        assert output_file.exists()

    cluster_csv = summary.output_files[0].read_text(encoding="utf-8")
    pixel_csv = summary.output_files[1].read_text(encoding="utf-8")
    assert "cluster" in cluster_csv
    assert "pixel" in pixel_csv


def test_ingest_snpp_can_persist_via_repository(tmp_path, monkeypatch):
    calls = {}

    class FakeRepository:
        def __init__(self, database):
            calls["database"] = database

        def source_file_completed(self, satellite, path):
            calls.setdefault("source_file_checks", []).append((satellite, path))
            return False

        def reset_running_source_files(self, *, satellite, message):
            calls["reset_running"] = (satellite, message)
            return 0

        def start_run(self, run_id, satellite, source_path=None):
            calls["start_run"] = (run_id, satellite, source_path)

        def finish_run(self, run_id, status, message=None):
            calls["finish_run"] = (run_id, status, message)

        def mark_source_file_running(self, satellite, path):
            calls.setdefault("running_sources", []).append((satellite, path))

        def mark_source_file_failed(self, satellite, path, message):
            calls.setdefault("failed_sources", []).append((satellite, path, message))

        def persist_ingestion(self, **kwargs):
            calls.setdefault("persist_calls", []).append(kwargs)
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

    summary = ingest_snpp(settings, input_dir=Path("tests/fixtures/snpp"), persist=True)

    assert summary.persisted_cluster_count == 2
    assert summary.persisted_pixel_count == 3
    assert "failure" not in calls
    assert calls["persist_calls"][0]["satellite"] == "snpp"
    assert len(calls["persist_calls"][0]["clusters"]) == 2
    assert len(calls["running_sources"]) == 1


def test_ingest_snpp_can_enrich_before_persisting(tmp_path, monkeypatch):
    calls = {}

    class FakeGeoRepository:
        def __init__(self, database):
            calls["geo_database"] = database

        def enrich_detection(self, detection, *, duplicate_buffer_degrees):
            calls.setdefault("duplicate_buffers", []).append(duplicate_buffer_degrees)
            if detection.confidence == 7:
                return None
            return detection.with_location(
                AdminLocation(
                    kecamatan="Example Kecamatan",
                    kabupaten="Example Kabupaten",
                    provinsi="Example Province",
                )
            )

    class FakeRepository:
        def __init__(self, database):
            calls["hotspot_database"] = database

        def source_file_completed(self, satellite, path):
            return False

        def reset_running_source_files(self, *, satellite, message):
            calls["reset_running"] = (satellite, message)
            return 0

        def start_run(self, run_id, satellite, source_path=None):
            calls["start_run"] = (run_id, satellite, source_path)

        def finish_run(self, run_id, status, message=None):
            calls["finish_run"] = (run_id, status, message)

        def mark_source_file_running(self, satellite, path):
            calls.setdefault("running_sources", []).append((satellite, path))

        def mark_source_file_failed(self, satellite, path, message):
            calls.setdefault("failed_sources", []).append((satellite, path, message))

        def persist_ingestion(self, **kwargs):
            calls["persist_kwargs"] = kwargs
            pixel_count = sum(len(cluster.detections) for cluster in kwargs["clusters"])
            return len(kwargs["clusters"]), pixel_count

        def mark_run_failed(self, run_id, satellite, message):
            calls["failure"] = (run_id, satellite, message)

    monkeypatch.setattr("brin_hotspot.ingestion.hotspot.GeoRepository", FakeGeoRepository)
    monkeypatch.setattr("brin_hotspot.ingestion.hotspot.HotspotRepository", FakeRepository)
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summary = ingest_snpp(
        settings,
        input_dir=Path("tests/fixtures/snpp"),
        persist=True,
        enrich=True,
    )

    assert summary.parsed_count == 3
    assert summary.enriched_count == 2
    assert summary.filtered_count == 1
    assert summary.cluster_count == 1
    assert summary.persisted_cluster_count == 1
    assert summary.persisted_pixel_count == 2
    assert calls["duplicate_buffers"] == [0.00027027027, 0.00027027027, 0.00027027027]
    persisted_cluster = calls["persist_kwargs"]["clusters"][0]
    assert persisted_cluster.detections[0].location is not None


def test_ingest_snpp_completes_source_when_enrichment_filters_all(tmp_path, monkeypatch):
    calls = {}

    class FakeGeoRepository:
        def __init__(self, database):
            pass

        def enrich_detection(self, detection, *, duplicate_buffer_degrees):
            return None

    class FakeRepository:
        def __init__(self, database):
            pass

        def source_file_completed(self, satellite, path):
            return False

        def reset_running_source_files(self, *, satellite, message):
            return 0

        def start_run(self, run_id, satellite, source_path=None):
            pass

        def finish_run(self, run_id, status, message=None):
            calls["finish_run"] = (run_id, status, message)

        def mark_source_file_running(self, satellite, path):
            calls.setdefault("running_sources", []).append(path)

        def mark_source_file_failed(self, satellite, path, message):
            calls.setdefault("failed_sources", []).append((path, message))

        def persist_ingestion(self, **kwargs):
            calls["persist_kwargs"] = kwargs
            return 0, 0

    monkeypatch.setattr("brin_hotspot.ingestion.hotspot.GeoRepository", FakeGeoRepository)
    monkeypatch.setattr("brin_hotspot.ingestion.hotspot.HotspotRepository", FakeRepository)
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summary = ingest_snpp(
        settings,
        input_dir=Path("tests/fixtures/snpp"),
        persist=True,
        enrich=True,
    )

    assert summary.parsed_count == 3
    assert summary.filtered_count == 3
    assert summary.cluster_count == 0
    assert summary.persisted_cluster_count == 0
    assert summary.persisted_pixel_count == 0
    assert calls["persist_kwargs"]["clusters"] == []
    assert len(calls["persist_kwargs"]["source_metadata"]) == 1
    assert "failed_sources" not in calls


def test_ingest_snpp_skips_completed_source_files(tmp_path, monkeypatch):
    class FakeRepository:
        def __init__(self, database):
            pass

        def reset_running_source_files(self, *, satellite, message):
            return 0

        def start_run(self, run_id, satellite, source_path=None):
            pass

        def finish_run(self, run_id, status, message=None):
            pass

        def source_file_completed(self, satellite, path):
            return True

        def mark_source_file_running(self, satellite, path):
            raise AssertionError("completed source files should not be marked running")

        def mark_source_file_failed(self, satellite, path, message):
            raise AssertionError("skip should not be treated as failure")

        def persist_ingestion(self, **kwargs):
            raise AssertionError("completed source files should not be persisted")

        def mark_run_failed(self, run_id, satellite, message):
            raise AssertionError("skip should not be treated as failure")

    monkeypatch.setattr("brin_hotspot.ingestion.hotspot.HotspotRepository", FakeRepository)
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summary = ingest_snpp(settings, input_dir=Path("tests/fixtures/snpp"), persist=True)

    assert summary.parsed_count == 0
    assert summary.cluster_count == 0
    assert len(summary.skipped_files) == 1


def test_ingest_snpp_persists_each_source_file_independently(tmp_path, monkeypatch):
    fixture_file = next(Path("tests/fixtures/snpp").rglob("AFIMG_npp*.txt"))
    input_dir = tmp_path / "input"
    first = input_dir / "2026" / "04" / "24" / "054359000" / fixture_file.name
    second = input_dir / "2026" / "04" / "24" / "064359000" / fixture_file.name.replace(
        "t0543590",
        "t0643590",
    )
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text(fixture_file.read_text(encoding="utf-8"), encoding="utf-8")
    second.write_text(fixture_file.read_text(encoding="utf-8"), encoding="utf-8")
    calls = {}

    class FakeRepository:
        def __init__(self, database):
            pass

        def source_file_completed(self, satellite, path):
            return False

        def reset_running_source_files(self, *, satellite, message):
            calls["reset_running"] = (satellite, message)
            return 0

        def start_run(self, run_id, satellite, source_path=None):
            calls["start_run"] = (run_id, satellite, source_path)

        def finish_run(self, run_id, status, message=None):
            calls["finish_run"] = (run_id, status, message)

        def mark_source_file_running(self, satellite, path):
            calls.setdefault("running_sources", []).append(path)

        def mark_source_file_failed(self, satellite, path, message):
            calls.setdefault("failed_sources", []).append((path, message))

        def persist_ingestion(self, **kwargs):
            calls.setdefault("persist_calls", []).append(kwargs)
            pixel_count = sum(len(cluster.detections) for cluster in kwargs["clusters"])
            return len(kwargs["clusters"]), pixel_count

        def mark_run_failed(self, run_id, satellite, message):
            calls["failure"] = (run_id, satellite, message)

    monkeypatch.setattr("brin_hotspot.ingestion.hotspot.HotspotRepository", FakeRepository)
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "unused",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summary = ingest_snpp(settings, input_dir=input_dir, persist=True)

    assert summary.parsed_count == 6
    assert len(calls["running_sources"]) == 2
    assert len(calls["persist_calls"]) == 2
    assert all(len(call["source_files"]) == 1 for call in calls["persist_calls"])
    assert "failure" not in calls
