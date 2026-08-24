from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from brin_hotspot.api.repository import ReadOnlyHotspotRepository
from brin_hotspot.api.schemas import (
    ApiHealth,
    GeoJsonFeatureCollection,
    HotspotStatisticsResponse,
    HotspotTrendResponse,
    IngestionRunResponse,
    LocationBoundsResponse,
    LocationOptionsResponse,
    OperationalSummary,
    SourceFileResponse,
)
from brin_hotspot.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="BRIN Hotspot API",
        version="0.1.0",
        description="Read-only API for BRIN fire hotspot visualization and data access.",
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", response_model=ApiHealth)
    def health() -> ApiHealth:
        return ApiHealth()

    @app.get("/api/v1/summary", response_model=OperationalSummary)
    def summary(repository: Annotated[ReadOnlyHotspotRepository, Depends(get_repository)]):
        return repository.summary()

    @app.get("/api/v1/hotspots", response_model=GeoJsonFeatureCollection)
    def hotspots(
        repository: Annotated[ReadOnlyHotspotRepository, Depends(get_repository)],
        kind: Annotated[Literal["pixel", "cluster"], Query()] = "cluster",
        satellite: Annotated[list[str] | None, Query()] = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        min_confidence: Annotated[int | None, Query(ge=0, le=9)] = None,
        province: str | None = None,
        kabupaten: str | None = None,
        kecamatan: str | None = None,
        bbox: Annotated[
            tuple[float, float, float, float] | None,
            Query(description="Repeated west,south,east,north values."),
        ] = None,
        limit: Annotated[
            int | None,
            Query(
                ge=1,
                le=100000,
                description=(
                    "Optional maximum returned features. "
                    "Omit to return all matching hotspots."
                ),
            ),
        ] = None,
        cluster_projection: Annotated[
            Literal["latitude_adjusted", "epsg4087"],
            Query(),
        ] = "latitude_adjusted",
    ) -> GeoJsonFeatureCollection:
        satellites = satellite or ()
        return GeoJsonFeatureCollection(
            total=repository.hotspot_count(
                kind=kind,
                satellites=satellites,
                observed_from=observed_from,
                observed_to=observed_to,
                min_confidence=min_confidence,
                province=province,
                kabupaten=kabupaten,
                kecamatan=kecamatan,
                bbox=bbox,
                cluster_projection=cluster_projection,
            ),
            features=repository.hotspots(
                kind=kind,
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
        )

    @app.get("/api/v1/statistics", response_model=HotspotStatisticsResponse)
    def statistics(
        repository: Annotated[ReadOnlyHotspotRepository, Depends(get_repository)],
        kind: Annotated[Literal["pixel", "cluster"], Query()] = "cluster",
        satellite: Annotated[list[str] | None, Query()] = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        min_confidence: Annotated[int | None, Query(ge=0, le=9)] = None,
        province: str | None = None,
        kabupaten: str | None = None,
        kecamatan: str | None = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        cluster_projection: Annotated[
            Literal["latitude_adjusted", "epsg4087"],
            Query(),
        ] = "latitude_adjusted",
    ) -> HotspotStatisticsResponse:
        return repository.statistics(
            kind=kind,
            satellites=satellite or (),
            observed_from=observed_from,
            observed_to=observed_to,
            min_confidence=min_confidence,
            province=province,
            kabupaten=kabupaten,
            kecamatan=kecamatan,
            limit=limit,
            cluster_projection=cluster_projection,
        )

    @app.get("/api/v1/trend", response_model=HotspotTrendResponse)
    def trend(
        repository: Annotated[ReadOnlyHotspotRepository, Depends(get_repository)],
        kind: Annotated[Literal["pixel", "cluster"], Query()] = "cluster",
        satellite: Annotated[list[str] | None, Query()] = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        min_confidence: Annotated[int | None, Query(ge=0, le=9)] = None,
        province: str | None = None,
        kabupaten: str | None = None,
        kecamatan: str | None = None,
        cluster_projection: Annotated[
            Literal["latitude_adjusted", "epsg4087"],
            Query(),
        ] = "latitude_adjusted",
    ) -> HotspotTrendResponse:
        return repository.trend(
            kind=kind,
            satellites=satellite or (),
            observed_from=observed_from,
            observed_to=observed_to,
            min_confidence=min_confidence,
            province=province,
            kabupaten=kabupaten,
            kecamatan=kecamatan,
            cluster_projection=cluster_projection,
        )

    @app.get("/api/v1/runs", response_model=list[IngestionRunResponse])
    def runs(
        repository: Annotated[ReadOnlyHotspotRepository, Depends(get_repository)],
        satellite: str | None = None,
        status: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> Sequence[IngestionRunResponse]:
        return repository.runs(satellite=satellite, status=status, limit=limit)

    @app.get("/api/v1/source-files", response_model=list[SourceFileResponse])
    def source_files(
        repository: Annotated[ReadOnlyHotspotRepository, Depends(get_repository)],
        satellite: str | None = None,
        status: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> Sequence[SourceFileResponse]:
        return repository.source_files(satellite=satellite, status=status, limit=limit)

    @app.get("/api/v1/locations", response_model=LocationOptionsResponse)
    def locations(
        repository: Annotated[ReadOnlyHotspotRepository, Depends(get_repository)],
        province: str | None = None,
        kabupaten: str | None = None,
    ) -> LocationOptionsResponse:
        return repository.locations(province=province, kabupaten=kabupaten)

    @app.get("/api/v1/location-bounds", response_model=LocationBoundsResponse)
    def location_bounds(
        repository: Annotated[ReadOnlyHotspotRepository, Depends(get_repository)],
        province: str | None = None,
        kabupaten: str | None = None,
        kecamatan: str | None = None,
    ) -> LocationBoundsResponse:
        return repository.location_bounds(
            province=province,
            kabupaten=kabupaten,
            kecamatan=kecamatan,
        )

    return app


def get_repository() -> ReadOnlyHotspotRepository:
    settings = get_settings()
    return ReadOnlyHotspotRepository(settings.hotspot_database)


app = create_app()
