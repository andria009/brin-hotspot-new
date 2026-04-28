from datetime import datetime

from fastapi.testclient import TestClient

from brin_hotspot.api.app import create_app, get_repository
from brin_hotspot.api.schemas import (
    IngestionRunResponse,
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


def test_api_exposes_read_only_hotspot_endpoints():
    repository = FakeRepository()
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    assert client.get("/api/v1/health").json()["status"] == "ok"

    summary = client.get("/api/v1/summary").json()
    assert summary["satellites"][0]["satellite"] == "snpp"
    assert summary["satellites"][0]["pixels"] == 3

    hotspots = client.get("/api/v1/hotspots?kind=cluster&satellite=snpp").json()
    assert hotspots["type"] == "FeatureCollection"
    assert hotspots["total"] == 2501
    assert hotspots["features"][0]["geometry"]["coordinates"] == [120.5, -2.5]

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
        },
    )

    assert response.status_code == 200
    assert repository.hotspot_kwargs["observed_from"].isoformat() == "2026-04-24T00:00:00"
    assert repository.hotspot_kwargs["observed_to"].isoformat() == "2026-04-24T23:59:59"
    assert repository.hotspot_kwargs["province"] == "Riau"
    assert repository.hotspot_kwargs["kecamatan"] == "Menteng"
