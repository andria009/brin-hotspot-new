from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4


@dataclass(frozen=True)
class AdminLocation:
    kecamatan: str
    kabupaten: str
    provinsi: str


@dataclass(frozen=True)
class HotspotDetection:
    latitude: float
    longitude: float
    confidence: int
    observed_at: datetime
    satellite: str
    source_file: Path
    scene_id: str
    source_station: str
    location: AdminLocation | None = None

    def with_location(self, location: AdminLocation) -> HotspotDetection:
        return HotspotDetection(
            latitude=self.latitude,
            longitude=self.longitude,
            confidence=self.confidence,
            observed_at=self.observed_at,
            satellite=self.satellite,
            source_file=self.source_file,
            scene_id=self.scene_id,
            source_station=self.source_station,
            location=location,
        )


@dataclass(frozen=True)
class HotspotCluster:
    latitude: float
    longitude: float
    confidence: int
    radius_meters: int
    detections: tuple[HotspotDetection, ...]


@dataclass(frozen=True)
class IngestionSummary:
    run_id: UUID = field(default_factory=uuid4)
    satellite: str = ""
    source_files: tuple[Path, ...] = ()
    skipped_files: tuple[Path, ...] = ()
    parsed_count: int = 0
    enriched_count: int = 0
    filtered_count: int = 0
    cluster_count: int = 0
    persisted_cluster_count: int = 0
    persisted_pixel_count: int = 0
    output_files: tuple[Path, ...] = ()
