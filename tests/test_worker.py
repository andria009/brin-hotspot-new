from pathlib import Path

import pytest

from brin_hotspot.config import PathSettings, Settings
from brin_hotspot.domain import IngestionSummary
from brin_hotspot.worker import run_ingestion_cycle, run_worker_loop


def test_run_ingestion_cycle_dispatches_selected_satellites(tmp_path, monkeypatch):
    calls = []

    def fake_ingest(settings, input_dir, *, persist=False, enrich=False):
        calls.append((settings, input_dir, persist, enrich))
        return IngestionSummary(satellite=input_dir.name, parsed_count=1)

    monkeypatch.setattr("brin_hotspot.worker._ingest_function", lambda satellite: fake_ingest)
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summaries = run_ingestion_cycle(
        settings,
        satellites=("snpp", "landsat8"),
        persist=True,
        enrich=True,
    )

    assert [summary.satellite for summary in summaries] == ["snpp", "landsat8"]
    assert calls == [
        (settings, Path(tmp_path / "input/snpp"), True, True),
        (settings, Path(tmp_path / "input/landsat8"), True, True),
    ]


def test_run_worker_loop_repeats_cycles_without_sleep_for_single_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "brin_hotspot.worker.run_ingestion_cycle",
        lambda *args, **kwargs: (IngestionSummary(satellite="snpp"),),
    )
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    summary = run_worker_loop(
        settings,
        satellites=("snpp",),
        persist=False,
        enrich=False,
        interval_seconds=1,
        max_cycles=1,
    )

    assert summary.cycle_count == 1
    assert len(summary.ingestion_summaries) == 1


def test_run_ingestion_cycle_rejects_unknown_satellite(tmp_path):
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    with pytest.raises(ValueError, match="Unsupported satellite"):
        run_ingestion_cycle(settings, satellites=("unknown",))
