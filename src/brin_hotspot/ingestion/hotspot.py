from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from brin_hotspot.config import Settings
from brin_hotspot.domain import HotspotDetection, IngestionSummary
from brin_hotspot.ingestion.clustering import cluster_detections
from brin_hotspot.ingestion.csv_export import write_cluster_csv, write_pixel_csv
from brin_hotspot.ingestion.sources import SatelliteInputSettings, SourceItem
from brin_hotspot.repositories.geo_repository import GeoRepository
from brin_hotspot.repositories.hotspot_repository import HotspotRepository

logger = logging.getLogger(__name__)


def ingest_hotspot_sources(
    settings: Settings,
    *,
    satellite_settings: SatelliteInputSettings,
    find_sources: Callable[[Path], list[SourceItem]],
    parse_source: Callable[[SourceItem], list[HotspotDetection]],
    input_dir: Path | None = None,
    persist: bool = False,
    enrich: bool = False,
) -> IngestionSummary:
    run_id = uuid4()
    source_dir = input_dir or settings.paths.input_dir / (
        satellite_settings.input_subdir or satellite_settings.satellite
    )
    sources = find_sources(source_dir)
    repository = HotspotRepository(settings.hotspot_database) if persist else None
    geo_repository = GeoRepository(settings.hotspot_database) if enrich else None
    logger.info(
        "hotspot_ingestion_started",
        extra={
            "run_id": str(run_id),
            "satellite": satellite_settings.satellite,
            "input_dir": str(source_dir),
            "source_count": len(sources),
        },
    )

    detections: list[HotspotDetection] = []
    parsed_count = 0
    filtered_count = 0
    processed_files: list[Path] = []
    skipped_files: list[Path] = []

    for source in sources:
        if repository and all(
            repository.source_file_completed(satellite_settings.satellite, source_file)
            for source_file in source.files
        ):
            skipped_files.extend(source.files)
            logger.info(
                "hotspot_source_skipped",
                extra={
                    "run_id": str(run_id),
                    "satellite": satellite_settings.satellite,
                    "source": str(source.path),
                    "reason": "already_completed",
                },
            )
            continue

        parsed = parse_source(source)
        parsed_count += len(parsed)
        logger.info(
            "hotspot_source_parsed",
            extra={
                "run_id": str(run_id),
                "satellite": satellite_settings.satellite,
                "source": str(source.path),
                "source_file_count": len(source.files),
                "parsed_count": len(parsed),
            },
        )

        if geo_repository:
            enriched = []
            for detection in parsed:
                enriched_detection = geo_repository.enrich_detection(
                    detection,
                    duplicate_buffer_degrees=satellite_settings.duplicate_buffer_degrees,
                )
                if enriched_detection is None:
                    filtered_count += 1
                    continue
                enriched.append(enriched_detection)
            detections.extend(enriched)
            logger.info(
                "hotspot_source_enriched",
                extra={
                    "run_id": str(run_id),
                    "satellite": satellite_settings.satellite,
                    "source": str(source.path),
                    "enriched_count": len(enriched),
                    "filtered_count": len(parsed) - len(enriched),
                },
            )
        else:
            detections.extend(parsed)

        processed_files.extend(source.files)

    clusters = cluster_detections(
        detections,
        resolution_meters=satellite_settings.resolution_meters,
        neighbor_multiplier=satellite_settings.neighbor_multiplier,
    )
    output_dir = settings.paths.output_dir / satellite_settings.satellite
    cluster_csv = write_cluster_csv(clusters, output_dir / f"{run_id}_cluster.csv")
    pixel_radius_meters = round(satellite_settings.resolution_meters * 3)
    pixel_csv = write_pixel_csv(
        clusters,
        output_dir / f"{run_id}_pixel.csv",
        pixel_radius_meters=pixel_radius_meters,
    )

    persisted_cluster_count = 0
    persisted_pixel_count = 0
    if repository and processed_files:
        try:
            persisted_cluster_count, persisted_pixel_count = repository.persist_ingestion(
                run_id=run_id,
                satellite=satellite_settings.satellite,
                source_files=tuple(processed_files),
                clusters=clusters,
                pixel_radius_meters=pixel_radius_meters,
            )
        except Exception as exc:
            repository.mark_run_failed(run_id, satellite_settings.satellite, str(exc))
            raise

    summary = IngestionSummary(
        run_id=run_id,
        satellite=satellite_settings.satellite,
        source_files=tuple(processed_files),
        skipped_files=tuple(skipped_files),
        parsed_count=parsed_count,
        enriched_count=len(detections) if geo_repository else 0,
        filtered_count=filtered_count,
        cluster_count=len(clusters),
        persisted_cluster_count=persisted_cluster_count,
        persisted_pixel_count=persisted_pixel_count,
        output_files=(cluster_csv, pixel_csv),
    )
    logger.info(
        "hotspot_ingestion_completed",
        extra={
            "run_id": str(run_id),
            "satellite": summary.satellite,
            "parsed_count": summary.parsed_count,
            "enriched_count": summary.enriched_count,
            "filtered_count": summary.filtered_count,
            "cluster_count": summary.cluster_count,
            "persisted_cluster_count": summary.persisted_cluster_count,
            "persisted_pixel_count": summary.persisted_pixel_count,
            "skipped_file_count": len(summary.skipped_files),
            "output_files": [str(path) for path in summary.output_files],
        },
    )
    return summary
