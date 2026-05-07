from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from brin_hotspot.config import Settings
from brin_hotspot.domain import IngestionSummary
from brin_hotspot.ingestion.hotspot import ingest_hotspot_sources
from brin_hotspot.ingestion.sources import SatelliteInputSettings, SourceItem
from brin_hotspot.satellites.modis import (
    AQUA_SETTINGS,
    TERA_SETTINGS,
    find_aqua_files,
    find_tera_files,
    parse_modis_file,
    scene_id_from_modis_path,
)


def ingest_aqua(
    settings: Settings,
    input_dir: Path | None = None,
    input_dirs: tuple[Path, ...] | None = None,
    *,
    persist: bool = False,
    enrich: bool = False,
) -> IngestionSummary:
    return _ingest_modis(
        settings,
        satellite_settings=AQUA_SETTINGS,
        find_files=find_aqua_files,
        input_dir=input_dir,
        input_dirs=input_dirs,
        persist=persist,
        enrich=enrich,
    )


def ingest_tera(
    settings: Settings,
    input_dir: Path | None = None,
    input_dirs: tuple[Path, ...] | None = None,
    *,
    persist: bool = False,
    enrich: bool = False,
) -> IngestionSummary:
    return _ingest_modis(
        settings,
        satellite_settings=TERA_SETTINGS,
        find_files=find_tera_files,
        input_dir=input_dir,
        input_dirs=input_dirs,
        persist=persist,
        enrich=enrich,
    )


def _ingest_modis(
    settings: Settings,
    *,
    satellite_settings: SatelliteInputSettings,
    find_files: Callable[[Path], list[Path]],
    input_dir: Path | None,
    input_dirs: tuple[Path, ...] | None,
    persist: bool,
    enrich: bool,
) -> IngestionSummary:
    return ingest_hotspot_sources(
        settings,
        satellite_settings=satellite_settings,
        find_sources=lambda source_dir: [
            SourceItem.single(source_file, source_key=scene_id_from_modis_path(source_file))
            for source_file in find_files(source_dir)
        ],
        parse_source=lambda source: parse_modis_file(source.path, satellite_settings),
        input_dir=input_dir,
        input_dirs=input_dirs,
        persist=persist,
        enrich=enrich,
    )
