from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from brin_hotspot.config import Settings
from brin_hotspot.domain import HotspotDetection, IngestionSummary
from brin_hotspot.ingestion.hotspot import ingest_hotspot_sources
from brin_hotspot.ingestion.sources import SourceItem
from brin_hotspot.satellites.snpp import ViirsTextSettings, scene_id_from_viirs_path


def ingest_viirs_text(
    settings: Settings,
    *,
    satellite_settings: ViirsTextSettings,
    find_files: Callable[[Path], list[Path]],
    parse_file: Callable[[Path], list[HotspotDetection]],
    input_dir: Path | None = None,
    input_dirs: tuple[Path, ...] | None = None,
    persist: bool = False,
    enrich: bool = False,
) -> IngestionSummary:
    return ingest_hotspot_sources(
        settings,
        satellite_settings=satellite_settings,
        find_sources=lambda source_dir: [
            SourceItem.single(source_file, source_key=scene_id_from_viirs_path(source_file))
            for source_file in find_files(source_dir)
        ],
        parse_source=lambda source: parse_file(source.path),
        input_dir=input_dir,
        input_dirs=input_dirs,
        persist=persist,
        enrich=enrich,
    )
