from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from brin_hotspot.domain import HotspotDetection

type PathLike = str | Path


@dataclass(frozen=True)
class ViirsTextSettings:
    satellite: str
    file_glob: str
    input_subdir: str | None = None
    source_station: str = "Parepare"
    resolution_meters: float = 375.0
    neighbor_multiplier: float = 2.0
    duplicate_buffer_degrees: float = 0.00027027027


SNPP_SETTINGS = ViirsTextSettings(satellite="snpp", file_glob="AFIMG_npp*.txt")
NOAA20_SETTINGS = ViirsTextSettings(satellite="noaa20", file_glob="AFIMG_j01*.txt")
_VIIRS_FILENAME_TIME_RE = re.compile(r"_d(?P<date>\d{8})_t(?P<time>\d{6})(?P<fraction>\d*)")


def parse_viirs_text_file(
    path: PathLike,
    settings: ViirsTextSettings,
) -> list[HotspotDetection]:
    path = Path(path)
    observed_at = parse_observed_at_from_path(path)
    scene_id = scene_id_from_viirs_path(path)
    detections: list[HotspotDetection] = []

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 6:
                raise ValueError(f"{path}:{line_number} expected at least 6 CSV columns")

            detections.append(
                HotspotDetection(
                    latitude=float(parts[0]),
                    longitude=float(parts[1]),
                    confidence=int(float(parts[5])),
                    observed_at=observed_at,
                    satellite=settings.satellite,
                    source_file=path,
                    scene_id=scene_id,
                    source_station=settings.source_station,
                )
            )

    return detections


def parse_snpp_file(path: PathLike) -> list[HotspotDetection]:
    return parse_viirs_text_file(path, SNPP_SETTINGS)


def parse_noaa20_file(path: PathLike) -> list[HotspotDetection]:
    return parse_viirs_text_file(path, NOAA20_SETTINGS)


def scene_id_from_viirs_path(path: PathLike) -> str:
    return "_".join(Path(path).name.split("_")[:4])


def parse_observed_at_from_path(path: PathLike) -> datetime:
    path = Path(path)
    filename_match = _VIIRS_FILENAME_TIME_RE.search(path.name)
    if filename_match:
        fraction = filename_match.group("fraction")[:6].ljust(6, "0")
        return datetime.strptime(
            f"{filename_match.group('date')}{filename_match.group('time')}{fraction}",
            "%Y%m%d%H%M%S%f",
        )

    parts = path.parts
    for index in range(len(parts) - 4, -1, -1):
        candidate = parts[index : index + 4]
        if len(candidate) != 4:
            continue
        value = "-".join(candidate)
        try:
            return datetime.strptime(value, "%Y-%m-%d-%H%M%S%f")
        except ValueError:
            continue

    raise ValueError(f"Cannot derive SNPP observation time from path: {path}")


def find_viirs_text_files(input_dir: PathLike, settings: ViirsTextSettings) -> list[Path]:
    input_dir = Path(input_dir)
    return sorted(
        path
        for path in input_dir.rglob(settings.file_glob)
        if path.is_file()
    )


def find_snpp_files(input_dir: PathLike) -> list[Path]:
    return find_viirs_text_files(input_dir, SNPP_SETTINGS)


def find_noaa20_files(input_dir: PathLike) -> list[Path]:
    return find_viirs_text_files(input_dir, NOAA20_SETTINGS)
