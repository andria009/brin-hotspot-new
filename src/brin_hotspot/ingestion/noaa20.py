from __future__ import annotations

from pathlib import Path

from brin_hotspot.config import Settings
from brin_hotspot.domain import IngestionSummary
from brin_hotspot.ingestion.viirs import ingest_viirs_text
from brin_hotspot.satellites.noaa20 import NOAA20_SETTINGS, find_noaa20_files, parse_noaa20_file


def ingest_noaa20(
    settings: Settings,
    input_dir: Path | None = None,
    *,
    persist: bool = False,
    enrich: bool = False,
) -> IngestionSummary:
    return ingest_viirs_text(
        settings,
        satellite_settings=NOAA20_SETTINGS,
        find_files=find_noaa20_files,
        parse_file=parse_noaa20_file,
        input_dir=input_dir,
        persist=persist,
        enrich=enrich,
    )

