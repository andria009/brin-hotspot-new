import {
  Activity,
  Database,
  Download,
  Flame,
  Layers,
  Map as MapIcon,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Satellite,
  Search
} from "lucide-react";
import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { getHotspots, getLocations, getRuns, getSources, getSummary } from "./api";
import hotspotLogo from "./assets/hotspot-logo.png";
import type {
  HotspotCollection,
  HotspotKind,
  IngestionRun,
  LocationOptions,
  OperationalSummary,
  SourceFile
} from "./types";

const SATELLITES = ["snpp", "noaa20", "aqua", "terra", "landsat8"];
type Basemap = "street" | "satellite";

export default function App() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const mapNodeRef = useRef<HTMLDivElement | null>(null);
  const [summary, setSummary] = useState<OperationalSummary | null>(null);
  const [hotspots, setHotspots] = useState<HotspotCollection | null>(null);
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [sources, setSources] = useState<SourceFile[]>([]);
  const [kind, setKind] = useState<HotspotKind>("cluster");
  const [satellites, setSatellites] = useState<string[]>(["snpp", "noaa20", "aqua"]);
  const [minConfidence, setMinConfidence] = useState(7);
  const [observedFrom, setObservedFrom] = useState("");
  const [observedTo, setObservedTo] = useState("");
  const [province, setProvince] = useState("");
  const [kabupaten, setKabupaten] = useState("");
  const [kecamatan, setKecamatan] = useState("");
  const [locations, setLocations] = useState<LocationOptions>({
    provinces: [],
    kabupaten: [],
    kecamatan: []
  });
  const [selected, setSelected] = useState<GeoJSON.Feature | null>(null);
  const [rightRailOpen, setRightRailOpen] = useState(true);
  const [basemap, setBasemap] = useState<Basemap>("street");

  const totals = useMemo(() => {
    const satellitesSummary = summary?.satellites ?? [];
    return {
      clusters: satellitesSummary.reduce((sum, item) => sum + item.clusters, 0),
      pixels: satellitesSummary.reduce((sum, item) => sum + item.pixels, 0),
      enriched: satellitesSummary.reduce((sum, item) => sum + item.enriched_pixels, 0),
      latest: satellitesSummary
        .map((item) => item.latest_observed_at)
        .filter(Boolean)
        .sort()
        .at(-1)
    };
  }, [summary]);
  const latestRunsBySatellite = useMemo(() => latestRunPerSatellite(runs), [runs]);
  const latestSourcesBySatellite = useMemo(() => latestSourcesPerSatellite(sources, 2), [sources]);
  const visibleCount = hotspots?.total ?? hotspots?.features.length ?? 0;

  useEffect(() => {
    if (!mapNodeRef.current || mapRef.current) {
      return;
    }
    mapRef.current = new maplibregl.Map({
      container: mapNodeRef.current,
      center: [118, -2.5],
      zoom: 4.3,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "OpenStreetMap"
          },
          esriWorldImagery: {
            type: "raster",
            tiles: [
              "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ],
            tileSize: 256,
            attribution: "Esri World Imagery"
          }
        },
        layers: [
          { id: "osm", type: "raster", source: "osm" },
          {
            id: "esri-world-imagery",
            type: "raster",
            source: "esriWorldImagery",
            layout: { visibility: "none" }
          }
        ]
      }
    });
    mapRef.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    mapRef.current.on("load", () => {
      mapRef.current?.addSource("hotspots", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      mapRef.current?.addLayer({
        id: "hotspot-points",
        type: "circle",
        source: "hotspots",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "confidence"], 7, 3, 9, 6.5],
          "circle-color": [
            "match",
            ["get", "confidence"],
            9,
            "#d71920",
            8,
            "#f28e2b",
            "#f4d35e"
          ],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.9
        }
      });
      mapRef.current?.on("click", "hotspot-points", (event) => {
        setSelected(event.features?.[0] ?? null);
      });
      mapRef.current?.on("mouseenter", "hotspot-points", () => {
        mapRef.current!.getCanvas().style.cursor = "pointer";
      });
      mapRef.current?.on("mouseleave", "hotspot-points", () => {
        mapRef.current!.getCanvas().style.cursor = "";
      });
    });
    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    void refresh();
  }, [
    kind,
    satellites,
    minConfidence,
    observedFrom,
    observedTo,
    province,
    kabupaten,
    kecamatan
  ]);

  useEffect(() => {
    void refreshLocations(province, kabupaten);
  }, [province, kabupaten]);

  useEffect(() => {
    const source = mapRef.current?.getSource("hotspots") as maplibregl.GeoJSONSource | undefined;
    if (source && hotspots) {
      source.setData(hotspots);
    }
  }, [hotspots]);

  useEffect(() => {
    updateMapRegionHighlight();
  }, [province, kecamatan]);

  useEffect(() => {
    updateBasemap();
  }, [basemap]);

  async function refresh() {
    const [summaryData, hotspotData, runData, sourceData] = await Promise.all([
      getSummary(),
      getHotspots({
        kind,
        satellites,
        minConfidence,
        observedFrom,
        observedTo,
        province,
        kabupaten,
        kecamatan
      }),
      getRuns(),
      getSources()
    ]);
    setSummary(summaryData);
    setHotspots(hotspotData);
    setRuns(runData);
    setSources(sourceData);
  }

  async function refreshLocations(selectedProvince: string, selectedKabupaten: string) {
    setLocations(await getLocations(selectedProvince, selectedKabupaten));
  }

  function toggleSatellite(satellite: string) {
    setSatellites((current) =>
      current.includes(satellite)
        ? current.filter((item) => item !== satellite)
        : [...current, satellite]
    );
  }

  function updateProvince(value: string) {
    setProvince(value);
    setKabupaten("");
    setKecamatan("");
  }

  function updateKabupaten(value: string) {
    setKabupaten(value);
    setKecamatan("");
  }

  function applyDatePreset(days: number) {
    const toDate = new Date();
    const fromDate = new Date(toDate);
    fromDate.setDate(toDate.getDate() - (days - 1));
    setObservedFrom(toDateInputValue(fromDate));
    setObservedTo(toDateInputValue(toDate));
  }

  function updateBasemap() {
    const map = mapRef.current;
    if (!map?.getLayer("osm") || !map.getLayer("esri-world-imagery")) {
      return;
    }
    map.setLayoutProperty("osm", "visibility", basemap === "street" ? "visible" : "none");
    map.setLayoutProperty(
      "esri-world-imagery",
      "visibility",
      basemap === "satellite" ? "visible" : "none"
    );
  }

  function updateMapRegionHighlight() {
    const map = mapRef.current;
    if (!map?.getLayer("hotspot-points")) {
      return;
    }
    map.setPaintProperty(
      "hotspot-points",
      "circle-color",
      hotspotColorExpression(province, kabupaten, kecamatan)
    );
    map.setPaintProperty(
      "hotspot-points",
      "circle-opacity",
      hotspotOpacityExpression(province, kabupaten, kecamatan)
    );
  }

  function exportGeoJson() {
    const blob = new Blob([JSON.stringify(hotspots, null, 2)], { type: "application/geo+json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `brin-hotspots-${kind}.geojson`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className={`app-shell ${rightRailOpen ? "" : "rail-collapsed"}`}>
      <aside className="sidebar">
        <header className="brand">
          <img className="brand-logo" src={hotspotLogo} alt="BRIN Hotspot Monitoring System" />
          <div>
            <p>BRIN Fire Hotspot</p>
            <span>Indonesia active fire monitoring</span>
          </div>
        </header>

        <section className="panel metrics">
          <Metric icon={<Layers size={18} />} label="Clusters" value={totals.clusters} />
          <Metric icon={<Flame size={18} />} label="Pixels" value={totals.pixels} />
          <Metric
            className="metric-wide"
            icon={<Activity size={18} />}
            label="Latest"
            value={formatShort(totals.latest)}
          />
        </section>

        <section className="panel controls">
          <div className="panel-title">
            <Search size={16} />
            <span>Filters</span>
          </div>
          <div className="segmented">
            <button className={kind === "cluster" ? "active" : ""} onClick={() => setKind("cluster")}>Cluster</button>
            <button className={kind === "pixel" ? "active" : ""} onClick={() => setKind("pixel")}>Pixel</button>
          </div>
          <label className="range-label">
            Minimum confidence <strong>{minConfidence}</strong>
            <input min="0" max="9" value={minConfidence} onChange={(event) => setMinConfidence(Number(event.target.value))} type="range" />
          </label>
          <div className="datetime-grid">
            <label>
              From date
              <input
                type="date"
                value={observedFrom}
                onChange={(event) => setObservedFrom(event.target.value)}
              />
            </label>
            <label>
              To date
              <input
                type="date"
                value={observedTo}
                onChange={(event) => setObservedTo(event.target.value)}
              />
            </label>
          </div>
          <div className="date-preset-grid">
            <button onClick={() => applyDatePreset(2)}>Last 24 hours</button>
            <button onClick={() => applyDatePreset(7)}>Last 7 days</button>
          </div>
          <label className="text-filter">
            Provinsi
            <input
              className={!province ? "unselected" : ""}
              list="province-options"
              value={province}
              onChange={(event) => updateProvince(event.target.value)}
              placeholder="All provinces"
            />
            <datalist id="province-options">
              {locations.provinces.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
          </label>
          <label className="text-filter">
            Kota/Kabupaten
            <input
              className={!kabupaten ? "unselected" : ""}
              disabled={!province}
              list="kabupaten-options"
              value={kabupaten}
              onChange={(event) => updateKabupaten(event.target.value)}
              placeholder={province ? "All kota/kabupaten in selected province" : "Select provinsi first"}
            />
            <datalist id="kabupaten-options">
              {locations.kabupaten.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
          </label>
          <label className="text-filter">
            Kecamatan
            <input
              className={!kecamatan ? "unselected" : ""}
              disabled={!kabupaten}
              list="kecamatan-options"
              value={kecamatan}
              onChange={(event) => setKecamatan(event.target.value)}
              placeholder={kabupaten ? "All kecamatan in selected kota/kabupaten" : "Select kota/kabupaten first"}
            />
            <datalist id="kecamatan-options">
              {locations.kecamatan.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
          </label>
          <div className="satellite-grid">
            {SATELLITES.map((satellite) => (
              <button
                key={satellite}
                className={satellites.includes(satellite) ? "selected" : ""}
                onClick={() => toggleSatellite(satellite)}
              >
                <Satellite size={15} />
                {satellite.toUpperCase()}
              </button>
            ))}
          </div>
        </section>

      </aside>

      <section className="map-area">
        <div className="map-toolbar">
          <div>
            <strong>{formatCount(visibleCount)}</strong>
            <span> visible {kind}s</span>
          </div>
          <div className="basemap-switch" aria-label="Basemap">
            <MapIcon size={16} />
            <button className={basemap === "street" ? "active" : ""} onClick={() => setBasemap("street")}>
              Street
            </button>
            <button className={basemap === "satellite" ? "active" : ""} onClick={() => setBasemap("satellite")}>
              Satellite
            </button>
          </div>
          <button onClick={() => setRightRailOpen((open) => !open)}>
            {rightRailOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
            Details
          </button>
          <button onClick={() => void refresh()}><RefreshCw size={16} /> Refresh</button>
          <button onClick={exportGeoJson}><Download size={16} /> GeoJSON</button>
        </div>
        <div ref={mapNodeRef} className="map" />
        {selected && <FeatureInspector feature={selected} onClose={() => setSelected(null)} />}
      </section>

      {rightRailOpen && (
        <aside className="right-rail">
          <section className="panel status-panel">
            <div className="panel-title">
              <Layers size={16} />
              <span>Status</span>
            </div>
            {(summary?.source_statuses ?? []).map((status) => (
              <div className="status-row" key={`${status.satellite}-${status.status}`}>
                <span>{status.satellite.toUpperCase()} · {status.status}</span>
                <strong>{status.count}</strong>
              </div>
            ))}
          </section>
          <section className="panel list-panel">
            <div className="panel-title">
              <Activity size={16} />
              <span>Recent Runs</span>
            </div>
            {latestRunsBySatellite.map((run) => (
              <Row
                key={run.id}
                title={`${run.satellite.toUpperCase()} ${run.status}`}
                meta={formatDate(run.started_at)}
              />
            ))}
          </section>
          <section className="panel">
            <div className="panel-title">
              <Database size={16} />
              <span>Source Files</span>
            </div>
            {latestSourcesBySatellite.map(([satellite, satelliteSources]) => (
              <div className="satellite-group" key={satellite}>
                <div className="group-title">{satellite.toUpperCase()}</div>
                {satelliteSources.map((source) => (
                  <Row
                    key={`${source.satellite}-${source.path}`}
                    title={source.status}
                    meta={source.path.split("/").at(-1) ?? source.path}
                  />
                ))}
              </div>
            ))}
          </section>
        </aside>
      )}
    </main>
  );
}

function latestRunPerSatellite(runs: IngestionRun[]) {
  const latest = new Map<string, IngestionRun>();
  for (const run of runs) {
    const current = latest.get(run.satellite);
    if (!current || new Date(run.started_at) > new Date(current.started_at)) {
      latest.set(run.satellite, run);
    }
  }
  return Array.from(latest.values()).sort((a, b) => a.satellite.localeCompare(b.satellite));
}

function latestSourcesPerSatellite(sources: SourceFile[], limit: number) {
  const grouped = new Map<string, SourceFile[]>();
  for (const source of sources) {
    const items = grouped.get(source.satellite) ?? [];
    items.push(source);
    grouped.set(source.satellite, items);
  }
  return Array.from(grouped.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([satellite, items]) => [
      satellite,
      items
        .sort((a, b) => sourceTime(b).getTime() - sourceTime(a).getTime())
        .slice(0, limit)
    ] as const);
}

function sourceTime(source: SourceFile) {
  return new Date(source.processed_at ?? source.observed_at ?? 0);
}

function hotspotColorExpression(
  province: string,
  kabupaten: string,
  kecamatan: string
): maplibregl.ExpressionSpecification {
  const confidenceColor: maplibregl.ExpressionSpecification = [
    "match",
    ["get", "confidence"],
    9,
    "#d71920",
    8,
    "#f28e2b",
    "#f4d35e"
  ];
  const regionMatch = regionMatchExpression(province, kabupaten, kecamatan);
  if (!regionMatch) {
    return confidenceColor;
  }
  return ["case", regionMatch, confidenceColor, "#9aa6b5"];
}

function hotspotOpacityExpression(
  province: string,
  kabupaten: string,
  kecamatan: string
): maplibregl.ExpressionSpecification {
  const regionMatch = regionMatchExpression(province, kabupaten, kecamatan);
  if (!regionMatch) {
    return ["literal", 0.9];
  }
  return ["case", regionMatch, 0.9, 0.32];
}

function regionMatchExpression(
  province: string,
  kabupaten: string,
  kecamatan: string
): maplibregl.ExpressionSpecification | null {
  if (kecamatan) {
    return ["==", ["get", "kecamatan"], kecamatan];
  }
  if (kabupaten) {
    return ["==", ["get", "kabupaten"], kabupaten];
  }
  if (province) {
    return ["==", ["get", "province"], province];
  }
  return null;
}

function Metric({
  className = "",
  icon,
  label,
  value
}: {
  className?: string;
  icon: React.ReactNode;
  label: string;
  value: number | string | undefined;
}) {
  return (
    <div className={`metric ${className}`.trim()}>
      {icon}
      <span>{label}</span>
      <strong>{value ?? "-"}</strong>
    </div>
  );
}

function Row({ title, meta }: { title: string; meta: string }) {
  return (
    <div className="data-row">
      <strong>{title}</strong>
      <span>{meta}</span>
    </div>
  );
}

function FeatureInspector({ feature, onClose }: { feature: GeoJSON.Feature; onClose: () => void }) {
  const props = feature.properties ?? {};
  return (
    <div className="inspector">
      <button onClick={onClose} aria-label="Close">×</button>
      <h2>{String(props.satellite ?? "").toUpperCase()} hotspot</h2>
      <dl>
        <dt>Confidence</dt><dd>{String(props.confidence ?? "-")}</dd>
        <dt>Observed</dt><dd>{formatDate(String(props.observed_at ?? ""))}</dd>
        <dt>Province</dt><dd>{String(props.province ?? "-")}</dd>
        <dt>Kabupaten</dt><dd>{String(props.kabupaten ?? "-")}</dd>
        <dt>Kecamatan</dt><dd>{String(props.kecamatan ?? "-")}</dd>
        <dt>Scene</dt><dd>{String(props.scene_id ?? "-")}</dd>
      </dl>
    </div>
  );
}

function formatDate(value?: string | null) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatShort(value?: string | null) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat("id-ID", {
    year: "numeric",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatCount(value: number) {
  return new Intl.NumberFormat("id-ID").format(value);
}

function toDateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
