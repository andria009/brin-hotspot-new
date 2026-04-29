from __future__ import annotations

import psycopg

from brin_hotspot.config import DatabaseSettings
from brin_hotspot.domain import AdminLocation, HotspotDetection


class GeoRepository:
    """Read-side geospatial enrichment and filtering repository used by ingestion."""

    def __init__(self, database: DatabaseSettings):
        self._database = database

    def enrich_detection(
        self,
        detection: HotspotDetection,
        *,
        duplicate_buffer_degrees: float,
    ) -> HotspotDetection | None:
        """Return an enriched detection or None when it should be filtered.

        A detection is filtered when it falls inside a persistent anomaly polygon
        or duplicates an existing pixel from the same satellite within a short
        time and distance window.
        """

        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                # The SQL performs three operations in one round trip: locate
                # administrative boundaries, reject persistent anomalies, and
                # reject near-duplicate pixels.
                cursor.execute(
                    """
                    WITH point AS (
                        SELECT ST_SetSRID(ST_MakePoint(%s, %s), 4326) AS geom
                    ),
                    location AS (
                        SELECT
                            kec_ar.wa AS kecamatan,
                            kab_kota_ar.wa AS kabupaten,
                            prov_ar.wa AS provinsi
                        FROM point
                        JOIN kec_ar ON ST_Contains(kec_ar.geom, point.geom)
                        JOIN kab_kota_ar ON kab_kota_ar.gid = kec_ar.kab_id
                        JOIN prov_ar ON prov_ar.gid = kec_ar.prov_id
                        LIMIT 1
                    )
                    SELECT location.kecamatan, location.kabupaten, location.provinsi
                    FROM location
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM persistent_anomalies_buffer_500m anomaly, point
                        WHERE ST_Contains(anomaly.geom, point.geom)
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM hotspot_pixel existing, point
                        WHERE existing.satellite = %s
                          AND existing.observed_at >= %s::timestamp - interval '10 minutes'
                          AND existing.observed_at <= %s::timestamp + interval '10 minutes'
                          AND ST_Contains(
                              ST_Buffer(existing.coordinate::geometry, %s),
                              point.geom
                          )
                    );
                    """,
                    (
                        detection.longitude,
                        detection.latitude,
                        detection.satellite,
                        detection.observed_at,
                        detection.observed_at,
                        duplicate_buffer_degrees,
                    ),
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return detection.with_location(
            AdminLocation(
                kecamatan=row[0],
                kabupaten=_normalize_kabupaten(row[1]),
                provinsi=row[2],
            )
        )


def _normalize_kabupaten(value: str) -> str:
    return value.replace("KAB.", "").replace("KOTA", "").strip()
