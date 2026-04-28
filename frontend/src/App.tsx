import {
  Activity,
  BarChart3,
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
import {
  getHotspots,
  getLocations,
  getRuns,
  getSources,
  getStatistics,
  getSummary,
  getTrend
} from "./api";
import hotspotLogo from "./assets/hotspot-logo.png";
import type {
  HotspotCollection,
  HotspotStatistics,
  HotspotTrend,
  HotspotKind,
  IngestionRun,
  LocationOptions,
  OperationalSummary,
  SourceFile
} from "./types";

const SATELLITES = ["snpp", "noaa20", "aqua", "terra", "landsat8"];
const SATELLITE_COLORS: Record<string, string> = {
  snpp: "#b7192b",
  noaa20: "#e76f2c",
  aqua: "#2f80ed",
  terra: "#287c56",
  landsat8: "#6f4dbf"
};
const CONFIDENCE_VALUES = Array.from({ length: 10 }, (_, index) => index);
type Basemap = "street" | "satellite";

export default function App() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const mapNodeRef = useRef<HTMLDivElement | null>(null);
  const defaultDateInitializedRef = useRef(false);
  const [summary, setSummary] = useState<OperationalSummary | null>(null);
  const [hotspots, setHotspots] = useState<HotspotCollection | null>(null);
  const [statistics, setStatistics] = useState<HotspotStatistics | null>(null);
  const [trend, setTrend] = useState<HotspotTrend | null>(null);
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
  const [rightRailOpen, setRightRailOpen] = useState(false);
  const [bottomRailOpen, setBottomRailOpen] = useState(false);
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
          "circle-color": confidenceColorExpression(),
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
    const filters = {
      kind,
      satellites,
      minConfidence,
      observedFrom,
      observedTo,
      province,
      kabupaten,
      kecamatan
    };
    const [summaryData, hotspotData, statisticData, trendData, runData, sourceData] = await Promise.all([
      getSummary(),
      getHotspots(filters),
      getStatistics(filters),
      getTrend(filters),
      getRuns(),
      getSources()
    ]);
    setSummary(summaryData);
    if (!defaultDateInitializedRef.current && !observedFrom && !observedTo) {
      const latestDate = latestAvailableDate(summaryData);
      if (latestDate) {
        defaultDateInitializedRef.current = true;
        setObservedFrom(latestDate);
        setObservedTo(latestDate);
      }
    }
    setHotspots(hotspotData);
    setStatistics(statisticData);
    setTrend(trendData);
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
            <span className="range-label-header">
              Minimum confidence <strong>{minConfidence}</strong>
            </span>
            <input min="0" max="9" value={minConfidence} onChange={(event) => setMinConfidence(Number(event.target.value))} type="range" />
            <span className="confidence-scale" aria-label="Confidence color scale">
              {CONFIDENCE_VALUES.map((value) => (
                <span className="confidence-scale-item" key={value}>
                  <span
                    className={`confidence-dot ${value < minConfidence ? "muted" : ""}`}
                    style={{ backgroundColor: confidenceColor(value) }}
                    aria-hidden="true"
                  />
                </span>
              ))}
            </span>
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
          <button onClick={() => setBottomRailOpen((open) => !open)}><BarChart3 size={16} /> Statistics</button>
          <button onClick={() => void refresh()}><RefreshCw size={16} /> Refresh</button>
          <button onClick={exportGeoJson}><Download size={16} /> GeoJSON</button>
        </div>
        <div ref={mapNodeRef} className="map" />
        {selected && <FeatureInspector feature={selected} onClose={() => setSelected(null)} />}
        {bottomRailOpen && (
          <section className="bottom-rail">
            <div className="statistics-grid">
              <StatisticsPanel
                kind={kind}
                statistics={statistics}
                satellites={satellites}
                province={province}
                kabupaten={kabupaten}
                kecamatan={kecamatan}
              />
              <TrendPanel kind={kind} trend={trend} satellites={satellites} />
            </div>
          </section>
        )}
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

function confidenceColor(confidence: number) {
  const stops = [
    { value: 0, color: [255, 255, 255] },
    { value: 6, color: [244, 211, 94] },
    { value: 8, color: [242, 142, 43] },
    { value: 9, color: [215, 25, 32] }
  ];
  const clamped = Math.max(0, Math.min(9, confidence));
  const upperIndex = stops.findIndex((stop) => clamped <= stop.value);
  const upper = stops[Math.max(upperIndex, 1)];
  const lower = stops[Math.max(upperIndex - 1, 0)];
  const span = upper.value - lower.value || 1;
  const ratio = (clamped - lower.value) / span;
  const rgb = lower.color.map((channel, index) =>
    Math.round(channel + (upper.color[index] - channel) * ratio)
  );
  return `rgb(${rgb.join(", ")})`;
}

function confidenceColorExpression(): maplibregl.ExpressionSpecification {
  return [
    "interpolate",
    ["linear"],
    ["get", "confidence"],
    0,
    "#ffffff",
    6,
    "#f4d35e",
    8,
    "#f28e2b",
    9,
    "#d71920"
  ];
}

function hotspotColorExpression(
  province: string,
  kabupaten: string,
  kecamatan: string
): maplibregl.ExpressionSpecification {
  const confidenceColor = confidenceColorExpression();
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

function StatisticsPanel({
  kind,
  statistics,
  satellites,
  province,
  kabupaten,
  kecamatan
}: {
  kind: HotspotKind;
  statistics: HotspotStatistics | null;
  satellites: string[];
  province: string;
  kabupaten: string;
  kecamatan: string;
}) {
  const items = statistics?.items ?? [];
  const maxTotal = Math.max(...items.map((item) => item.total), 0);
  return (
    <section className="panel statistics-panel">
      <div className="panel-title">
        <BarChart3 size={16} />
        <span>Statistics</span>
      </div>
      <div className="chart-context">
        <strong>{statisticsTitle(statistics?.level, province, kabupaten, kecamatan)}</strong>
        <span>{kind}s by selected satellites</span>
      </div>
      <div className="chart-legend">
        {satellites.map((satellite) => (
          <span key={satellite}>
            <i style={{ background: satelliteColor(satellite) }} />
            {satellite.toUpperCase()}
          </span>
        ))}
      </div>
      <div className="stacked-chart">
        {items.length === 0 && <div className="empty-chart">No matching hotspots</div>}
        {items.map((item) => (
          <div className="chart-row" key={item.label}>
            <div className="chart-row-label">
              <span>{item.label}</span>
              <strong>{formatCount(item.total)}</strong>
            </div>
            <div className="chart-track">
              <div className="chart-stack" style={{ width: `${barWidth(item.total, maxTotal)}%` }}>
                {satellites.map((satellite) => {
                  const value = item.satellites[satellite] ?? 0;
                  if (value <= 0) {
                    return null;
                  }
                  return (
                    <span
                      key={satellite}
                      title={`${satellite.toUpperCase()}: ${formatCount(value)}`}
                      style={{
                        background: satelliteColor(satellite),
                        width: `${(value / item.total) * 100}%`
                      }}
                    />
                  );
                })}
              </div>
            </div>
            <div className="chart-values">
              {satellites
                .filter((satellite) => (item.satellites[satellite] ?? 0) > 0)
                .map((satellite) => (
                  <span key={satellite}>
                    {satellite.toUpperCase()} {formatCount(item.satellites[satellite])}
                  </span>
                ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function TrendPanel({
  kind,
  trend,
  satellites
}: {
  kind: HotspotKind;
  trend: HotspotTrend | null;
  satellites: string[];
}) {
  const items = trend?.items ?? [];
  const series = [
    ...satellites.map((satellite) => ({
      key: satellite,
      label: satellite.toUpperCase(),
      color: satelliteColor(satellite),
      values: items.map((item) => item.satellites[satellite] ?? 0)
    })),
    {
      key: "total",
      label: "TOTAL",
      color: "#142333",
      values: items.map((item) => item.total)
    }
  ];
  const maxValue = Math.max(...series.flatMap((item) => item.values), 0);
  return (
    <section className="panel trend-panel">
      <div className="panel-title">
        <Activity size={16} />
        <span>Daily Trend</span>
      </div>
      <div className="chart-context">
        <strong>{kind}s per day</strong>
        <span>selected satellites and total</span>
      </div>
      <div className="chart-legend">
        {series.map((item) => (
          <span key={item.key}>
            <i style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
      {items.length === 0 ? (
        <div className="empty-chart">No matching hotspots</div>
      ) : (
        <>
          <svg className="line-chart" viewBox="0 0 640 220" role="img" aria-label="Daily hotspot trend">
            <line className="axis-line" x1="42" y1="174" x2="610" y2="174" />
            <line className="axis-line" x1="42" y1="24" x2="42" y2="174" />
            {[0.25, 0.5, 0.75, 1].map((tick) => (
              <line
                className="grid-line"
                key={tick}
                x1="42"
                x2="610"
                y1={174 - tick * 150}
                y2={174 - tick * 150}
              />
            ))}
            {series.map((item) => (
              <polyline
                fill="none"
                key={item.key}
                points={linePoints(item.values, maxValue)}
                stroke={item.color}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={item.key === "total" ? 3 : 2}
              />
            ))}
            {items.map((item, index) => (
              <text className="axis-label" key={item.date} x={xPosition(index, items.length)} y="198">
                {formatTrendDate(item.date)}
              </text>
            ))}
            <text className="axis-value" x="8" y="30">{formatCount(maxValue)}</text>
            <text className="axis-value" x="8" y="178">0</text>
          </svg>
          <div className="trend-values">
            {items.map((item) => (
              <span key={item.date}>
                {formatTrendDate(item.date)} {formatCount(item.total)}
              </span>
            ))}
          </div>
        </>
      )}
    </section>
  );
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

function statisticsTitle(
  level: HotspotStatistics["level"] | undefined,
  province: string,
  kabupaten: string,
  kecamatan: string
) {
  if (level === "satellite") {
    return `Hotspots in ${kecamatan}`;
  }
  if (level === "kecamatan") {
    return `Kecamatan in ${kabupaten}`;
  }
  if (level === "kabupaten") {
    return `Kota/kabupaten in ${province}`;
  }
  return "Hotspots per provinsi";
}

function barWidth(total: number, maxTotal: number) {
  if (maxTotal <= 0) {
    return 0;
  }
  return Math.max((total / maxTotal) * 100, 3);
}

function satelliteColor(satellite: string) {
  return SATELLITE_COLORS[satellite] ?? "#627184";
}

function linePoints(values: number[], maxValue: number) {
  if (values.length === 0) {
    return "";
  }
  return values
    .map((value, index) => `${xPosition(index, values.length)},${yPosition(value, maxValue)}`)
    .join(" ");
}

function xPosition(index: number, count: number) {
  if (count <= 1) {
    return 326;
  }
  return 42 + (index / (count - 1)) * 568;
}

function yPosition(value: number, maxValue: number) {
  if (maxValue <= 0) {
    return 174;
  }
  return 174 - (value / maxValue) * 150;
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

function formatTrendDate(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short"
  }).format(new Date(`${value}T00:00:00`));
}

function latestAvailableDate(summary: OperationalSummary) {
  return summary.satellites
    .map((item) => item.latest_observed_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1)
    ?.slice(0, 10);
}

function toDateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
