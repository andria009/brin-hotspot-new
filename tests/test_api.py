from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from brin_hotspot.api.app import create_app, get_geocatalog_client, get_repository
from brin_hotspot.api.repository import ReadOnlyHotspotRepository, _hotspot_feature
from brin_hotspot.api.schemas import (
    HotspotStatisticsResponse,
    HotspotTrendResponse,
    IngestionRunResponse,
    LatestObservationResponse,
    LocationOptionsResponse,
    OperationalSummary,
    SatelliteSummary,
    SourceFileResponse,
    SourceStatusSummary,
)


class FakeRepository:
    def __init__(self):
        self.hotspot_kwargs = None

    def summary(self):
        return OperationalSummary(
            generated_at=datetime(2026, 4, 27, 6, 0),
            satellites=[
                SatelliteSummary(
                    satellite="snpp",
                    clusters=2,
                    pixels=3,
                    enriched_pixels=2,
                    latest_observed_at=datetime(2026, 4, 27, 5, 30),
                )
            ],
            source_statuses=[
                SourceStatusSummary(satellite="snpp", status="completed", count=1)
            ],
        )

    def latest_observation(self):
        return LatestObservationResponse(latest_observed_at=datetime(2026, 4, 27, 5, 30))

    def hotspots(self, **kwargs):
        self.hotspot_kwargs = kwargs
        assert kwargs["kind"] == "cluster"
        assert kwargs["satellites"] == ["snpp"]
        return [
            {
                "type": "Feature",
                "id": "cluster-1",
                "geometry": {"type": "Point", "coordinates": [120.5, -2.5]},
                "properties": {
                    "kind": "cluster",
                    "satellite": "snpp",
                    "confidence": 9,
                    "province": "TEST PROVINCE",
                    "kabupaten": None,
                    "kecamatan": None,
                    "radius_meters": 1000,
                    "source_station": "Parepare",
                    "observed_at": "2026-04-27T05:30:00",
                    "source_file": "source.txt",
                    "scene_id": "SNPP_20260427053000",
                },
            }
        ]

    def hotspot_count(self, **kwargs):
        return 2501

    def statistics(self, **kwargs):
        self.statistics_kwargs = kwargs
        return HotspotStatisticsResponse(
            level="kabupaten",
            items=[
                {
                    "label": "PELALAWAN",
                    "total": 12,
                    "satellites": {"snpp": 7, "noaa20": 5},
                }
            ],
        )

    def trend(self, **kwargs):
        self.trend_kwargs = kwargs
        return HotspotTrendResponse(
            items=[
                {
                    "date": "2026-04-27",
                    "total": 10,
                    "satellites": {"snpp": 6, "noaa20": 4},
                }
            ]
        )

    def runs(self, **kwargs):
        return [
            IngestionRunResponse(
                id="run-id",
                satellite="snpp",
                status="completed",
                started_at=datetime(2026, 4, 27, 6, 0),
            )
        ]

    def source_files(self, **kwargs):
        return [
            SourceFileResponse(
                satellite="snpp",
                path="source.txt",
                status="completed",
            )
        ]

    def locations(self, **kwargs):
        return LocationOptionsResponse(
            provinces=["RIAU", "SULAWESI TEST"],
            kabupaten=["LUWU TEST"] if kwargs["province"] else [],
            kecamatan=["WALENRANG TEST"] if kwargs["kabupaten"] else [],
        )

    def location_bounds(self, **kwargs):
        return {"bbox": (100.0, -2.0, 101.0, -1.0)}


def test_adjacent_cluster_method_reaches_repository():
    repository = FakeRepository()
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repository
    response = TestClient(app).get(
        "/api/v1/hotspots?kind=cluster&satellite=snpp&cluster_projection=local_utm"
        "&cluster_method=adjacent"
    )
    assert response.status_code == 200
    assert repository.hotspot_kwargs["cluster_method"] == "adjacent"


def test_adjacent_display_geometry_is_opt_in(monkeypatch):
    repository = FakeRepository()
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)
    assert client.get(
        "/api/v1/hotspots?kind=cluster&satellite=snpp&cluster_method=adjacent&display=true"
    ).status_code == 200
    assert repository.hotspot_kwargs["display"] is True

    statements = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def cursor(self):
            return self

        def execute(self, query, _params):
            statements.append(query)

        def fetchall(self):
            return []

    monkeypatch.setattr("brin_hotspot.api.repository.psycopg.connect",
                        lambda *_args, **_kwargs: FakeConnection())
    database_repository = ReadOnlyHotspotRepository(SimpleNamespace(dsn="unused"))
    database_repository.hotspots(kind="cluster", cluster_method="adjacent", display=True)
    assert "ST_AsGeoJSON(COALESCE(display_geom, footprint_geom))" in statements[-1]
    database_repository.hotspots(kind="cluster", cluster_method="adjacent")
    assert "ST_AsGeoJSON(footprint_geom)" in statements[-1]


def test_adjacent_cluster_feature_includes_geometry_and_footprint_area():
    footprint = (
        '{"type":"MultiPolygon","coordinates":[[[[104,-2],[104.1,-2],'
        '[104.1,-1.9],[104,-1.9],[104,-2]]]]}'
    )
    row = (1, "snpp", -1.95, 104.05, 8, None, None, None, 300, "Parepare",
           datetime(2026, 10, 6), "source.txt", "scene", footprint, 281250.0, 2)
    feature = _hotspot_feature(kind="cluster", id_column="cid", row=row)
    assert feature["geometry"]["type"] == "MultiPolygon"
    assert feature["properties"]["footprint_area_m2"] == 281250.0
    assert feature["properties"]["center_longitude"] == 104.05


def test_api_exposes_read_only_hotspot_endpoints():
    repository = FakeRepository()
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    assert client.get("/api/v1/health").json()["status"] == "ok"

    summary = client.get("/api/v1/summary").json()
    assert summary["satellites"][0]["satellite"] == "snpp"
    assert summary["satellites"][0]["pixels"] == 3

    latest = client.get("/api/v1/latest-observation").json()
    assert latest["latest_observed_at"] == "2026-04-27T05:30:00"

    hotspots = client.get("/api/v1/hotspots?kind=cluster&satellite=snpp").json()
    assert hotspots["type"] == "FeatureCollection"
    assert hotspots["total"] == 2501
    assert hotspots["features"][0]["geometry"]["coordinates"] == [120.5, -2.5]

    count_only = client.get("/api/v1/hotspots?kind=cluster&count_only=true").json()
    assert count_only["total"] == 2501
    assert count_only["features"] == []

    runs = client.get("/api/v1/runs").json()
    assert runs[0]["status"] == "completed"

    sources = client.get("/api/v1/source-files").json()
    assert sources[0]["path"] == "source.txt"

    locations = client.get(
        "/api/v1/locations?province=SULAWESI%20TEST&kabupaten=LUWU%20TEST"
    ).json()
    assert locations["provinces"] == ["RIAU", "SULAWESI TEST"]
    assert locations["kabupaten"] == ["LUWU TEST"]
    assert locations["kecamatan"] == ["WALENRANG TEST"]

    bounds = client.get("/api/v1/location-bounds?province=SULAWESI%20TEST").json()
    assert bounds["bbox"] == [100.0, -2.0, 101.0, -1.0]

    statistics = client.get(
        "/api/v1/statistics?kind=cluster&satellite=snpp&satellite=noaa20&province=RIAU"
    ).json()
    assert statistics["level"] == "kabupaten"
    assert statistics["items"][0]["satellites"]["snpp"] == 7

    searched = client.get(
        "/api/v1/statistics?kind=cluster&province=RIAU&search=PELALAWAN"
    )
    assert searched.status_code == 200
    assert repository.statistics_kwargs["search"] == "PELALAWAN"

    trend = client.get(
        "/api/v1/trend?kind=cluster&satellite=snpp&satellite=noaa20&province=RIAU"
    ).json()
    assert trend["items"][0]["date"] == "2026-04-27"
    assert trend["items"][0]["total"] == 10


def test_hotspots_accepts_time_and_region_filters():
    repository = FakeRepository()
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        "/api/v1/hotspots",
        params={
            "kind": "cluster",
            "satellite": "snpp",
            "observed_from": "2026-04-24T00:00:00",
            "observed_to": "2026-04-24T23:59:59",
            "province": "Riau",
            "kecamatan": "Menteng",
            "bbox": ["90", "-10", "150", "10"],
        },
    )

    assert response.status_code == 200
    assert repository.hotspot_kwargs["observed_from"].isoformat() == "2026-04-24T00:00:00"
    assert repository.hotspot_kwargs["observed_to"].isoformat() == "2026-04-24T23:59:59"
    assert repository.hotspot_kwargs["province"] == "Riau"
    assert repository.hotspot_kwargs["kecamatan"] == "Menteng"
    assert repository.hotspot_kwargs["bbox"] == (90.0, -10.0, 150.0, 10.0)
    assert repository.hotspot_kwargs["limit"] == 100000


def test_trend_counts_confidence_by_day_and_satellite_with_indonesia_filter(monkeypatch):
    class FakeConnection:
        query = ""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def cursor(self):
            return self

        def execute(self, query, _params):
            self.query = query

        def fetchall(self):
            day = datetime(2026, 10, 17).date()
            return [(day, "snpp", 8, 2), (day, "snpp", 9, 1),
                    (day, "noaa20", 8, 3)]

    connection = FakeConnection()
    monkeypatch.setattr("brin_hotspot.api.repository.psycopg.connect",
                        lambda *_args, **_kwargs: connection)
    item = ReadOnlyHotspotRepository(SimpleNamespace(dsn="unused")).trend(
        kind="pixel", satellites=["snpp", "noaa20"]
    ).items[0]

    assert item.total == 6
    assert item.satellites == {"snpp": 3, "noaa20": 3}
    assert item.confidences[8] == 5
    assert item.satellite_confidences["snpp"] == {8: 2, 9: 1}
    assert "ST_Covers(indonesia.geom, coordinate::geometry)" in connection.query


def test_statistics_search_filters_each_administrative_level_before_limit(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def cursor(self):
            return self

        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchall(self):
            return []

    connection = FakeConnection()
    monkeypatch.setattr("brin_hotspot.api.repository.psycopg.connect",
                        lambda *_args, **_kwargs: connection)
    repository = ReadOnlyHotspotRepository(SimpleNamespace(dsn="unused"))
    for filters, column in [({}, "provinsi"), ({"province": "Riau"}, "kabupaten"),
                            ({"province": "Riau", "kabupaten": "Pelalawan"}, "kecamatan")]:
        repository.statistics(kind="pixel", satellites=["snpp"], search="Tualang", **filters)
        assert f"{column}, '')" in connection.query
        assert "ILIKE %s" in connection.query
        assert connection.params[-1] == "%Tualang%"


def test_scene_resolve_proxies_request_to_geocatalog():
    class FakeGeoCatalogClient:
        def request_scene(self, payload, user_token=None):
            assert payload["satellite"] == "snpp"
            assert payload["pixel_size_meters"] == 375
            assert payload["acquire"] is False
            return {
                "status": "ready",
                "request_key": "request-1",
                "satellite": "snpp",
                "platform": "suomi-npp",
                "asset_url": "http://localhost:8090/api/v1/datasets/dataset-1/download?ticket=x",
            }

    app = create_app()
    app.dependency_overrides[get_geocatalog_client] = FakeGeoCatalogClient
    client = TestClient(app)
    response = client.post(
        "/api/v1/scenes/resolve",
        json={
            "satellite": "snpp",
            "observed_at": "2026-04-27T05:30:00",
            "longitude": 120.5,
            "latitude": -2.5,
            "scene_id": "SNPP_20260427053000",
            "pixel_size_meters": 375,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert "ticket=x" in response.json()["asset_url"]


def test_scene_resolve_lets_any_signed_in_role_preview(monkeypatch):
    from brin_hotspot.api import app as app_module
    from brin_hotspot.auth import Identity
    from brin_hotspot.config import Settings

    forwarded = []

    class FakeGeoCatalogClient:
        def request_scene(self, payload, user_token=None):
            forwarded.append(user_token)
            return {"status": "pending", "request_key": "r", "satellite": "noaa20",
                    "platform": "noaa-20", "retry_after_seconds": 15}

    roles = {"explorer-token": "explorer", "no-role-token": None}
    monkeypatch.setattr(
        app_module,
        "decode_access_token",
        lambda token, _settings: Identity(token, "user@example.test", "User", roles[token]),
    )
    app = create_app(Settings(HOTSPOT_OIDC_ENABLED=True))
    app.dependency_overrides[get_geocatalog_client] = FakeGeoCatalogClient
    client = TestClient(app)
    payload = {"satellite": "noaa20", "observed_at": "2026-10-04T18:45:53", "longitude": 110.3,
               "latitude": -2.6, "pixel_size_meters": 375}

    anonymous = client.post("/api/v1/scenes/resolve", json=payload)
    no_role = client.post("/api/v1/scenes/resolve", json=payload,
                          headers={"Authorization": "Bearer no-role-token"})
    explorer = client.post("/api/v1/scenes/resolve", json=payload,
                           headers={"Authorization": "Bearer explorer-token"})

    assert anonymous.status_code == 401
    assert no_role.status_code == 403
    assert explorer.status_code == 200
    assert forwarded == ["explorer-token"]


def test_cors_allows_only_configured_origins():
    from brin_hotspot.config import Settings

    client = TestClient(create_app(Settings(HOTSPOT_CORS_ORIGINS="https://geomimo-hotspot.brin.go.id")))

    allowed = client.get("/api/v1/health", headers={"Origin": "https://geomimo-hotspot.brin.go.id"})
    blocked = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "https://geomimo-hotspot.brin.go.id"
    assert "access-control-allow-origin" not in blocked.headers


def test_public_file_names_hide_server_directories():
    from brin_hotspot.api.repository import public_file_names

    assert public_file_names("/app/data/input/snpp/2021/AFIMG_npp.txt") == "AFIMG_npp.txt"
    assert public_file_names("/app/out/aqua/original,/app/out/aqua/buffer") == "original,buffer"
    assert public_file_names(None) is None
