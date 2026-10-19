from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from brin_hotspot.domain import HotspotCluster, HotspotDetection
from brin_hotspot.repositories.hotspot_repository import HotspotRepository


def test_adjacent_cluster_stores_connected_display_polygon_and_nominal_area():
    statements = []

    class FakeCursor:
        def execute(self, query, params):
            assert query.count("%s") == len(params)
            statements.append(query)

        def fetchone(self):
            return (1,)

    detection = HotspotDetection(
        latitude=-2, longitude=104, confidence=8, observed_at=datetime(2026, 10, 16, 6),
        satellite="snpp", source_file=Path("scene.txt"), scene_id="scene",
        source_station="Parepare",
    )
    neighbor = HotspotDetection(
        latitude=-2, longitude=104.005, confidence=8,
        observed_at=detection.observed_at, satellite="snpp",
        source_file=detection.source_file, scene_id="scene", source_station="Parepare",
    )
    cluster = HotspotCluster(-2, 104.0025, 8, 600, (detection, neighbor))
    HotspotRepository._insert_cluster(FakeCursor(), cluster, cluster_method="adjacent")
    assert "display_geom = ST_Multi(ST_Transform(display.geom, 4326))" in statements[-1]
    assert "footprint_area_m2 = ST_Area(footprint.geom)" in statements[-1]
    assert "ST_Buffer(ST_MakeLine(first_geom, second_geom)" in statements[-1]


def test_adjacent_materialization_replaces_only_selected_satellite_and_dates(monkeypatch):
    statements = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def transaction(self):
            return self

        def cursor(self):
            return self

        def execute(self, query, params):
            statements.append((query, params))

        def fetchall(self):
            return [
                ("snpp", -2.0, 104.0, 8, None, None, None, "Parepare",
                 datetime(2026, 10, 16, 6), "scene.txt", "scene"),
                ("snpp", -2.01, 104.01, 8, None, None, None, "Parepare",
                 datetime(2026, 10, 16, 6), "another.txt", "scene"),
            ]

    monkeypatch.setattr("brin_hotspot.repositories.hotspot_repository.psycopg.connect",
                        lambda *_args, **_kwargs: FakeConnection())
    monkeypatch.setattr("brin_hotspot.repositories.hotspot_repository.cluster_detections",
                        lambda *_args, **_kwargs: [])
    start = datetime(2026, 10, 16)
    end = datetime(2026, 10, 17)

    count = HotspotRepository(SimpleNamespace(dsn="unused")).materialize_cluster_projection(
        cluster_projection="local_utm", cluster_method="adjacent", satellites=("snpp",),
        observed_from=start, observed_to=end,
    )

    assert count == 0
    assert len(statements) == 2
    delete_query, delete_params = statements[1]
    assert "DELETE FROM hotspot_cluster" in delete_query
    assert "satellite = %s" in delete_query
    assert "observed_at = %s" in delete_query
    assert "cluster_projection = %s" in delete_query
    assert "cluster_method = 'adjacent'" in delete_query
    assert delete_params == ("local_utm", "snpp", datetime(2026, 10, 16, 6), "scene")
    assert "satellite = ANY(%s)" in statements[0][0]
    assert statements[0][1] == [["snpp"], start, end]


def test_ingestion_replay_replaces_adjacent_scene_only_when_variant_is_available(monkeypatch):
    operations = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def transaction(self):
            return self

        def cursor(self):
            return self

        def execute(self, query, _params):
            operations.append(query.strip().split()[0])

    monkeypatch.setattr("brin_hotspot.repositories.hotspot_repository.psycopg.connect",
                        lambda *_args, **_kwargs: FakeConnection())
    monkeypatch.setattr(HotspotRepository, "_start_run", staticmethod(lambda *_args: None))
    monkeypatch.setattr(HotspotRepository, "_insert_cluster",
                        staticmethod(lambda *_args, **_kwargs: operations.append("INSERT") or 1))
    monkeypatch.setattr(HotspotRepository, "_insert_pixel",
                        staticmethod(lambda *_args, **_kwargs: None))
    monkeypatch.setattr(HotspotRepository, "_mark_source_file_completed",
                        staticmethod(lambda *_args, **_kwargs: None))
    detection = HotspotDetection(
        latitude=-2, longitude=104, confidence=8, observed_at=datetime(2026, 10, 16, 6),
        satellite="snpp", source_file=Path("scene.txt"), scene_id="scene",
        source_station="Parepare",
    )
    cluster = HotspotCluster(-2, 104, 8, 265, (detection,))
    repository = HotspotRepository(SimpleNamespace(dsn="unused"))
    options = dict(run_id=uuid4(), satellite="snpp", source_files=(detection.source_file,),
                   clusters=[cluster], pixel_radius_meters=188, finish_run=False)

    repository.persist_ingestion(**options, adjacent_clusters=[cluster])
    assert operations == ["DELETE", "INSERT", "INSERT"]

    operations.clear()
    repository.persist_ingestion(**options, adjacent_clusters=None)
    assert operations == ["INSERT"]
