import { mockHotspots, mockLocations, mockRuns, mockSources, mockSummary } from "./mockData";
import type {
  HotspotCollection,
  HotspotKind,
  IngestionRun,
  LocationOptions,
  OperationalSummary,
  SourceFile
} from "./types";

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

export async function getRuns(): Promise<IngestionRun[]> {
  return getJson("/runs?limit=10", mockRuns);
}

export async function getSources(): Promise<SourceFile[]> {
  return getJson("/source-files?limit=10", mockSources);
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
  if (value.length === 10) {
    return `${value}T${endOfDay ? "23:59:59" : "00:00:00"}`;
  }
  return value.length === 16 ? `${value}:00` : value;
}
