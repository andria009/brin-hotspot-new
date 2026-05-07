from __future__ import annotations

from pathlib import Path

from brin_hotspot.config import Settings
from brin_hotspot.domain import IngestionSummary
from brin_hotspot.ingestion.hotspot import ingest_hotspot_sources
from brin_hotspot.satellites.landsat8 import (
    LANDSAT8_SETTINGS,
    find_landsat8_sources,
    parse_landsat8_source,
)


def ingest_landsat8(
    settings: Settings,
    input_dir: Path | None = None,
    input_dirs: tuple[Path, ...] | None = None,
    *,
    persist: bool = False,
    enrich: bool = False,
) -> IngestionSummary:
    return ingest_hotspot_sources(
        settings,
        satellite_settings=LANDSAT8_SETTINGS,
        find_sources=find_landsat8_sources,
        parse_source=parse_landsat8_source,
        input_dir=input_dir,
        input_dirs=input_dirs,
        persist=persist,
        enrich=enrich,
    )
