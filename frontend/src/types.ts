export type HotspotKind = "cluster" | "pixel";
export type ClusterProjection = "latitude_adjusted" | "epsg4087";

// These types mirror the FastAPI response schemas. Keep them aligned with
// src/brin_hotspot/api/schemas.py when adding or renaming API fields.

export type SatelliteSummary = {
  satellite: string;
  clusters: number;
  pixels: number;
  enriched_pixels: number;
  latest_observed_at: string | null;
};

export type SourceStatusSummary = {
  satellite: string;
  status: string;
  count: number;
};

export type OperationalSummary = {
  generated_at: string;
  satellites: SatelliteSummary[];
  source_statuses: SourceStatusSummary[];
};

export type HotspotFeature = GeoJSON.Feature<
  GeoJSON.Point,
  {
    kind: HotspotKind;
    satellite: string;
    confidence: number;
    province: string | null;
    kabupaten: string | null;
    kecamatan: string | null;
    radius_meters: number | null;
    source_station: string | null;
    observed_at: string | null;
    source_file: string | null;
    scene_id: string | null;
  }
>;

export type HotspotCollection = GeoJSON.FeatureCollection<
  GeoJSON.Point,
  HotspotFeature["properties"]
> & {
  // Actual filtered count in the API. It differs from features.length only when
  // callers explicitly request a limited map payload.
  total?: number;
};

export type SceneResponse = {
  status: "ready" | "pending" | "unavailable";
  request_key: string;
  satellite: string;
  platform: string;
  dataset: {
    id: string;
    title: string;
    file_name: string;
    acquisition_start: string | null;
    bbox: [number, number, number, number] | null;
  } | null;
  asset_url: string | null;
  assets: {
    id: string;
    role: string;
    title: string;
    media_type: string;
    bbox: [number, number, number, number] | null;
    download_url: string;
  }[];
  bundle_url: string | null;
  overlay_url: string | null;
  overlay_bbox: [number, number, number, number] | null;
  expires_in_seconds: number | null;
  job: { id: string; status: string } | null;
  retry_after_seconds: number | null;
  reason: string | null;
  can_acquire: boolean;
};

export type IngestionRun = {
  id: string;
  satellite: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  source_path: string | null;
  message: string | null;
};

export type SourceFile = {
  satellite: string;
  path: string;
  scene_id: string | null;
  observed_at: string | null;
  status: string;
  processed_at: string | null;
  last_error: string | null;
};

export type LocationOptions = {
  provinces: string[];
  kabupaten: string[];
  kecamatan: string[];
};

export type LocationBounds = {
  bbox: [number, number, number, number] | null;
};

export type StatisticLevel = "province" | "kabupaten" | "kecamatan" | "satellite";

export type StatisticItem = {
  label: string;
  total: number;
  satellites: Record<string, number>;
};

export type HotspotStatistics = {
  level: StatisticLevel;
  items: StatisticItem[];
};

export type TrendItem = {
  date: string;
  total: number;
  satellites: Record<string, number>;
};

export type HotspotTrend = {
  items: TrendItem[];
};
