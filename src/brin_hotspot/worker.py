from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from brin_hotspot.config import Settings
from brin_hotspot.domain import IngestionSummary

logger = logging.getLogger(__name__)

IngestFunction = Callable[[Settings, Path | None], IngestionSummary]


@dataclass(frozen=True)
class WorkerRunSummary:
    cycle_count: int
    ingestion_summaries: tuple[IngestionSummary, ...]


def run_ingestion_cycle(
    settings: Settings,
    *,
    satellites: tuple[str, ...] = ("snpp", "noaa20", "aqua", "terra", "landsat8"),
    input_dirs: Mapping[str, Path] | None = None,
    persist: bool = False,
    enrich: bool = False,
    continue_on_error: bool = False,
) -> tuple[IngestionSummary, ...]:
    """Run one polling cycle across the selected satellite feeds."""

    summaries: list[IngestionSummary] = []
    for satellite in satellites:
        ingest = _ingest_function(satellite)
        # Input overrides let production use converted MODIS CSV directories
        # while keeping the default satellite subdirectory convention.
        input_dir = (input_dirs or {}).get(satellite, settings.paths.input_dir / satellite)
        logger.info(
            "worker_satellite_started",
            extra={
                "satellite": satellite,
                "input_dir": str(input_dir),
                "persist": persist,
                "enrich": enrich,
            },
        )
        try:
            summary = ingest(settings, input_dir, persist=persist, enrich=enrich)
        except Exception:
            logger.exception(
                "worker_satellite_failed",
                extra={"satellite": satellite, "input_dir": str(input_dir)},
            )
            if continue_on_error:
                continue
            raise
        summaries.append(summary)
        logger.info(
            "worker_satellite_completed",
            extra={
                "satellite": satellite,
                "run_id": str(summary.run_id),
                "parsed_count": summary.parsed_count,
                "cluster_count": summary.cluster_count,
                "persisted_cluster_count": summary.persisted_cluster_count,
            },
        )
    return tuple(summaries)


def run_worker_loop(
    settings: Settings,
    *,
    satellites: tuple[str, ...],
    input_dirs: Mapping[str, Path] | None = None,
    persist: bool,
    enrich: bool,
    interval_seconds: int,
    max_cycles: int | None,
    continue_on_error: bool = True,
) -> WorkerRunSummary:
    """Run ingestion cycles until max_cycles is reached or the process stops."""

    summaries: list[IngestionSummary] = []
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        cycle += 1
        logger.info(
            "worker_cycle_started",
            extra={"cycle": cycle, "max_cycles": max_cycles},
        )
        try:
            summaries.extend(
                run_ingestion_cycle(
                    settings,
                    satellites=satellites,
                    input_dirs=input_dirs,
                    persist=persist,
                    enrich=enrich,
                    continue_on_error=continue_on_error,
                )
            )
        except KeyboardInterrupt:
            logger.warning("worker_loop_interrupted", extra={"cycle": cycle})
            return WorkerRunSummary(
                cycle_count=cycle - 1,
                ingestion_summaries=tuple(summaries),
            )
        logger.info(
            "worker_cycle_completed",
            extra={"cycle": cycle, "max_cycles": max_cycles},
        )
        if max_cycles is None or cycle < max_cycles:
            time.sleep(interval_seconds)
    return WorkerRunSummary(cycle_count=cycle, ingestion_summaries=tuple(summaries))


def _ingest_function(satellite: str):
    """Resolve satellite names lazily so optional parser dependencies stay isolated."""

    if satellite == "snpp":
        from brin_hotspot.ingestion.snpp import ingest_snpp

        return ingest_snpp
    if satellite == "noaa20":
        from brin_hotspot.ingestion.noaa20 import ingest_noaa20

        return ingest_noaa20
    if satellite == "aqua":
        from brin_hotspot.ingestion.modis import ingest_aqua

        return ingest_aqua
    if satellite == "terra":
        from brin_hotspot.ingestion.modis import ingest_terra

        return ingest_terra
    if satellite == "landsat8":
        from brin_hotspot.ingestion.landsat8 import ingest_landsat8

        return ingest_landsat8
    raise ValueError(f"Unsupported satellite: {satellite}")
