from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg

from brin_hotspot.config import DatabaseSettings


@dataclass(frozen=True)
class IngestionRunRecord:
    id: str
    satellite: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    source_path: str | None
    message: str | None


@dataclass(frozen=True)
class SourceFileRecord:
    satellite: str
    path: str
    scene_id: str | None
    observed_at: datetime | None
    status: str
    processed_at: datetime | None
    last_error: str | None


class OperationsRepository:
    def __init__(self, database: DatabaseSettings):
        self._database = database

    def list_runs(
        self,
        *,
        satellite: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[IngestionRunRecord]:
        query = """
            SELECT id::text, satellite, status, started_at, finished_at, source_path, message
            FROM ingestion_runs
            WHERE (%s::text IS NULL OR satellite = %s)
              AND (%s::text IS NULL OR status = %s)
            ORDER BY started_at DESC
            LIMIT %s;
        """
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (satellite, satellite, status, status, limit))
                return [IngestionRunRecord(*row) for row in cursor.fetchall()]

    def list_source_files(
        self,
        *,
        satellite: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[SourceFileRecord]:
        query = """
            SELECT satellite, path, scene_id, observed_at, status, processed_at, last_error
            FROM source_files
            WHERE (%s::text IS NULL OR satellite = %s)
              AND (%s::text IS NULL OR status = %s)
            ORDER BY COALESCE(processed_at, first_seen_at) DESC
            LIMIT %s;
        """
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (satellite, satellite, status, status, limit))
                return [SourceFileRecord(*row) for row in cursor.fetchall()]

    def mark_source_file_pending(self, *, satellite: str, path: str) -> bool:
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE source_files
                        SET status = 'pending',
                            processed_at = NULL,
                            last_error = NULL
                        WHERE satellite = %s AND path = %s;
                        """,
                        (satellite, path),
                    )
                    return cursor.rowcount > 0
