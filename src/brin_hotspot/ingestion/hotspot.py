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
    cluster_count = 0
    persisted_cluster_count = 0
    persisted_pixel_count = 0
    processed_files: list[Path] = []
    skipped_files: list[Path] = []
    output_files: list[Path] = []
    pixel_radius_meters = round(satellite_settings.resolution_meters * 3)

    if repository:
        reset_count = repository.reset_running_source_files(
            satellite=satellite_settings.satellite,
            message="reset at ingestion startup",
        )
        if reset_count:
            logger.warning(
                "hotspot_running_sources_reset",
                extra={
                    "run_id": str(run_id),
                    "satellite": satellite_settings.satellite,
                    "reset_count": reset_count,
                },
            )
        repository.start_run(
            run_id,
            satellite_settings.satellite,
            source_path=str(source_dir),
        )

    try:
        for source_index, source in enumerate(sources, start=1):
            (
                source_parsed_count,
                source_filtered_count,
                source_cluster_count,
                source_persisted_cluster_count,
                source_persisted_pixel_count,
                source_detections,
                source_output_files,
                source_processed_files,
                source_skipped_files,
            ) = _process_source(
                settings=settings,
                run_id=run_id,
                source_index=source_index,
                source=source,
                satellite_settings=satellite_settings,
                parse_source=parse_source,
                repository=repository,
                geo_repository=geo_repository,
                pixel_radius_meters=pixel_radius_meters,
                persist=persist,
            )
            parsed_count += source_parsed_count
            filtered_count += source_filtered_count
            cluster_count += source_cluster_count
            persisted_cluster_count += source_persisted_cluster_count
            persisted_pixel_count += source_persisted_pixel_count
            detections.extend(source_detections)
            output_files.extend(source_output_files)
            processed_files.extend(source_processed_files)
            skipped_files.extend(source_skipped_files)
    except KeyboardInterrupt:
        if repository:
            repository.finish_run(run_id, "interrupted", "interrupted by operator")
        raise
    except BaseException as exc:
        if repository:
            repository.finish_run(run_id, "failed", str(exc))
        raise

    if repository:
        repository.finish_run(run_id, "completed", None)

    summary = IngestionSummary(
        run_id=run_id,
        satellite=satellite_settings.satellite,
        source_files=tuple(processed_files),
        skipped_files=tuple(skipped_files),
        parsed_count=parsed_count,
        enriched_count=len(detections) if geo_repository else 0,
        filtered_count=filtered_count,
        cluster_count=cluster_count,
        persisted_cluster_count=persisted_cluster_count,
        persisted_pixel_count=persisted_pixel_count,
        output_files=tuple(output_files),
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


def _process_source(
    *,
    settings: Settings,
    run_id,
    source_index: int,
    source: SourceItem,
    satellite_settings: SatelliteInputSettings,
    parse_source: Callable[[SourceItem], list[HotspotDetection]],
    repository: HotspotRepository | None,
    geo_repository: GeoRepository | None,
    pixel_radius_meters: int,
    persist: bool,
) -> tuple[
    int,
    int,
    int,
    int,
    int,
    list[HotspotDetection],
    list[Path],
    list[Path],
    list[Path],
]:
    if repository and all(
        repository.source_file_completed(satellite_settings.satellite, source_file)
        for source_file in source.files
    ):
        logger.info(
            "hotspot_source_skipped",
            extra={
                "run_id": str(run_id),
                "satellite": satellite_settings.satellite,
                "source": str(source.path),
                "reason": "already_completed",
            },
        )
        return (0, 0, 0, 0, 0, [], [], [], list(source.files))

    if repository:
        for source_file in source.files:
            repository.mark_source_file_running(satellite_settings.satellite, source_file)

    try:
        parsed = parse_source(source)
    except Exception as exc:
        if repository:
            for source_file in source.files:
                repository.mark_source_file_failed(
                    satellite_settings.satellite,
                    source_file,
                    str(exc),
                )
        logger.exception(
            "hotspot_source_failed",
            extra={
                "run_id": str(run_id),
                "satellite": satellite_settings.satellite,
                "source": str(source.path),
            },
        )
        if persist:
            return (0, 0, 0, 0, 0, [], [], [], [])
        raise

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

    source_filtered_count = 0
    if geo_repository:
        source_detections = []
        for detection in parsed:
            enriched_detection = geo_repository.enrich_detection(
                detection,
                duplicate_buffer_degrees=satellite_settings.duplicate_buffer_degrees,
            )
            if enriched_detection is None:
                source_filtered_count += 1
                continue
            source_detections.append(enriched_detection)
        logger.info(
            "hotspot_source_enriched",
            extra={
                "run_id": str(run_id),
                "satellite": satellite_settings.satellite,
                "source": str(source.path),
                "enriched_count": len(source_detections),
                "filtered_count": source_filtered_count,
            },
        )
    else:
        source_detections = parsed

    source_clusters = cluster_detections(
        source_detections,
        resolution_meters=satellite_settings.resolution_meters,
        neighbor_multiplier=satellite_settings.neighbor_multiplier,
    )
    source_output_dir = settings.paths.output_dir / satellite_settings.satellite
    source_output_prefix = f"{run_id}_{source_index:05d}_{_safe_output_stem(source.path)}"
    cluster_csv = write_cluster_csv(
        source_clusters,
        source_output_dir / f"{source_output_prefix}_cluster.csv",
    )
    pixel_csv = write_pixel_csv(
        source_clusters,
        source_output_dir / f"{source_output_prefix}_pixel.csv",
        pixel_radius_meters=pixel_radius_meters,
    )

    source_persisted_cluster_count = 0
    source_persisted_pixel_count = 0
    try:
        if repository:
            source_persisted_cluster_count, source_persisted_pixel_count = (
                repository.persist_ingestion(
                    run_id=run_id,
                    satellite=satellite_settings.satellite,
                    source_files=source.files,
                    clusters=source_clusters,
                    pixel_radius_meters=pixel_radius_meters,
                    finish_run=False,
                )
            )
    except Exception as exc:
        if repository:
            for source_file in source.files:
                repository.mark_source_file_failed(
                    satellite_settings.satellite,
                    source_file,
                    str(exc),
                )
        raise

    return (
        len(parsed),
        source_filtered_count,
        len(source_clusters),
        source_persisted_cluster_count,
        source_persisted_pixel_count,
        source_detections,
        [cluster_csv, pixel_csv],
        list(source.files),
        [],
    )


def _safe_output_stem(path: Path) -> str:
    safe = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in path.stem)
    return safe[:80] or "source"
