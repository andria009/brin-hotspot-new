import {
  mockHotspots,
  mockLocations,
  mockRuns,
  mockSources,
  mockStatistics,
  mockSummary,
  mockTrend
} from "./mockData";
import type {
  HotspotCollection,
  HotspotKind,
  HotspotStatistics,
  HotspotTrend,
  IngestionRun,
  LocationOptions,
  OperationalSummary,
  SourceFile
} from "./types";

// In production Nginx proxies /api/v1 to the API container. Local Vite
// development can override this with VITE_HOTSPOT_API_BASE.
const API_BASE = import.meta.env.VITE_HOTSPOT_API_BASE ?? "/api/v1";

export type HotspotFilters = {
  kind: HotspotKind;
  satellites: string[];
  minConfidence: number;
  observedFrom: string;
  observedTo: string;
  province: string;
  kabupaten: string;
  kecamatan: string;
};

export async function getSummary(): Promise<OperationalSummary> {
  return getJson("/summary", mockSummary);
}

export async function getHotspots(filters: HotspotFilters): Promise<HotspotCollection> {
  // Avoid an unnecessary API call when the UI state intentionally hides all
  // satellites. The rest of the dashboard can then render an empty map cleanly.
  if (filters.satellites.length === 0) {
    return { type: "FeatureCollection", total: 0, features: [] };
  }
  const params = new URLSearchParams({
    kind: filters.kind,
    min_confidence: String(filters.minConfidence),
    limit: "2000"
  });
  filters.satellites.forEach((satellite) => params.append("satellite", satellite));
  appendIfPresent(params, "observed_from", toApiDateTime(filters.observedFrom));
  appendIfPresent(params, "observed_to", toApiDateTime(filters.observedTo, true));
  return getJson(`/hotspots?${params.toString()}`, mockHotspots);
}

export async function getStatistics(filters: HotspotFilters): Promise<HotspotStatistics> {
  // Keep the chart title/grouping stable even when there is no selected
  // satellite data to fetch.
  if (filters.satellites.length === 0) {
    return { level: statisticLevel(filters), items: [] };
  }
  const params = hotspotParams(filters);
  appendIfPresent(params, "province", filters.province);
  appendIfPresent(params, "kabupaten", filters.kabupaten);
  appendIfPresent(params, "kecamatan", filters.kecamatan);
  params.set("limit", "20");
  return getJson(`/statistics?${params.toString()}`, mockStatistics);
}

export async function getTrend(filters: HotspotFilters): Promise<HotspotTrend> {
  if (filters.satellites.length === 0) {
    return { items: [] };
  }
  const params = hotspotParams(filters);
  appendIfPresent(params, "province", filters.province);
  appendIfPresent(params, "kabupaten", filters.kabupaten);
  appendIfPresent(params, "kecamatan", filters.kecamatan);
  params.delete("limit");
  return getJson(`/trend?${params.toString()}`, mockTrend);
}

export async function getRuns(): Promise<IngestionRun[]> {
  return getJson("/runs?limit=200", mockRuns);
}

function hotspotParams(filters: HotspotFilters) {
  const params = new URLSearchParams({
    kind: filters.kind,
    min_confidence: String(filters.minConfidence),
    limit: "2000"
  });
  filters.satellites.forEach((satellite) => params.append("satellite", satellite));
  appendIfPresent(params, "observed_from", toApiDateTime(filters.observedFrom));
  appendIfPresent(params, "observed_to", toApiDateTime(filters.observedTo, true));
  return params;
}

export async function getSources(): Promise<SourceFile[]> {
  return getJson("/source-files?limit=200", mockSources);
}

export async function getLocations(province = "", kabupaten = ""): Promise<LocationOptions> {
  const params = new URLSearchParams();
  appendIfPresent(params, "province", province);
  appendIfPresent(params, "kabupaten", kabupaten);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return getJson(`/locations${suffix}`, mockLocations);
}

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`);
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    return (await response.json()) as T;
  } catch {
    // Mock fallback keeps UI development and demos usable before the database is
    // populated or when only the frontend dev server is running.
    return fallback;
  }
}

function appendIfPresent(params: URLSearchParams, key: string, value: string) {
  const trimmed = value.trim();
  if (trimmed) {
    params.append(key, trimmed);
  }
}

function toApiDateTime(value: string, endOfDay = false) {
  if (!value) {
    return "";
  }
  // The UI uses date-only controls, while the API expects datetimes for
  // inclusive filtering.
  if (value.length === 10) {
    return `${value}T${endOfDay ? "23:59:59" : "00:00:00"}`;
  }
  return value.length === 16 ? `${value}:00` : value;
}

function statisticLevel(filters: HotspotFilters) {
  // Mirrors the backend grouping rules used by /statistics.
  if (filters.kecamatan) {
    return "satellite";
  }
  if (filters.kabupaten) {
    return "kecamatan";
  }
  if (filters.province) {
    return "kabupaten";
  }
  return "province";
}
