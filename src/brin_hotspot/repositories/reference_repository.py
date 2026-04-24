from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import psycopg

from brin_hotspot.config import DatabaseSettings

ReferenceDataset = Literal["province", "kabupaten", "kecamatan", "anomaly"]


@dataclass(frozen=True)
class ReferenceFeature:
    gid: int
    name: str
    geometry: dict[str, Any]
    prov_id: int | None = None
    kab_id: int | None = None


class ReferenceRepository:
    def __init__(self, database: DatabaseSettings):
        self._database = database

    def import_features(self, dataset: ReferenceDataset, features: list[ReferenceFeature]) -> int:
        with psycopg.connect(self._database.dsn, connect_timeout=5) as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    for feature in features:
                        _insert_feature(cursor, dataset, feature)
        return len(features)


def load_geojson_features(
    path: Path,
    *,
    id_field: str,
    name_field: str,
    prov_id_field: str | None = None,
    kab_id_field: str | None = None,
) -> list[ReferenceFeature]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"{path} must contain a GeoJSON FeatureCollection")

    features = []
    for index, feature in enumerate(payload.get("features", []), start=1):
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry")
        if geometry is None:
            continue

        gid = int(properties.get(id_field) or index)
        name = str(properties[name_field]).strip()
        prov_id = _optional_int(properties.get(prov_id_field)) if prov_id_field else None
        kab_id = _optional_int(properties.get(kab_id_field)) if kab_id_field else None
        features.append(
            ReferenceFeature(
                gid=gid,
                name=name,
                geometry=geometry,
                prov_id=prov_id,
                kab_id=kab_id,
            )
        )

    return features


def _insert_feature(
    cursor: psycopg.Cursor,
    dataset: ReferenceDataset,
    feature: ReferenceFeature,
) -> None:
    geometry = json.dumps(feature.geometry)
    if dataset == "province":
        cursor.execute(
            """
            INSERT INTO prov_ar (gid, wa, geom)
            VALUES (%s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
            ON CONFLICT (gid)
            DO UPDATE SET wa = EXCLUDED.wa, geom = EXCLUDED.geom;
            """,
            (feature.gid, feature.name, geometry),
        )
        return

    if dataset == "kabupaten":
        cursor.execute(
            """
            INSERT INTO kab_kota_ar (gid, wa, prov_id, geom)
            VALUES (%s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
            ON CONFLICT (gid)
            DO UPDATE SET wa = EXCLUDED.wa, prov_id = EXCLUDED.prov_id, geom = EXCLUDED.geom;
            """,
            (feature.gid, feature.name, feature.prov_id, geometry),
        )
        return

    if dataset == "kecamatan":
        cursor.execute(
            """
            INSERT INTO kec_ar (gid, wa, prov_id, kab_id, geom)
            VALUES (%s, %s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
            ON CONFLICT (gid)
            DO UPDATE SET
                wa = EXCLUDED.wa,
                prov_id = EXCLUDED.prov_id,
                kab_id = EXCLUDED.kab_id,
                geom = EXCLUDED.geom;
            """,
            (feature.gid, feature.name, feature.prov_id, feature.kab_id, geometry),
        )
        return

    if dataset == "anomaly":
        cursor.execute(
            """
            INSERT INTO persistent_anomalies_buffer_500m (gid, name, geom)
            VALUES (%s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
            ON CONFLICT (gid)
            DO UPDATE SET name = EXCLUDED.name, geom = EXCLUDED.geom;
            """,
            (feature.gid, feature.name, geometry),
        )
        return

    raise ValueError(f"Unsupported reference dataset: {dataset}")


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)

