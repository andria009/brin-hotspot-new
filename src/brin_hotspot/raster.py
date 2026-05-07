from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from brin_hotspot.config import Settings
from brin_hotspot.repositories.raster_repository import RasterMetadata, RasterRepository

type PathLike = str | Path

SATELLITE_NAMES = {
    "AQUA": "aqua",
    "TERA": "tera",
    "SNPP": "snpp",
    "NOAA20": "noaa20",
    "L8": "landsat8",
}


@dataclass(frozen=True)
class RasterScanSummary:
    discovered_count: int
    persisted_count: int
    skipped_count: int


@dataclass(frozen=True)
class RasterTileSummary:
    discovered_count: int
    tiled_count: int
    skipped_count: int
    output_dirs: tuple[Path, ...]


def find_raster_files(input_dir: PathLike, *, raster_type: str = "FI") -> list[Path]:
    suffix = f"{raster_type}.tif"
    return sorted(path for path in Path(input_dir).rglob(f"*{suffix}") if path.is_file())


def parse_raster_filename(path: PathLike, *, raster_type: str = "FI") -> RasterMetadata:
    path = Path(path)
    parts = path.stem.split("_")
    if len(parts) < 3:
        raise ValueError(f"Cannot parse raster filename: {path}")
    satellite = SATELLITE_NAMES.get(parts[0])
    if satellite is None:
        raise ValueError(f"Unsupported raster satellite prefix: {path}")

    if parts[0] == "L8":
        if len(parts) < 4:
            raise ValueError(f"Cannot parse Landsat 8 raster filename: {path}")
        observed_at = datetime.strptime(parts[-3] + parts[-2], "%Y%m%d%H%M%S")
        infox = f"{parts[0]}_{parts[1]}"
    else:
        observed_at = datetime.strptime(parts[-3] + parts[-2], "%Y%m%d%H%M%S")
        infox = f"{parts[0]}_{parts[-3]}{parts[-2]}"

    return RasterMetadata(
        satellite=satellite,
        observed_at=observed_at,
        raster_type=raster_type,
        infox=infox,
        source_file=path,
        polygon_wkt="POLYGON EMPTY",
    )


def raster_bounds_polygon(path: PathLike) -> str:
    completed = subprocess.run(
        ["gdalinfo", "-json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    corners = payload.get("wgs84Extent", {}).get("coordinates")
    if corners:
        ring = corners[0]
    else:
        corner_coordinates = payload.get("cornerCoordinates")
        if not corner_coordinates:
            raise ValueError(f"gdalinfo did not report raster bounds for {path}")
        ring = [
            corner_coordinates["lowerLeft"],
            corner_coordinates["lowerRight"],
            corner_coordinates["upperRight"],
            corner_coordinates["upperLeft"],
            corner_coordinates["lowerLeft"],
        ]
    points = ", ".join(f"{lon} {lat}" for lon, lat in ring)
    return f"POLYGON(({points}))"


def scan_rasters(
    settings: Settings,
    *,
    input_dir: Path,
    raster_type: str = "FI",
    persist: bool = False,
) -> RasterScanSummary:
    files = find_raster_files(input_dir, raster_type=raster_type)
    repository = RasterRepository(settings.raster_database) if persist else None
    persisted_count = 0
    skipped_count = 0

    for path in files:
        metadata = parse_raster_filename(path, raster_type=raster_type)
        try:
            polygon_wkt = raster_bounds_polygon(path)
        except Exception:
            skipped_count += 1
            if persist:
                raise
            continue
        metadata = RasterMetadata(
            satellite=metadata.satellite,
            observed_at=metadata.observed_at,
            raster_type=metadata.raster_type,
            infox=metadata.infox,
            source_file=metadata.source_file,
            polygon_wkt=polygon_wkt,
        )
        if repository and repository.upsert_metadata(metadata):
            persisted_count += 1

    return RasterScanSummary(
        discovered_count=len(files),
        persisted_count=persisted_count,
        skipped_count=skipped_count,
    )


def tile_output_dir(base_dir: PathLike, metadata: RasterMetadata) -> Path:
    return (
        Path(base_dir)
        / metadata.satellite
        / f"{metadata.observed_at:%Y}"
        / f"{metadata.observed_at:%m}"
        / f"{metadata.observed_at:%d}"
        / f"{metadata.observed_at:%H%M%S}"
        / metadata.raster_type
    )


def gdal2tiles_command(
    source_file: PathLike,
    output_dir: PathLike,
    *,
    zoom: str,
    processes: int = 1,
) -> list[str]:
    return [
        "gdal2tiles.py",
        "--xyz",
        "--resume",
        "--webviewer=none",
        "--processes",
        str(processes),
        "-z",
        zoom,
        str(source_file),
        str(output_dir),
    ]


def generate_tiles(
    input_dir: PathLike,
    output_dir: PathLike,
    *,
    raster_type: str = "FI",
    zoom: str = "5-12",
    processes: int = 1,
    timeout_seconds: int = 1800,
) -> RasterTileSummary:
    files = find_raster_files(input_dir, raster_type=raster_type)
    tiled_count = 0
    skipped_count = 0
    output_dirs: list[Path] = []

    for path in files:
        metadata = parse_raster_filename(path, raster_type=raster_type)
        target_dir = tile_output_dir(output_dir, metadata)
        target_dir.mkdir(parents=True, exist_ok=True)
        command = gdal2tiles_command(path, target_dir, zoom=zoom, processes=processes)
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except Exception:
            skipped_count += 1
            continue
        tiled_count += 1
        output_dirs.append(target_dir)

    return RasterTileSummary(
        discovered_count=len(files),
        tiled_count=tiled_count,
        skipped_count=skipped_count,
        output_dirs=tuple(output_dirs),
    )
