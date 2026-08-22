from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import psycopg

from brin_hotspot.api.schemas import (
    HotspotStatisticsResponse,
    HotspotTrendResponse,
    IngestionRunResponse,
    LocationOptionsResponse,
    OperationalSummary,
    SatelliteSummary,
    SourceFileResponse,
    SourceStatusSummary,
    StatisticItem,
    TrendItem,
)
from brin_hotspot.config import DatabaseSettings
from brin_hotspot.domain import AdminLocation, HotspotDetection
from brin_hotspot.ingestion.clustering import ClusteringProjection, cluster_detections
from brin_hotspot.satellites.landsat8 import LANDSAT8_SETTINGS
from brin_hotspot.satellites.modis import AQUA_SETTINGS, TERA_SETTINGS
from brin_hotspot.satellites.snpp import NOAA20_SETTINGS, SNPP_SETTINGS

HotspotKind = Literal["pixel", "cluster"]

_SATELLITE_CLUSTER_SETTINGS = {
    "snpp": SNPP_SETTINGS,
    "noaa20": NOAA20_SETTINGS,
    "aqua": AQUA_SETTINGS,
    "tera": TERA_SETTINGS,
    "landsat8": LANDSAT8_SETTINGS,
}


class ReadOnlyHotspotRepository:
    def __init__(self, database: DatabaseSettings):
        self._database = database

    def summary(self) -> OperationalSummary:
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH satellites AS (
                        SELECT satellite FROM hotspot_pixel
                        UNION
                        SELECT satellite FROM hotspot_cluster
                        UNION
                        SELECT satellite FROM source_files
                    ),
                    pixel_counts AS (
                        SELECT satellite,
                               count(*)::int AS pixels,
                               count(provinsi)::int AS enriched_pixels,
                               max(observed_at) AS latest_observed_at
                        FROM hotspot_pixel
                        GROUP BY satellite
                    ),
                    cluster_counts AS (
                        SELECT satellite, count(*)::int AS clusters
                        FROM hotspot_cluster
                        GROUP BY satellite
                    )
                    SELECT satellites.satellite,
                           COALESCE(cluster_counts.clusters, 0),
                           COALESCE(pixel_counts.pixels, 0),
                           COALESCE(pixel_counts.enriched_pixels, 0),
                           pixel_counts.latest_observed_at
                    FROM satellites
                    LEFT JOIN pixel_counts USING (satellite)
                    LEFT JOIN cluster_counts USING (satellite)
                    ORDER BY satellites.satellite;
                    """
                )
                satellites = [
                    SatelliteSummary(
                        satellite=row[0],
                        clusters=row[1],
                        pixels=row[2],
                        enriched_pixels=row[3],
                        latest_observed_at=row[4],
                    )
                    for row in cursor.fetchall()
                ]
                cursor.execute(
                    """
                    SELECT satellite, status, count(*)::int
                    FROM source_files
                    GROUP BY satellite, status
                    ORDER BY satellite, status;
                    """
                )
                source_statuses = [
                    SourceStatusSummary(satellite=row[0], status=row[1], count=row[2])
                    for row in cursor.fetchall()
                ]
        return OperationalSummary(
            generated_at=datetime.now().astimezone(),
            satellites=satellites,
            source_statuses=source_statuses,
        )

    def hotspots(
        self,
        *,
        kind: HotspotKind,
        satellites: Sequence[str] = (),
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        min_confidence: int | None = None,
        province: str | None = None,
        kabupaten: str | None = None,
        kecamatan: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        limit: int = 1000,
        cluster_projection: ClusteringProjection = "local",
    ) -> list[dict[str, Any]]:
        if kind == "cluster":
            return self._clustered_hotspot_features(
                satellites=satellites,
                observed_from=observed_from,
                observed_to=observed_to,
                min_confidence=min_confidence,
                province=province,
                kabupaten=kabupaten,
                kecamatan=kecamatan,
                bbox=bbox,
                limit=limit,
                cluster_projection=cluster_projection,
            )

        table = "hotspot_pixel" if kind == "pixel" else "hotspot_cluster"
        id_column = "hid" if kind == "pixel" else "cid"
        query = f"""
            SELECT
                {id_column},
                satellite,
                ST_Y(coordinate::geometry) AS latitude,
                ST_X(coordinate::geometry) AS longitude,
                conf_lvl,
                provinsi,
                kabupaten,
                kecamatan,
                radius,
                source_station,
                observed_at,
                source_file,
                scene_id
            FROM {table}
        """
        where, params = _hotspot_filters(
            satellites=satellites,
            observed_from=observed_from,
            observed_to=observed_to,
            min_confidence=min_confidence,
            province=province,
            kabupaten=kabupaten,
            kecamatan=kecamatan,
            bbox=bbox,
        )
        if where:
            query += " WHERE " + " AND ".join(where)
        query += f" ORDER BY observed_at DESC, {id_column} DESC LIMIT %s;"
        params.append(min(max(limit, 1), 5000))

        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return [
                    _hotspot_feature(kind=kind, id_column=id_column, row=row)
                    for row in cursor.fetchall()
                ]

    def hotspot_count(
        self,
        *,
        kind: HotspotKind,
        satellites: Sequence[str] = (),
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        min_confidence: int | None = None,
        province: str | None = None,
        kabupaten: str | None = None,
        kecamatan: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        cluster_projection: ClusteringProjection = "local",
    ) -> int:
        if kind == "cluster":
            return len(
                self._clustered_hotspot_features(
                    satellites=satellites,
                    observed_from=observed_from,
                    observed_to=observed_to,
                    min_confidence=min_confidence,
                    province=province,
                    kabupaten=kabupaten,
                    kecamatan=kecamatan,
                    bbox=bbox,
                    limit=None,
                    cluster_projection=cluster_projection,
                )
            )

        table = "hotspot_pixel" if kind == "pixel" else "hotspot_cluster"
        query = f"SELECT count(*)::int FROM {table}"
        where, params = _hotspot_filters(
            satellites=satellites,
            observed_from=observed_from,
            observed_to=observed_to,
            min_confidence=min_confidence,
            province=province,
            kabupaten=kabupaten,
            kecamatan=kecamatan,
            bbox=bbox,
        )
        if where:
            query += " WHERE " + " AND ".join(where)
        query += ";"

        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return int(row[0]) if row else 0

    def statistics(
        self,
        *,
        kind: HotspotKind,
        satellites: Sequence[str] = (),
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        min_confidence: int | None = None,
        province: str | None = None,
        kabupaten: str | None = None,
        kecamatan: str | None = None,
        limit: int = 20,
        cluster_projection: ClusteringProjection = "local",
    ) -> HotspotStatisticsResponse:
        if kecamatan:
            level = "satellite"
            group_expression = "satellite"
            group_alias = "satellite"
        elif kabupaten:
            level = "kecamatan"
            group_expression = "COALESCE(NULLIF(kecamatan, ''), 'Unknown')"
            group_alias = "label"
        elif province:
            level = "kabupaten"
            group_expression = "COALESCE(NULLIF(kabupaten, ''), 'Unknown')"
            group_alias = "label"
        else:
            level = "province"
            group_expression = "COALESCE(NULLIF(provinsi, ''), 'Unknown')"
            group_alias = "label"

        if kind == "cluster":
            features = self._clustered_hotspot_features(
                satellites=satellites,
                observed_from=observed_from,
                observed_to=observed_to,
                min_confidence=min_confidence,
                province=province,
                kabupaten=kabupaten,
                kecamatan=kecamatan,
                bbox=None,
                limit=None,
                cluster_projection=cluster_projection,
            )
            grouped = _group_cluster_statistics(features, level)
            items = [
                StatisticItem(
                    label=label,
                    total=sum(satellite_counts.values()),
                    satellites=satellite_counts,
                )
                for label, satellite_counts in grouped.items()
            ]
            items.sort(key=lambda item: (-item.total, item.label))
            return HotspotStatisticsResponse(level=level, items=items[: min(max(limit, 1), 50)])

        table = "hotspot_pixel"
        where, params = _hotspot_filters(
            satellites=satellites,
            observed_from=observed_from,
            observed_to=observed_to,
            min_confidence=min_confidence,
            province=province,
            kabupaten=kabupaten,
            kecamatan=kecamatan,
            bbox=None,
        )
        query = f"""
            SELECT {group_expression} AS {group_alias},
                   satellite,
                   count(*)::int AS total
            FROM {table}
        """
        if where:
            query += " WHERE " + " AND ".join(where)
        query += f"""
            GROUP BY {group_expression}, satellite
            ORDER BY {group_expression}, satellite;
        """

        grouped: dict[str, dict[str, int]] = {}
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                for label, satellite, count in cursor.fetchall():
                    satellite_counts = grouped.setdefault(label, {})
                    satellite_counts[satellite] = count

        items = [
            StatisticItem(
                label=label,
                total=sum(satellite_counts.values()),
                satellites=satellite_counts,
            )
            for label, satellite_counts in grouped.items()
        ]
        items.sort(key=lambda item: (-item.total, item.label))
        return HotspotStatisticsResponse(level=level, items=items[: min(max(limit, 1), 50)])

    def trend(
        self,
        *,
        kind: HotspotKind,
        satellites: Sequence[str] = (),
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        min_confidence: int | None = None,
        province: str | None = None,
        kabupaten: str | None = None,
        kecamatan: str | None = None,
        cluster_projection: ClusteringProjection = "local",
    ) -> HotspotTrendResponse:
        if kind == "cluster":
            features = self._clustered_hotspot_features(
                satellites=satellites,
                observed_from=observed_from,
                observed_to=observed_to,
                min_confidence=min_confidence,
                province=province,
                kabupaten=kabupaten,
                kecamatan=kecamatan,
                bbox=None,
                limit=None,
                cluster_projection=cluster_projection,
            )
            grouped: dict[str, dict[str, int]] = {}
            for feature in features:
                properties = feature["properties"]
                observed_at = properties.get("observed_at")
                satellite = properties.get("satellite")
                if not observed_at or not satellite:
                    continue
                date_key = str(observed_at)[:10]
                satellite_counts = grouped.setdefault(date_key, {})
                satellite_counts[str(satellite)] = satellite_counts.get(str(satellite), 0) + 1
            return HotspotTrendResponse(
                items=[
                    TrendItem(
                        date=date_key,
                        total=sum(satellite_counts.values()),
                        satellites=satellite_counts,
                    )
                    for date_key, satellite_counts in sorted(grouped.items())
                ]
            )

        table = "hotspot_pixel"
        where, params = _hotspot_filters(
            satellites=satellites,
            observed_from=observed_from,
            observed_to=observed_to,
            min_confidence=min_confidence,
            province=province,
            kabupaten=kabupaten,
            kecamatan=kecamatan,
            bbox=None,
        )
        query = f"""
            SELECT observed_at::date AS observed_date,
                   satellite,
                   count(*)::int AS total
            FROM {table}
        """
        if where:
            query += " WHERE " + " AND ".join(where)
        query += """
            GROUP BY observed_date, satellite
            ORDER BY observed_date, satellite;
        """

        grouped: dict[str, dict[str, int]] = {}
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                for observed_date, satellite, count in cursor.fetchall():
                    date_key = observed_date.isoformat()
                    satellite_counts = grouped.setdefault(date_key, {})
                    satellite_counts[satellite] = count

        items = [
            TrendItem(
                date=date_key,
                total=sum(satellite_counts.values()),
                satellites=satellite_counts,
            )
            for date_key, satellite_counts in sorted(grouped.items())
        ]
        return HotspotTrendResponse(items=items)

    def runs(
        self,
        *,
        satellite: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[IngestionRunResponse]:
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id::text,
                           satellite,
                           status,
                           started_at,
                           finished_at,
                           source_path,
                           message
                    FROM ingestion_runs
                    WHERE (%s::text IS NULL OR satellite = %s)
                      AND (%s::text IS NULL OR status = %s)
                    ORDER BY started_at DESC
                    LIMIT %s;
                    """,
                    (satellite, satellite, status, status, min(max(limit, 1), 200)),
                )
                return [
                    IngestionRunResponse(
                        id=row[0],
                        satellite=row[1],
                        status=row[2],
                        started_at=row[3],
                        finished_at=row[4],
                        source_path=row[5],
                        message=row[6],
                    )
                    for row in cursor.fetchall()
                ]

    def source_files(
        self,
        *,
        satellite: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SourceFileResponse]:
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT satellite, path, scene_id, observed_at, status, processed_at, last_error
                    FROM source_files
                    WHERE (%s::text IS NULL OR satellite = %s)
                      AND (%s::text IS NULL OR status = %s)
                    ORDER BY COALESCE(processed_at, first_seen_at) DESC
                    LIMIT %s;
                    """,
                    (satellite, satellite, status, status, min(max(limit, 1), 200)),
                )
                return [
                    SourceFileResponse(
                        satellite=row[0],
                        path=row[1],
                        scene_id=row[2],
                        observed_at=row[3],
                        status=row[4],
                        processed_at=row[5],
                        last_error=row[6],
                    )
                    for row in cursor.fetchall()
                ]

    def locations(
        self,
        *,
        province: str | None = None,
        kabupaten: str | None = None,
    ) -> LocationOptionsResponse:
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH provinces AS (
                        SELECT provinsi AS name FROM hotspot_pixel WHERE provinsi IS NOT NULL
                        UNION
                        SELECT provinsi AS name FROM hotspot_cluster WHERE provinsi IS NOT NULL
                        UNION
                        SELECT wa AS name FROM prov_ar WHERE wa IS NOT NULL
                    )
                    SELECT DISTINCT name
                    FROM provinces
                    ORDER BY name;
                    """
                )
                provinces = [row[0] for row in cursor.fetchall()]
                cursor.execute(
                    """
                    WITH kabupaten AS (
                        SELECT provinsi, kabupaten FROM hotspot_pixel
                        WHERE kabupaten IS NOT NULL
                        UNION
                        SELECT provinsi, kabupaten FROM hotspot_cluster
                        WHERE kabupaten IS NOT NULL
                        UNION
                        SELECT prov_ar.wa AS provinsi, kab_kota_ar.wa AS kabupaten
                        FROM kab_kota_ar
                        LEFT JOIN prov_ar ON prov_ar.gid = kab_kota_ar.prov_id
                        WHERE kab_kota_ar.wa IS NOT NULL
                    )
                    SELECT DISTINCT kabupaten
                    FROM kabupaten
                    WHERE (%s::text IS NULL OR provinsi ILIKE %s)
                    ORDER BY kabupaten;
                    """,
                    (province, province),
                )
                kabupaten_options = [row[0] for row in cursor.fetchall()]
                cursor.execute(
                    """
                    WITH kecamatan AS (
                        SELECT provinsi, kabupaten, kecamatan FROM hotspot_pixel
                        WHERE kecamatan IS NOT NULL
                        UNION
                        SELECT provinsi, kabupaten, kecamatan FROM hotspot_cluster
                        WHERE kecamatan IS NOT NULL
                        UNION
                        SELECT prov_ar.wa AS provinsi,
                               kab_kota_ar.wa AS kabupaten,
                               kec_ar.wa AS kecamatan
                        FROM kec_ar
                        LEFT JOIN prov_ar ON prov_ar.gid = kec_ar.prov_id
                        LEFT JOIN kab_kota_ar ON kab_kota_ar.gid = kec_ar.kab_id
                        WHERE kec_ar.wa IS NOT NULL
                    )
                    SELECT DISTINCT kecamatan
                    FROM kecamatan
                    WHERE (%s::text IS NULL OR provinsi ILIKE %s)
                      AND (%s::text IS NULL OR kabupaten ILIKE %s)
                    ORDER BY kecamatan;
                    """,
                    (province, province, kabupaten, kabupaten),
                )
                kecamatan = [row[0] for row in cursor.fetchall()]
        return LocationOptionsResponse(
            provinces=provinces,
            kabupaten=kabupaten_options,
            kecamatan=kecamatan,
        )

    def _clustered_hotspot_features(
        self,
        *,
        satellites: Sequence[str],
        observed_from: datetime | None,
        observed_to: datetime | None,
        min_confidence: int | None,
        province: str | None,
        kabupaten: str | None,
        kecamatan: str | None,
        bbox: tuple[float, float, float, float] | None,
        limit: int | None,
        cluster_projection: ClusteringProjection,
    ) -> list[dict[str, Any]]:
        rows = self._filtered_pixel_rows(
            satellites=satellites,
            observed_from=observed_from,
            observed_to=observed_to,
            min_confidence=min_confidence,
            province=province,
            kabupaten=kabupaten,
            kecamatan=kecamatan,
            bbox=bbox,
        )
        grouped: dict[tuple[str, datetime, str, str], list[HotspotDetection]] = defaultdict(list)
        for row in rows:
            detection = _detection_from_pixel_row(row)
            grouped[
                (
                    detection.satellite,
                    detection.observed_at,
                    detection.scene_id,
                    str(detection.source_file),
                )
            ].append(detection)

        features: list[dict[str, Any]] = []
        for detections in grouped.values():
            settings = _SATELLITE_CLUSTER_SETTINGS.get(detections[0].satellite)
            if settings is None:
                continue
            clusters = cluster_detections(
                detections,
                resolution_meters=settings.resolution_meters,
                neighbor_multiplier=settings.neighbor_multiplier,
                projection=cluster_projection,
            )
            features.extend(
                _cluster_feature(cluster, cluster_projection=cluster_projection)
                for cluster in clusters
            )

        features.sort(
            key=lambda feature: (
                str(feature["properties"].get("observed_at") or ""),
                str(feature["properties"].get("satellite") or ""),
                str(feature["id"]),
            ),
            reverse=True,
        )
        if limit is None:
            return features
        return features[: min(max(limit, 1), 5000)]

    def _filtered_pixel_rows(
        self,
        *,
        satellites: Sequence[str],
        observed_from: datetime | None,
        observed_to: datetime | None,
        min_confidence: int | None,
        province: str | None,
        kabupaten: str | None,
        kecamatan: str | None,
        bbox: tuple[float, float, float, float] | None,
    ):
        query = """
            SELECT
                hid,
                satellite,
                ST_Y(coordinate::geometry) AS latitude,
                ST_X(coordinate::geometry) AS longitude,
                conf_lvl,
                provinsi,
                kabupaten,
                kecamatan,
                radius,
                source_station,
                observed_at,
                source_file,
                scene_id
            FROM hotspot_pixel
        """
        where, params = _hotspot_filters(
            satellites=satellites,
            observed_from=observed_from,
            observed_to=observed_to,
            min_confidence=min_confidence,
            province=province,
            kabupaten=kabupaten,
            kecamatan=kecamatan,
            bbox=bbox,
        )
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY observed_at DESC, hid DESC;"
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()


def _hotspot_filters(
    *,
    satellites: Sequence[str],
    observed_from: datetime | None,
    observed_to: datetime | None,
    min_confidence: int | None,
    province: str | None,
    kabupaten: str | None,
    kecamatan: str | None,
    bbox: tuple[float, float, float, float] | None,
) -> tuple[list[str], list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if satellites:
        where.append("satellite = ANY(%s)")
        params.append(list(satellites))
    if observed_from:
        where.append("observed_at >= %s")
        params.append(observed_from)
    if observed_to:
        where.append("observed_at <= %s")
        params.append(observed_to)
    if min_confidence is not None:
        where.append("conf_lvl >= %s")
        params.append(min_confidence)
    for column, value in (
        ("provinsi", province),
        ("kabupaten", kabupaten),
        ("kecamatan", kecamatan),
    ):
        if value:
            where.append(f"{column} ILIKE %s")
            params.append(value)
    if bbox:
        west, south, east, north = bbox
        where.append("coordinate::geometry && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
        params.extend([west, south, east, north])
    return where, params


def _hotspot_feature(*, kind: HotspotKind, id_column: str, row) -> dict[str, Any]:
    (
        identifier,
        satellite,
        latitude,
        longitude,
        confidence,
        province,
        kabupaten,
        kecamatan,
        radius,
        source_station,
        observed_at,
        source_file,
        scene_id,
    ) = row
    return {
        "type": "Feature",
        "id": f"{kind}-{identifier}",
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        "properties": {
            id_column: identifier,
            "kind": kind,
            "satellite": satellite,
            "confidence": confidence,
            "province": province,
            "kabupaten": kabupaten,
            "kecamatan": kecamatan,
            "radius_meters": radius,
            "source_station": source_station,
            "observed_at": observed_at.isoformat() if observed_at else None,
            "source_file": source_file,
            "scene_id": scene_id,
        },
    }


def _detection_from_pixel_row(row) -> HotspotDetection:
    (
        _identifier,
        satellite,
        latitude,
        longitude,
        confidence,
        province,
        kabupaten,
        kecamatan,
        _radius,
        source_station,
        observed_at,
        source_file,
        scene_id,
    ) = row
    location = (
        AdminLocation(kecamatan=kecamatan, kabupaten=kabupaten, provinsi=province)
        if province and kabupaten and kecamatan
        else None
    )
    return HotspotDetection(
        latitude=latitude,
        longitude=longitude,
        confidence=confidence,
        observed_at=observed_at,
        satellite=satellite,
        source_file=Path(source_file or ""),
        scene_id=scene_id or "",
        source_station=source_station or "",
        location=location,
    )


def _cluster_feature(cluster, *, cluster_projection: ClusteringProjection) -> dict[str, Any]:
    detection = cluster.detections[0]
    location = detection.location
    return {
        "type": "Feature",
        "id": (
            f"cluster-{cluster_projection}-{detection.satellite}-"
            f"{detection.observed_at.isoformat()}-{cluster.latitude:.6f}-{cluster.longitude:.6f}"
        ),
        "geometry": {"type": "Point", "coordinates": [cluster.longitude, cluster.latitude]},
        "properties": {
            "kind": "cluster",
            "satellite": detection.satellite,
            "confidence": cluster.confidence,
            "province": location.provinsi if location else None,
            "kabupaten": location.kabupaten if location else None,
            "kecamatan": location.kecamatan if location else None,
            "radius_meters": cluster.radius_meters,
            "source_station": detection.source_station,
            "observed_at": detection.observed_at.isoformat(),
            "source_file": str(detection.source_file),
            "scene_id": detection.scene_id,
            "cluster_projection": cluster_projection,
            "pixel_count": len(cluster.detections),
        },
    }


def _group_cluster_statistics(
    features: Sequence[dict[str, Any]],
    level: Literal["province", "kabupaten", "kecamatan", "satellite"],
) -> dict[str, dict[str, int]]:
    grouped: dict[str, dict[str, int]] = {}
    label_key = {
        "province": "province",
        "kabupaten": "kabupaten",
        "kecamatan": "kecamatan",
        "satellite": "satellite",
    }[level]
    for feature in features:
        properties = feature["properties"]
        satellite = str(properties.get("satellite") or "Unknown")
        label = str(properties.get(label_key) or "Unknown")
        satellite_counts = grouped.setdefault(label, {})
        satellite_counts[satellite] = satellite_counts.get(satellite, 0) + 1
    return grouped
