export type HotspotKind = "cluster" | "pixel";

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
  // Actual filtered count in the API, which can be larger than features.length
  // because map payloads are limited for browser performance.
  total?: number;
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
