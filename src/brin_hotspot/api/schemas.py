from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiHealth(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "brin-hotspot-api"


class SatelliteSummary(BaseModel):
    satellite: str
    clusters: int = 0
    pixels: int = 0
    enriched_pixels: int = 0
    latest_observed_at: datetime | None = None


class SourceStatusSummary(BaseModel):
    satellite: str
    status: str
    count: int


class OperationalSummary(BaseModel):
    generated_at: datetime
    satellites: list[SatelliteSummary]
    source_statuses: list[SourceStatusSummary]


class IngestionRunResponse(BaseModel):
    id: str
    satellite: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    source_path: str | None = None
    message: str | None = None


class SourceFileResponse(BaseModel):
    satellite: str
    path: str
    scene_id: str | None = None
    observed_at: datetime | None = None
    status: str
    processed_at: datetime | None = None
    last_error: str | None = None


class LocationOptionsResponse(BaseModel):
    provinces: list[str] = Field(default_factory=list)
    kabupaten: list[str] = Field(default_factory=list)
    kecamatan: list[str] = Field(default_factory=list)


class LocationBoundsResponse(BaseModel):
    bbox: tuple[float, float, float, float] | None = None


class StatisticItem(BaseModel):
    label: str
    total: int
    satellites: dict[str, int] = Field(default_factory=dict)


class HotspotStatisticsResponse(BaseModel):
    level: Literal["province", "kabupaten", "kecamatan", "satellite"]
    items: list[StatisticItem] = Field(default_factory=list)


class TrendItem(BaseModel):
    date: str
    total: int
    satellites: dict[str, int] = Field(default_factory=dict)


class HotspotTrendResponse(BaseModel):
    items: list[TrendItem] = Field(default_factory=list)


class GeoJsonFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    total: int = 0
    features: list[dict[str, Any]] = Field(default_factory=list)


class SceneRequest(BaseModel):
    satellite: str
    observed_at: datetime
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    scene_id: str | None = None
    pixel_size_meters: float = Field(gt=0, le=10_000)


class SceneResponse(BaseModel):
    status: Literal["ready", "pending", "unavailable"]
    request_key: str
    satellite: str
    platform: str
    dataset: dict[str, Any] | None = None
    asset_url: str | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    bundle_url: str | None = None
    overlay_url: str | None = None
    overlay_bbox: list[float] | None = None
    expires_in_seconds: int | None = None
    job: dict[str, Any] | None = None
    retry_after_seconds: int | None = None
    reason: str | None = None
