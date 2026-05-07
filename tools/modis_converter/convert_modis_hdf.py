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
        choices=("aqua", "tera", "all"),
        default="all",
        help="Satellite input family to convert.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip outputs that are newer than or as new as their source HDF file.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Trace discovered and processed source files.",
    )
    args = parser.parse_args()

    print(
        f"started input_dir={args.input_dir} output_dir={args.output_dir} "
        f"satellite={args.satellite} skip_existing={args.skip_existing}",
        flush=True,
    )
    results = convert_tree(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        satellite=args.satellite,
        skip_existing=args.skip_existing,
        debug=args.debug,
    )
    for result in results:
        if result.status == "failed":
            print(
                f"failed source={result.source} output={result.output} "
                f"rows={result.row_count} error={result.message}",
                file=sys.stderr,
                flush=True,
            )
        elif result.status == "skipped":
            print(f"skipped source={result.source} output={result.output} rows=0", flush=True)
        else:
            print(
                f"ok source={result.source} output={result.output} rows={result.row_count}",
                flush=True,
            )
    print(
        f"completed input_dir={args.input_dir} output_dir={args.output_dir} "
        f"satellite={args.satellite} files={len(results)}",
        flush=True,
    )


def convert_tree(
    *,
    input_dir: Path,
    output_dir: Path,
    satellite: str = "all",
    skip_existing: bool = False,
    debug: bool = False,
) -> list[ConversionResult]:
    sources = discover_sources(input_dir, satellite=satellite)
    if debug:
        print(
            f"discovered input_dir={input_dir} satellite={satellite} files={len(sources)}",
            flush=True,
        )
    results: list[ConversionResult] = []
    for path in sources:
        try:
            if debug:
                print(f"processing source={path}", flush=True)
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


def discover_sources(input_dir: Path, *, satellite: str) -> list[Path]:
    """Find MODIS HDF files and production `.data` wrappers for a satellite."""

    satellite_markers = {
        "aqua": ("a1", "aqua_or"),
        "tera": ("t1", "tera_or"),
        "all": ("a1", "aqua_or", "t1", "tera_or"),
    }[satellite]
    sources: list[Path] = []
    for path in input_dir.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        is_mod14_hdf = name.endswith(".mod14.hdf") and name.startswith(satellite_markers)
        is_production_data = name.endswith(".data") and any(
            marker in name for marker in satellite_markers if marker.endswith("_or")
        )
        if is_mod14_hdf or is_production_data:
            sources.append(path)
    return sorted(sources)


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
    if path.name.lower().endswith(".data"):
        timestamp = path.name.split(".", 1)[0]
        return datetime.strptime(timestamp[:12], "%Y%m%d%H%M")
    parts = scene_id_from_path(path).split(".")
    if len(parts) < 3:
        raise ValueError(f"Cannot derive MODIS observation time from filename: {path}")
    return datetime.strptime("-".join(parts[1:3]), "%y%j-%H%M")


def scene_id_from_path(path: Path) -> str:
    name = path.name
    lowered = name.lower()
    if lowered.endswith(".data"):
        observed_at = parse_observed_at(path)
        prefix = "t1" if "tera_or" in lowered else "a1"
        return f"{prefix}.{observed_at:%y%j}.{observed_at:%H%M}.mod14"
    suffix = ".mod14.hdf"
    if not lowered.endswith(suffix):
        raise ValueError(f"Unsupported MODIS filename: {path}")
    return name[: -len(suffix)] + ".mod14"


if __name__ == "__main__":
    main()
