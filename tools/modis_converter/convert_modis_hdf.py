from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ConversionResult:
    source: Path
    output: Path
    row_count: int
    status: str = "converted"
    message: str | None = None


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
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip outputs that are newer than or as new as their source HDF file.",
    )
    args = parser.parse_args()

    results = convert_tree(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        satellite=args.satellite,
        skip_existing=args.skip_existing,
    )
    for result in results:
        if result.status == "failed":
            print(
                f"failed source={result.source} output={result.output} "
                f"rows={result.row_count} error={result.message}",
                file=sys.stderr,
            )
        elif result.status == "skipped":
            print(f"skipped source={result.source} output={result.output} rows=0")
        else:
            print(f"ok source={result.source} output={result.output} rows={result.row_count}")


def convert_tree(
    *,
    input_dir: Path,
    output_dir: Path,
    satellite: str = "all",
    skip_existing: bool = False,
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
    results: list[ConversionResult] = []
    for path in sources:
        try:
            results.append(
                convert_file(
                    path,
                    input_dir=input_dir,
                    output_dir=output_dir,
                    skip_existing=skip_existing,
                )
            )
        except Exception as exc:
            output_path = converted_output_path(path, input_dir=input_dir, output_dir=output_dir)
            results.append(
                ConversionResult(
                    source=path,
                    output=output_path,
                    row_count=0,
                    status="failed",
                    message=str(exc),
                )
            )
    return results


def convert_file(
    path: Path,
    *,
    input_dir: Path,
    output_dir: Path,
    skip_existing: bool = False,
) -> ConversionResult:
    output_path = converted_output_path(path, input_dir=input_dir, output_dir=output_dir)
    if (
        skip_existing
        and output_path.exists()
        and output_path.stat().st_mtime >= path.stat().st_mtime
    ):
        return ConversionResult(source=path, output=output_path, row_count=0, status="skipped")

    rows = list(read_hdf_rows(path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output_path = output_path.with_name(f".{output_path.name}.tmp")
    with temp_output_path.open("w", encoding="utf-8", newline="") as handle:
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
    temp_output_path.replace(output_path)
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

    latitude_values = read_sds_values(latitudes)
    longitude_values = read_sds_values(longitudes)
    confidence_values = read_sds_values(confidences)
    for latitude, longitude, confidence in zip(
        latitude_values,
        longitude_values,
        confidence_values,
        strict=True,
    ):
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


def read_sds_values(dataset) -> Sequence:
    info = dataset.info()
    dimensions = info[2]
    if isinstance(dimensions, int):
        dimensions = (dimensions,)
    if any(dimension == 0 for dimension in dimensions):
        return ()
    values = dataset[:]
    if isinstance(values, str | bytes):
        return (values,)
    try:
        iter(values)
    except TypeError:
        return (values,)
    return values


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
