from __future__ import annotations

import logging
import time
from collections.abc import Callable
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
    persist: bool = False,
    enrich: bool = False,
) -> tuple[IngestionSummary, ...]:
    summaries: list[IngestionSummary] = []
    for satellite in satellites:
        ingest = _ingest_function(satellite)
        logger.info(
            "worker_satellite_started",
            extra={"satellite": satellite, "persist": persist, "enrich": enrich},
        )
        summary = ingest(
            settings,
            settings.paths.input_dir / satellite,
            persist=persist,
            enrich=enrich,
        )
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
    persist: bool,
    enrich: bool,
    interval_seconds: int,
    max_cycles: int,
) -> WorkerRunSummary:
    summaries: list[IngestionSummary] = []
    for cycle in range(max_cycles):
        logger.info(
            "worker_cycle_started",
            extra={"cycle": cycle + 1, "max_cycles": max_cycles},
        )
        summaries.extend(
            run_ingestion_cycle(
                settings,
                satellites=satellites,
                persist=persist,
                enrich=enrich,
            )
        )
        logger.info(
            "worker_cycle_completed",
            extra={"cycle": cycle + 1, "max_cycles": max_cycles},
        )
        if cycle < max_cycles - 1:
            time.sleep(interval_seconds)
    return WorkerRunSummary(cycle_count=max_cycles, ingestion_summaries=tuple(summaries))


def _ingest_function(satellite: str):
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
