import type {
  HotspotCollection,
  HotspotStatistics,
  HotspotTrend,
  IngestionRun,
  LocationOptions,
  OperationalSummary,
  SourceFile
} from "./types";

export const mockSummary: OperationalSummary = {
  generated_at: new Date().toISOString(),
  satellites: [
    { satellite: "snpp", clusters: 128, pixels: 376, enriched_pixels: 352, latest_observed_at: "2026-04-27T05:40:00" },
    { satellite: "noaa20", clusters: 94, pixels: 291, enriched_pixels: 280, latest_observed_at: "2026-04-27T06:12:00" },
    { satellite: "aqua", clusters: 37, pixels: 104, enriched_pixels: 96, latest_observed_at: "2026-04-27T04:55:00" }
  ],
  source_statuses: [
    { satellite: "snpp", status: "completed", count: 88 },
    { satellite: "noaa20", status: "completed", count: 75 },
    { satellite: "aqua", status: "completed", count: 41 },
    { satellite: "aqua", status: "failed", count: 2 }
  ]
};

export const mockHotspots: HotspotCollection = {
  type: "FeatureCollection",
  total: 5,
  features: [
    feature("cluster-1", 101.45, 0.51, "snpp", 9, "RIAU", "PELALAWAN", "PANGKALAN KERINCI"),
    feature("cluster-2", 113.92, -2.22, "noaa20", 8, "KALIMANTAN TENGAH", "PULANG PISAU", "SEBANGAU KUALA"),
    feature("cluster-3", 140.71, -6.12, "aqua", 7, "PAPUA SELATAN", "MERAUKE", "NAUKENJERAI"),
    feature("cluster-4", 116.88, -0.54, "snpp", 9, "KALIMANTAN TIMUR", "KUTAI KARTANEGARA", "MUARA KAMAN"),
    feature("cluster-5", 105.54, -3.02, "noaa20", 8, "SUMATERA SELATAN", "OGAN KOMERING ILIR", "TULUNG SELAPAN")
  ]
};

export const mockStatistics: HotspotStatistics = {
  level: "province",
  items: [
    { label: "RIAU", total: 42, satellites: { snpp: 19, noaa20: 15, aqua: 8 } },
    { label: "KALIMANTAN TENGAH", total: 31, satellites: { snpp: 12, noaa20: 13, aqua: 6 } },
    { label: "PAPUA SELATAN", total: 18, satellites: { snpp: 5, noaa20: 4, aqua: 9 } }
  ]
};

export const mockTrend: HotspotTrend = {
  items: [
    { date: "2026-04-23", total: 16, satellites: { snpp: 7, noaa20: 6, aqua: 3 } },
    { date: "2026-04-24", total: 22, satellites: { snpp: 10, noaa20: 8, aqua: 4 } },
    { date: "2026-04-25", total: 18, satellites: { snpp: 6, noaa20: 7, aqua: 5 } },
    { date: "2026-04-26", total: 29, satellites: { snpp: 13, noaa20: 9, aqua: 7 } },
    { date: "2026-04-27", total: 37, satellites: { snpp: 17, noaa20: 12, aqua: 8 } }
  ]
};

export const mockRuns: IngestionRun[] = [
  {
    id: "mock-run-snpp",
    satellite: "snpp",
    status: "completed",
    started_at: "2026-04-27T06:00:00",
    finished_at: "2026-04-27T06:01:14",
    source_path: "/app/data/input/snpp",
    message: null
  },
  {
    id: "mock-run-aqua",
    satellite: "aqua",
    status: "completed",
    started_at: "2026-04-27T05:55:00",
    finished_at: "2026-04-27T05:56:44",
    source_path: "/app/data/output/modis-converted/aqua",
    message: null
  }
];

export const mockSources: SourceFile[] = [
  {
    satellite: "snpp",
    path: "/app/data/input/snpp/2026/04/27/AFIMG_npp_d20260427_t0540000_e0546000.txt",
    scene_id: "SNPP_20260427054000",
    observed_at: "2026-04-27T05:40:00",
    status: "completed",
    processed_at: "2026-04-27T06:01:14",
    last_error: null
  },
  {
    satellite: "aqua",
    path: "/app/data/output/modis-converted/aqua/a1.26117.0455.mod14.hotspots.csv",
    scene_id: "a1.26117.0455.mod14",
    observed_at: "2026-04-27T04:55:00",
    status: "completed",
    processed_at: "2026-04-27T05:56:44",
    last_error: null
  }
];

export const mockLocations: LocationOptions = {
  provinces: [
    "JAKARTA TEST",
    "KALIMANTAN TENGAH",
    "PAPUA SELATAN",
    "RIAU",
    "SULAWESI TEST"
  ],
  kabupaten: [
    "LUWU TEST",
    "OGAN KOMERING ILIR",
    "PELALAWAN",
    "PULANG PISAU"
  ],
  kecamatan: [
    "MENTENG TEST",
    "PANGKALAN KERINCI",
    "SEBANGAU KUALA",
    "WALENRANG TEST"
  ]
};

function feature(
  id: string,
  longitude: number,
  latitude: number,
  satellite: string,
  confidence: number,
  province: string,
  kabupaten: string,
  kecamatan: string
) {
  return {
    type: "Feature" as const,
    id,
    geometry: { type: "Point" as const, coordinates: [longitude, latitude] },
    properties: {
      kind: "cluster" as const,
      satellite,
      confidence,
      province,
      kabupaten,
      kecamatan,
      radius_meters: 1200,
      source_station: "Parepare",
      observed_at: "2026-04-27T05:40:00",
      source_file: null,
      scene_id: id
    }
  };
}
