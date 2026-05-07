from pathlib import Path

from brin_hotspot.config import Settings
from brin_hotspot.domain import IngestionSummary
from brin_hotspot.ingestion.viirs import ingest_viirs_text
from brin_hotspot.satellites.snpp import SNPP_SETTINGS, find_snpp_files, parse_snpp_file


def ingest_snpp(
    settings: Settings,
    input_dir: Path | None = None,
    input_dirs: tuple[Path, ...] | None = None,
    *,
    persist: bool = False,
    enrich: bool = False,
) -> IngestionSummary:
    return ingest_viirs_text(
        settings,
        satellite_settings=SNPP_SETTINGS,
        find_files=find_snpp_files,
        parse_file=parse_snpp_file,
        input_dir=input_dir,
        input_dirs=input_dirs,
        persist=persist,
        enrich=enrich,
    )
