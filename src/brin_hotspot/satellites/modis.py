from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from brin_hotspot.domain import HotspotDetection
from brin_hotspot.ingestion.sources import SatelliteInputSettings

type PathLike = str | Path


AQUA_SETTINGS = SatelliteInputSettings(
    satellite="aqua",
    input_subdir="aqua",
    resolution_meters=1000.0,
    duplicate_buffer_degrees=0.009009,
)
TERRA_SETTINGS = replace(AQUA_SETTINGS, satellite="terra", input_subdir="terra")

_SATELLITE_PREFIXES = {"a1": AQUA_SETTINGS, "t1": TERRA_SETTINGS}


def parse_modis_file(
    path: PathLike,
    settings: SatelliteInputSettings | None = None,
) -> list[HotspotDetection]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return parse_modis_converted_csv_file(path, settings)
    return parse_modis_hdf_file(path, settings)


def parse_modis_hdf_file(
    path: PathLike,
    settings: SatelliteInputSettings | None = None,
) -> list[HotspotDetection]:
    path = Path(path)
    settings = settings or settings_from_modis_filename(path)
    observed_at = parse_modis_observed_at(path)
    scene_id = path.stem

    try:
        from pyhdf.SD import SD, SDC
    except ImportError as exc:
        raise RuntimeError(
            "MODIS HDF parsing requires pyhdf. Install the HDF optional dependency "
            "in environments that process AQUA/TERRA MOD14 files."
        ) from exc

    hdf = SD(str(path), SDC.READ)
    longitudes = hdf.select("FP_longitude")
    latitudes = hdf.select("FP_latitude")
    confidences = hdf.select("FP_confidence")
    return parse_modis_records(
        latitudes=latitudes,
        longitudes=longitudes,
        confidences=confidences,
        observed_at=observed_at,
        source_file=path,
        scene_id=scene_id,
        settings=settings,
    )


def parse_modis_converted_csv_file(
    path: PathLike,
    settings: SatelliteInputSettings | None = None,
) -> list[HotspotDetection]:
    path = Path(path)
    settings = settings or settings_from_modis_filename(path)
    observed_at = parse_modis_observed_at(path)
    scene_id = scene_id_from_modis_path(path)

    detections: list[HotspotDetection] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required_fields = {"latitude", "longitude", "confidence"}
        if not reader.fieldnames or not required_fields.issubset(reader.fieldnames):
            raise ValueError(
                f"Converted MODIS CSV must include fields: {', '.join(sorted(required_fields))}"
            )

        for row in reader:
            confidence = float(row["confidence"])
            if confidence <= 0:
                continue
            row_observed_at = row.get("observed_at") or ""
            detections.append(
                HotspotDetection(
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    confidence=normalize_modis_confidence(confidence),
                    observed_at=(
                        datetime.fromisoformat(row_observed_at)
                        if row_observed_at
                        else observed_at
                    ),
                    satellite=settings.satellite,
                    source_file=Path(row.get("source_file") or path),
                    scene_id=row.get("scene_id") or scene_id,
                    source_station=settings.source_station,
                )
            )
    return detections


def parse_modis_records(
    *,
    latitudes: Iterable[float],
    longitudes: Iterable[float],
    confidences: Iterable[float],
    observed_at: datetime,
    source_file: Path,
    scene_id: str,
    settings: SatelliteInputSettings,
) -> list[HotspotDetection]:
    detections: list[HotspotDetection] = []
    for latitude, longitude, original_confidence in zip(
        latitudes,
        longitudes,
        confidences,
        strict=True,
    ):
        if original_confidence <= 0:
            continue
        detections.append(
            HotspotDetection(
                latitude=float(latitude),
                longitude=float(longitude),
                confidence=normalize_modis_confidence(float(original_confidence)),
                observed_at=observed_at,
                satellite=settings.satellite,
                source_file=source_file,
                scene_id=scene_id,
                source_station=settings.source_station,
            )
        )
    return detections


def normalize_modis_confidence(original_confidence: float) -> int:
    if original_confidence > 80:
        return 9
    if original_confidence > 30:
        return 8
    return 7


def parse_modis_observed_at(path: PathLike) -> datetime:
    path = Path(path)
    parts = scene_id_from_modis_path(path).split(".")
    if len(parts) < 3:
        raise ValueError(f"Cannot derive MODIS observation time from filename: {path}")
    return datetime.strptime("-".join(parts[1:3]), "%y%j-%H%M")


def scene_id_from_modis_path(path: PathLike) -> str:
    path = Path(path)
    name = path.name
    for suffix in (".mod14.hotspots.csv", ".mod14.csv", ".mod14.hdf"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)] + ".mod14"
    return path.stem


def settings_from_modis_filename(path: PathLike) -> SatelliteInputSettings:
    prefix = Path(path).name.split(".")[0].lower()
    try:
        return _SATELLITE_PREFIXES[prefix]
    except KeyError as exc:
        raise ValueError(f"Unsupported MODIS filename prefix: {path}") from exc


def find_aqua_files(input_dir: PathLike) -> list[Path]:
    return _find_modis_files(input_dir, prefix="a1")


def find_terra_files(input_dir: PathLike) -> list[Path]:
    return _find_modis_files(input_dir, prefix="t1")


def _find_modis_files(input_dir: PathLike, *, prefix: str) -> list[Path]:
    input_dir = Path(input_dir)
    converted = sorted(
        path for path in input_dir.rglob(f"{prefix}*.mod14*.csv") if path.is_file()
    )
    converted_scene_ids = {scene_id_from_modis_path(path) for path in converted}
    hdf = sorted(
        path
        for path in input_dir.rglob(f"{prefix}*.mod14.hdf")
        if path.is_file() and scene_id_from_modis_path(path) not in converted_scene_ids
    )
    return sorted([*converted, *hdf])
