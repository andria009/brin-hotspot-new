from __future__ import annotations

import argparse
import csv
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ConversionResult:
    source: Path
    output: Path
    row_count: int


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert MODIS MOD14 HDF4 fire-pixel files to hotspot CSV files."
    )
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--satellite",
        choices=("aqua", "terra", "all"),
        default="all",
        help="Satellite input family to convert.",
    )
    args = parser.parse_args()

    results = convert_tree(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        satellite=args.satellite,
    )
    for result in results:
        print(f"ok source={result.source} output={result.output} rows={result.row_count}")


def convert_tree(
    *,
    input_dir: Path,
    output_dir: Path,
    satellite: str = "all",
) -> list[ConversionResult]:
    prefixes = {
        "aqua": ("a1",),
        "terra": ("t1",),
        "all": ("a1", "t1"),
    }[satellite]
    sources = sorted(
        path
        for prefix in prefixes
        for path in input_dir.rglob(f"{prefix}*.mod14.hdf")
        if path.is_file()
    )
    return [convert_file(path, input_dir=input_dir, output_dir=output_dir) for path in sources]


def convert_file(path: Path, *, input_dir: Path, output_dir: Path) -> ConversionResult:
    output_path = converted_output_path(path, input_dir=input_dir, output_dir=output_dir)
    rows = list(read_hdf_rows(path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "latitude",
                "longitude",
                "confidence",
                "observed_at",
                "scene_id",
                "source_file",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return ConversionResult(source=path, output=output_path, row_count=len(rows))


def read_hdf_rows(path: Path) -> Iterable[dict[str, str]]:
    try:
        from pyhdf.SD import SD, SDC
    except ImportError as exc:
        raise RuntimeError("MODIS conversion requires pyhdf in the converter image.") from exc

    observed_at = parse_observed_at(path)
    scene_id = scene_id_from_path(path)
    hdf = SD(str(path), SDC.READ)
    latitudes = hdf.select("FP_latitude")
    longitudes = hdf.select("FP_longitude")
    confidences = hdf.select("FP_confidence")
    for latitude, longitude, confidence in zip(latitudes, longitudes, confidences, strict=True):
        confidence = float(confidence)
        if confidence <= 0:
            continue
        yield {
            "latitude": str(float(latitude)),
            "longitude": str(float(longitude)),
            "confidence": str(confidence),
            "observed_at": observed_at.isoformat(),
            "scene_id": scene_id,
            "source_file": str(path),
        }


def converted_output_path(path: Path, *, input_dir: Path, output_dir: Path) -> Path:
    relative = path.relative_to(input_dir)
    output_name = f"{scene_id_from_path(path)}.hotspots.csv"
    return output_dir / relative.parent / output_name


def parse_observed_at(path: Path) -> datetime:
    parts = scene_id_from_path(path).split(".")
    if len(parts) < 3:
        raise ValueError(f"Cannot derive MODIS observation time from filename: {path}")
    return datetime.strptime("-".join(parts[1:3]), "%y%j-%H%M")


def scene_id_from_path(path: Path) -> str:
    name = path.name
    suffix = ".mod14.hdf"
    if not name.lower().endswith(suffix):
        raise ValueError(f"Unsupported MODIS filename: {path}")
    return name[: -len(suffix)] + ".mod14"


if __name__ == "__main__":
    main()
