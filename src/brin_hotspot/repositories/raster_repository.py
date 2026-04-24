from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg

from brin_hotspot.config import DatabaseSettings


@dataclass(frozen=True)
class RasterMetadata:
    satellite: str
    observed_at: datetime
    raster_type: str
    infox: str
    source_file: Path
    polygon_wkt: str


class RasterRepository:
    def __init__(self, database: DatabaseSettings):
        self._database = database

    def upsert_metadata(self, metadata: RasterMetadata) -> bool:
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        WITH vertex_row AS (
                            INSERT INTO raster_vertex (vertex, infox, satellite, observed_at)
                            VALUES (
                                ST_GeomFromText(%s, 4326)::geography,
                                %s,
                                %s,
                                %s
                            )
                            ON CONFLICT (infox) DO UPDATE
                            SET vertex = EXCLUDED.vertex,
                                satellite = EXCLUDED.satellite,
                                observed_at = EXCLUDED.observed_at
                            RETURNING vid
                        ),
                        inserted AS (
                            INSERT INTO raster_meta (
                                vertex_id,
                                satellite,
                                observed_at,
                                raster_type,
                                infox,
                                source_file
                            )
                            VALUES (
                                (SELECT vid FROM vertex_row),
                                %s,
                                %s,
                                %s,
                                %s,
                                %s
                            )
                            ON CONFLICT (infox, raster_type, source_file) DO NOTHING
                            RETURNING gid
                        )
                        SELECT EXISTS (SELECT 1 FROM inserted);
                        """,
                        (
                            metadata.polygon_wkt,
                            metadata.infox,
                            metadata.satellite,
                            metadata.observed_at,
                            metadata.satellite,
                            metadata.observed_at,
                            metadata.raster_type,
                            metadata.infox,
                            str(metadata.source_file),
                        ),
                    )
                    row = cursor.fetchone()
                    return bool(row and row[0])
