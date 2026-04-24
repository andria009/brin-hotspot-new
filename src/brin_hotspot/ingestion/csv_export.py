from __future__ import annotations

import csv
from pathlib import Path

from brin_hotspot.domain import HotspotCluster

CSV_HEADER = (
    "id",
    "tanggal (UTC)",
    "waktu (UTC)",
    "lintang",
    "bujur",
    "tingkat kepercayaan",
    "satelit",
    "radius kemungkinan",
    "kecamatan",
    "kabupaten",
    "provinsi",
    "tipe",
)


def write_cluster_csv(clusters: list[HotspotCluster], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        for index, cluster in enumerate(clusters, start=1):
            observed_at = cluster.detections[0].observed_at
            writer.writerow(
                (
                    index,
                    observed_at.date().isoformat(),
                    observed_at.time().isoformat(),
                    f"{cluster.latitude:.6f}",
                    f"{cluster.longitude:.6f}",
                    cluster.confidence,
                    cluster.detections[0].satellite,
                    cluster.radius_meters,
                    "",
                    "",
                    "",
                    "cluster",
                )
            )
    return output_path


def write_pixel_csv(
    clusters: list[HotspotCluster],
    output_path: Path,
    *,
    pixel_radius_meters: int,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        row_id = 1
        for cluster in clusters:
            for detection in cluster.detections:
                writer.writerow(
                    (
                        row_id,
                        detection.observed_at.date().isoformat(),
                        detection.observed_at.time().isoformat(),
                        f"{detection.latitude:.6f}",
                        f"{detection.longitude:.6f}",
                        detection.confidence,
                        detection.satellite,
                        pixel_radius_meters,
                        "",
                        "",
                        "",
                        "pixel",
                    )
                )
                row_id += 1
    return output_path
