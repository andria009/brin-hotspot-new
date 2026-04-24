from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

import psycopg

from brin_hotspot.config import DatabaseSettings
from brin_hotspot.domain import HotspotCluster, HotspotDetection


class HotspotRepository:
    def __init__(self, database: DatabaseSettings):
        self._database = database

    def source_file_completed(self, satellite: str, path: Path) -> bool:
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status = 'completed'
                    FROM source_files
                    WHERE satellite = %s AND path = %s;
                    """,
                    (satellite, str(path)),
                )
                row = cursor.fetchone()
                return bool(row and row[0])

    def persist_ingestion(
        self,
        *,
        run_id: UUID,
        satellite: str,
        source_files: tuple[Path, ...],
        clusters: list[HotspotCluster],
        pixel_radius_meters: int,
    ) -> tuple[int, int]:
        source_metadata = _source_metadata(clusters)
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    self._start_run(cursor, run_id, satellite, source_files)
                    cluster_count = 0
                    pixel_count = 0

                    for cluster in clusters:
                        cluster_id = self._insert_cluster(cursor, cluster)
                        cluster_count += 1
                        for detection in cluster.detections:
                            self._insert_pixel(
                                cursor,
                                detection,
                                cluster_id=cluster_id,
                                pixel_radius_meters=pixel_radius_meters,
                            )
                            pixel_count += 1

                    for source_file in source_files:
                        scene_id, observed_at = source_metadata.get(source_file, (None, None))
                        self._mark_source_file_completed(
                            cursor,
                            satellite,
                            source_file,
                            scene_id=scene_id,
                            observed_at=observed_at,
                        )

                    self._finish_run(cursor, run_id, "completed", None)
                    return cluster_count, pixel_count

    def mark_run_failed(self, run_id: UUID, satellite: str, message: str) -> None:
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    self._start_run(cursor, run_id, satellite, ())
                    self._finish_run(cursor, run_id, "failed", message)

    @staticmethod
    def _start_run(
        cursor: psycopg.Cursor,
        run_id: UUID,
        satellite: str,
        source_files: tuple[Path, ...],
    ) -> None:
        source_path = ",".join(str(path) for path in source_files) if source_files else None
        cursor.execute(
            """
            INSERT INTO ingestion_runs (id, satellite, status, source_path)
            VALUES (%s, %s, 'running', %s)
            ON CONFLICT (id) DO NOTHING;
            """,
            (run_id, satellite, source_path),
        )

    @staticmethod
    def _finish_run(cursor: psycopg.Cursor, run_id: UUID, status: str, message: str | None) -> None:
        cursor.execute(
            """
            UPDATE ingestion_runs
            SET status = %s, finished_at = now(), message = %s
            WHERE id = %s;
            """,
            (status, message, run_id),
        )

    @staticmethod
    def _mark_source_file_completed(
        cursor: psycopg.Cursor,
        satellite: str,
        source_file: Path,
        *,
        scene_id: str | None,
        observed_at: datetime | None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO source_files (satellite, path, scene_id, observed_at, status, processed_at)
            VALUES (%s, %s, %s, %s, 'completed', now())
            ON CONFLICT (satellite, path)
            DO UPDATE SET
                scene_id = EXCLUDED.scene_id,
                observed_at = EXCLUDED.observed_at,
                status = 'completed',
                processed_at = now(),
                last_error = NULL;
            """,
            (satellite, str(source_file), scene_id, observed_at),
        )

    @staticmethod
    def _insert_cluster(cursor: psycopg.Cursor, cluster: HotspotCluster) -> int:
        detection = cluster.detections[0]
        cursor.execute(
            """
            WITH inserted AS (
                INSERT INTO hotspot_cluster (
                    satellite,
                    coordinate,
                    conf_lvl,
                    provinsi,
                    kabupaten,
                    kecamatan,
                    radius,
                    source_station,
                    observed_at,
                    source_file,
                    scene_id
                )
                VALUES (
                    %s,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                ON CONFLICT (satellite, coordinate, observed_at) DO NOTHING
                RETURNING cid
            )
            SELECT cid FROM inserted
            UNION ALL
            SELECT cid
            FROM hotspot_cluster
            WHERE satellite = %s
              AND coordinate = ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
              AND observed_at = %s
            LIMIT 1;
            """,
            (
                detection.satellite,
                cluster.longitude,
                cluster.latitude,
                cluster.confidence,
                detection.location.provinsi if detection.location else None,
                detection.location.kabupaten if detection.location else None,
                detection.location.kecamatan if detection.location else None,
                cluster.radius_meters,
                detection.source_station,
                detection.observed_at,
                str(detection.source_file),
                detection.scene_id,
                detection.satellite,
                cluster.longitude,
                cluster.latitude,
                detection.observed_at,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to insert or fetch hotspot cluster")
        return int(row[0])

    @staticmethod
    def _insert_pixel(
        cursor: psycopg.Cursor,
        detection: HotspotDetection,
        *,
        cluster_id: int,
        pixel_radius_meters: int,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO hotspot_pixel (
                satellite,
                coordinate,
                conf_lvl,
                cluster_id,
                provinsi,
                kabupaten,
                kecamatan,
                source_station,
                radius,
                observed_at,
                source_file,
                scene_id
            )
            VALUES (
                %s,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (satellite, coordinate, observed_at) DO UPDATE
            SET cluster_id = EXCLUDED.cluster_id;
            """,
            (
                detection.satellite,
                detection.longitude,
                detection.latitude,
                detection.confidence,
                cluster_id,
                detection.location.provinsi if detection.location else None,
                detection.location.kabupaten if detection.location else None,
                detection.location.kecamatan if detection.location else None,
                detection.source_station,
                pixel_radius_meters,
                detection.observed_at,
                str(detection.source_file),
                detection.scene_id,
            ),
        )


def _source_metadata(clusters: list[HotspotCluster]) -> dict[Path, tuple[str, datetime]]:
    metadata = {}
    for cluster in clusters:
        for detection in cluster.detections:
            metadata[detection.source_file] = (detection.scene_id, detection.observed_at)
    return metadata
