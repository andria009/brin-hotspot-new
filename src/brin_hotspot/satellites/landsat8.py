from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from brin_hotspot.domain import HotspotDetection
from brin_hotspot.ingestion.sources import SatelliteInputSettings, SourceItem

type PathLike = str | Path


LANDSAT8_SETTINGS = SatelliteInputSettings(
    satellite="landsat8",
    input_subdir="landsat8",
    resolution_meters=30.0,
    neighbor_multiplier=3.0,
)

CENTER_TIME_BY_PATH = {
    "099": "003908",
    "100": "004418",
    "101": "005015",
    "102": "005617",
    "103": "010201",
    "104": "010815",
    "105": "011412",
    "106": "012049",
    "107": "012646",
    "108": "013311",
    "109": "014009",
    "110": "014640",
    "111": "015254",
    "112": "015852",
    "113": "020504",
    "114": "021138",
    "115": "021759",
    "116": "022348",
    "117": "022729",
    "118": "023304",
    "119": "023931",
    "120": "024545",
    "121": "025253",
    "122": "025843",
    "123": "030527",
    "124": "030953",
    "125": "031554",
    "126": "032122",
    "127": "032745",
    "128": "033505",
    "129": "034007",
    "130": "034540",
    "131": "035209",
    "132": "042310",
    "133": "043322",
    "134": "042904",
    "004": "153909",
}

CONFIDENCE_BY_LABEL = {"Low": 7, "Medium": 8, "High": 9}


def find_landsat8_sources(input_dir: PathLike) -> list[SourceItem]:
    input_dir = Path(input_dir)
    grouped_files: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(input_dir.rglob("*firepixels.txt")):
        if not path.name.startswith(("LC08", "LO08")) or not path.is_file():
            continue
        scene_key = landsat8_scene_key(path)
        if scene_key is not None:
            grouped_files[scene_key].append(path)

    return [
        SourceItem(path=Path("landsat8") / scene_key, files=tuple(paths), source_key=scene_key)
        for scene_key, paths in sorted(grouped_files.items())
    ]


def parse_landsat8_source(source: SourceItem) -> list[HotspotDetection]:
    detections: list[HotspotDetection] = []
    for source_file in source.files:
        detections.extend(parse_landsat8_firepixels_file(source_file))
    return detections


def parse_landsat8_firepixels_file(path: PathLike) -> list[HotspotDetection]:
    path = Path(path)
    observed_at = parse_landsat8_observed_at(path)
    scene_id = landsat8_scene_key(path)
    if scene_id is None:
        raise ValueError(f"Cannot derive Landsat 8 scene id from filename: {path}")

    detections: list[HotspotDetection] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or "Scene_ID" in line:
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 8:
                raise ValueError(f"{path}:{line_number} expected at least 8 CSV columns")
            try:
                confidence = CONFIDENCE_BY_LABEL[parts[7]]
            except KeyError as exc:
                raise ValueError(
                    f"{path}:{line_number} unsupported confidence label: {parts[7]}"
                ) from exc
            detections.append(
                HotspotDetection(
                    latitude=float(parts[6]),
                    longitude=float(parts[5]),
                    confidence=confidence,
                    observed_at=observed_at,
                    satellite=LANDSAT8_SETTINGS.satellite,
                    source_file=path,
                    scene_id=scene_id,
                    source_station=LANDSAT8_SETTINGS.source_station,
                )
            )
    return detections


def parse_landsat8_observed_at(path: PathLike) -> datetime:
    scene_key = landsat8_scene_key(path)
    if scene_key is None:
        raise ValueError(f"Cannot derive Landsat 8 observation time from filename: {path}")
    date_text, wrs_path = scene_key.split("_")
    return datetime.strptime(f"{date_text}{CENTER_TIME_BY_PATH[wrs_path]}", "%Y%m%d%H%M%S")


def landsat8_scene_key(path: PathLike) -> str | None:
    parts = Path(path).name.split("_")
    if len(parts) < 4:
        return None
    wrs_path = parts[2][:3]
    if wrs_path not in CENTER_TIME_BY_PATH:
        return None
    return f"{parts[3]}_{wrs_path}"
