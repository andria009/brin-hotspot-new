from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
    SceneRequest,
    SceneResponse,
    SourceFileResponse,
)
from brin_hotspot.auth import Identity, access_management_request, decode_access_token
from brin_hotspot.config import Settings, get_settings
from brin_hotspot.geocatalog import GeoCatalogClient, GeoCatalogError


class AccessRequestCreate(BaseModel):
    requested_role: Literal["explorer", "mage", "sage"]


class AccessRequestApproval(BaseModel):
    role: Literal["explorer", "mage", "sage", "god"]
    token_balance: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=1000)


class AccessRequestRejection(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class WalletAdjustment(BaseModel):
    token_delta: int
    reason: str = Field(min_length=1, max_length=1000)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title="BRIN Hotspot API",
        version="0.1.0",
        description="Read-only API for BRIN fire hotspot visualization and data access.",
    )
    app.state.settings = resolved_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", response_model=ApiHealth)
    def health() -> ApiHealth:
        return ApiHealth()

    @app.get("/api/v1/access/me")
    async def access_me(request: Request):
        token, _ = request_identity(request)
        return await access_management_request(
            resolved_settings, token, "GET", "/me"
        )

    @app.post("/api/v1/access/request", status_code=201)
    async def request_access(payload: AccessRequestCreate, request: Request):
        token, _ = request_identity(request)
        return await access_management_request(
            resolved_settings,
            token,
            "POST",
            "/access-requests",
            json_body={
                "application": "hotspot-new",
                "requested_role": payload.requested_role,
            },
        )

    @app.get("/api/v1/access/admin/requests")
    async def access_requests(
        request: Request,
        status: Literal["pending", "approved", "rejected"] = "pending",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        token, identity = request_identity(request)
        require_application_role(identity, "god")
        return await access_management_request(
            resolved_settings,
            token,
            "GET",
            "/admin/access-requests",
            params={"application": "hotspot-new", "status": status, "limit": limit},
        )

    @app.post("/api/v1/access/admin/requests/{request_id}/approve")
    async def approve_access(
        request_id: str,
        payload: AccessRequestApproval,
        request: Request,
    ):
        token, identity = request_identity(request)
        require_application_role(identity, "god")
        return await access_management_request(
            resolved_settings,
            token,
            "POST",
            f"/admin/access-requests/{request_id}/approve",
            json_body=payload.model_dump(exclude_none=True),
        )

    @app.get("/api/v1/access/admin/memberships")
    async def access_memberships(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        token, identity = request_identity(request)
        require_application_role(identity, "god")
        return await access_management_request(
            resolved_settings,
            token,
            "GET",
            "/admin/memberships",
            params={"application": "hotspot-new", "limit": limit},
        )

    @app.post("/api/v1/access/admin/requests/{request_id}/reject")
    async def reject_access(
        request_id: str,
        payload: AccessRequestRejection,
        request: Request,
    ):
        token, identity = request_identity(request)
        require_application_role(identity, "god")
        return await access_management_request(
            resolved_settings,
            token,
            "POST",
            f"/admin/access-requests/{request_id}/reject",
            json_body=payload.model_dump(),
        )

    @app.get("/api/v1/access/wallets")
    async def access_wallets(request: Request):
        token, _ = request_identity(request)
        return await access_management_request(
            resolved_settings, token, "GET", "/wallets"
        )

    @app.post("/api/v1/access/admin/wallets/{principal_id}/adjust")
    async def adjust_access_wallet(
        principal_id: str,
        payload: WalletAdjustment,
        request: Request,
    ):
        token, identity = request_identity(request)
        require_application_role(identity, "god")
        return await access_management_request(
            resolved_settings,
            token,
            "POST",
            f"/admin/wallets/hotspot-new/{principal_id}/adjust",
            json_body=payload.model_dump(),
        )

    @app.get("/api/v1/access/admin/audit")
    async def access_audit(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        token, identity = request_identity(request)
        require_application_role(identity, "god")
        return await access_management_request(
            resolved_settings,
            token,
            "GET",
            "/admin/audit",
            params={"application": "hotspot-new", "limit": limit},
        )

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

    @app.post("/api/v1/scenes/resolve", response_model=SceneResponse)
    def resolve_scene(
        payload: SceneRequest,
        request: Request,
        client: Annotated[GeoCatalogClient, Depends(get_geocatalog_client)],
    ) -> dict:
        if resolved_settings.oidc_enabled:
            user_token, identity = request_identity(request)
            require_application_role(identity, "mage")
        else:
            user_token = None
        try:
            return client.request_scene(payload.model_dump(mode="json"), user_token=user_token)
        except GeoCatalogError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return app


def request_identity(request: Request) -> tuple[str, Identity]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Keycloak login is required")
    settings: Settings = request.app.state.settings
    return token, decode_access_token(token, settings)


def require_application_role(identity: Identity, minimum_role: str) -> None:
    roles = ("explorer", "mage", "sage", "god")
    if identity.role not in roles or roles.index(identity.role) < roles.index(minimum_role):
        raise HTTPException(
            status_code=403,
            detail=f"{minimum_role} role is required for hotspot-new",
        )


def get_repository() -> ReadOnlyHotspotRepository:
    settings = get_settings()
    return ReadOnlyHotspotRepository(settings.hotspot_database)


def get_geocatalog_client() -> GeoCatalogClient:
    return GeoCatalogClient(get_settings())


app = create_app()
