import {
  Activity,
  BarChart3,
  ChevronDown,
  ChevronRight,
  Crosshair,
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
import { type PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  getHotspots,
  getHotspotTotal,
  getLocationBounds,
  getLocations,
  getRuns,
  getSources,
  getStatistics,
  getSummary,
  getTrend,
  type HotspotBbox,
  type HotspotFilters
} from "./api";
import hotspotIcon from "./assets/hotspot-icon.png";
import type {
  ClusterProjection,
  HotspotCollection,
  HotspotFeature,
  HotspotStatistics,
  HotspotTrend,
  HotspotKind,
  IngestionRun,
  LocationOptions,
  OperationalSummary,
  SourceFile
} from "./types";

const SATELLITES = ["snpp", "noaa20", "aqua", "tera", "landsat8"];
const SATELLITE_COLORS: Record<string, string> = {
  snpp: "#b7192b",
  noaa20: "#e76f2c",
  aqua: "#2f80ed",
  tera: "#287c56",
  landsat8: "#6f4dbf"
};
const SATELLITE_PIXEL_RADIUS_METERS: Record<string, number> = {
  snpp: 1125,
  noaa20: 1125,
  aqua: 3000,
  tera: 3000,
  landsat8: 90
};
// The confidence scale is discrete in the source data, but colors are interpolated
// so the map and sidebar legend read as one continuous low-to-high risk ramp.
const CONFIDENCE_VALUES = Array.from({ length: 10 }, (_, index) => index);
const HOTSPOT_FILL_LAYER = "hotspot-footprints";
type Basemap = "street" | "satellite";
type DetailSection = "status" | "runs" | "sources";
type ScreenPoint = { x: number; y: number };
type BboxSelectionState = {
  active: boolean;
  dragging: boolean;
  start: ScreenPoint | null;
  current: ScreenPoint | null;
};

export default function App() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const mapNodeRef = useRef<HTMLDivElement | null>(null);
  const defaultDateInitializedRef = useRef(false);
  const viewportRefreshTimeoutRef = useRef<number | null>(null);
  const latestHotspotRequestRef = useRef(0);
  const filtersRef = useRef<HotspotFilters | null>(null);
  const [summary, setSummary] = useState<OperationalSummary | null>(null);
  const [hotspots, setHotspots] = useState<HotspotCollection | null>(null);
  const [statistics, setStatistics] = useState<HotspotStatistics | null>(null);
  const [trend, setTrend] = useState<HotspotTrend | null>(null);
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [sources, setSources] = useState<SourceFile[]>([]);
  const [kind, setKind] = useState<HotspotKind>("cluster");
  const [clusterProjection, setClusterProjection] = useState<ClusterProjection>("latitude_adjusted");
  const [satellites, setSatellites] = useState<string[]>(["snpp", "noaa20", "aqua", "tera"]);
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [rightRailOpen, setRightRailOpen] = useState(false);
  const [bottomRailOpen, setBottomRailOpen] = useState(false);
  const [detailSections, setDetailSections] = useState<Record<DetailSection, boolean>>({
    status: true,
    runs: true,
    sources: true
  });
  const [basemap, setBasemap] = useState<Basemap>("street");
  const [bboxSelection, setBboxSelection] = useState<BboxSelectionState>({
    active: false,
    dragging: false,
    start: null,
    current: null
  });
  const [currentCounts, setCurrentCounts] = useState({ clusters: 0, pixels: 0 });
  const activeFilters = useMemo<HotspotFilters>(
    () => ({
      kind,
      clusterProjection,
      satellites,
      minConfidence,
      observedFrom,
      observedTo,
      province,
      kabupaten,
      kecamatan
    }),
    [
      kind,
      clusterProjection,
      satellites,
      minConfidence,
      observedFrom,
      observedTo,
      province,
      kabupaten,
      kecamatan
    ]
  );

  // Latest comes from the operational summary; the count cards are refreshed
  // from filtered API totals so they represent the current date/filters.
  const totals = useMemo(() => {
    const satellitesSummary = summary?.satellites ?? [];
    return {
      latest: satellitesSummary
        .map((item) => item.latest_observed_at)
        .filter(Boolean)
        .sort()
        .at(-1)
    };
  }, [summary]);
  const latestRunsBySatellite = useMemo(() => latestRunPerSatellite(runs), [runs]);
  const latestSourcesBySatellite = useMemo(() => latestSourcesPerSatellite(sources, 2), [sources]);
  const sourceStatusRows = useMemo(() => {
    const rows = summary?.source_statuses ?? [];
    return SATELLITES.flatMap((satellite) => {
      const satelliteRows = rows.filter((status) => status.satellite === satellite);
      return satelliteRows.length > 0
        ? satelliteRows
        : [{ satellite, status: "no sources", count: 0 }];
    });
  }, [summary]);
  // The map request is bbox-aware, so this count reflects the current viewport
  // while the metric cards below keep the full filtered totals.
  const visibleCount = hotspots?.total ?? hotspots?.features.length ?? 0;

  useEffect(() => {
    if (!mapNodeRef.current || mapRef.current) {
      return;
    }
    // The map style is defined inline so street and satellite basemaps can be
    // switched by toggling layer visibility without rebuilding the map.
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
      // Hotspots are kept in one GeoJSON source and rendered as square footprint
      // polygons; filters are applied by refetching data, while region selection
      // is a paint update.
      mapRef.current?.addSource("hotspots", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      mapRef.current?.addLayer({
        id: HOTSPOT_FILL_LAYER,
        type: "fill",
        source: "hotspots",
        paint: {
          "fill-color": confidenceColorExpression(),
          "fill-opacity": 0.86
        }
      });
      mapRef.current?.on("click", HOTSPOT_FILL_LAYER, (event) => {
        setSelected(event.features?.[0] ?? null);
      });
      mapRef.current?.on("mouseenter", HOTSPOT_FILL_LAYER, () => {
        mapRef.current!.getCanvas().style.cursor = "pointer";
      });
      mapRef.current?.on("mouseleave", HOTSPOT_FILL_LAYER, () => {
        mapRef.current!.getCanvas().style.cursor = "";
      });
      mapRef.current?.on("moveend", scheduleViewportHotspotRefresh);
      void refreshViewportHotspots();
    });
    return () => {
      if (viewportRefreshTimeoutRef.current) {
        window.clearTimeout(viewportRefreshTimeoutRef.current);
      }
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    void refresh();
  }, [activeFilters]);

  useEffect(() => {
    filtersRef.current = activeFilters;
  }, [activeFilters]);

  useEffect(() => {
    void refreshLocations(province, kabupaten);
  }, [province, kabupaten]);

  useEffect(() => {
    void zoomToSelectedLocation();
  }, [province, kabupaten, kecamatan]);

  useEffect(() => {
    const source = mapRef.current?.getSource("hotspots") as maplibregl.GeoJSONSource | undefined;
    if (source && hotspots) {
      source.setData(hotspotFootprints(hotspots, kind, mapRef.current?.getZoom() ?? 4.3));
    }
  }, [hotspots, kind]);

  useEffect(() => {
    updateMapRegionHighlight();
  }, [province, kabupaten, kecamatan]);

  useEffect(() => {
    updateBasemap();
  }, [basemap]);

  useEffect(() => {
    window.setTimeout(() => mapRef.current?.resize(), 0);
  }, [sidebarCollapsed, rightRailOpen, bottomRailOpen]);

  useEffect(() => {
    if (!bboxSelection.active) {
      return;
    }
    const cancelSelection = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setBboxSelection(inactiveBboxSelection());
      }
    };
    window.addEventListener("keydown", cancelSelection);
    return () => window.removeEventListener("keydown", cancelSelection);
  }, [bboxSelection.active]);

  async function refresh() {
    const filters = activeFilters;
    const bbox = currentMapBbox();
    const hotspotRequestId = ++latestHotspotRequestRef.current;
    const hotspotRequest = shouldFetchHotspotFeatures(filters, bbox)
      ? getHotspots(filters, bbox)
      : Promise.resolve(emptyHotspotCollection());
    const [
      summaryData,
      hotspotData,
      clusterTotal,
      pixelTotal,
      statisticData,
      trendData,
      runData,
      sourceData
    ] = await Promise.all([
      getSummary(),
      hotspotRequest,
      getHotspotTotal(filters, "cluster"),
      getHotspotTotal(filters, "pixel"),
      getStatistics(filters),
      getTrend(filters),
      getRuns(),
      getSources()
    ]);
    setSummary(summaryData);
    // On first load, focus the dashboard on the last day with available data
    // instead of the wall-clock current date, which may not have ingested data.
    if (!defaultDateInitializedRef.current && !observedFrom && !observedTo) {
      const latestDate = latestAvailableDate(summaryData);
      if (latestDate) {
        defaultDateInitializedRef.current = true;
        setObservedFrom(latestDate);
        setObservedTo(latestDate);
      }
    }
    if (hotspotRequestId === latestHotspotRequestRef.current) {
      setHotspots(hotspotData);
    }
    setCurrentCounts({ clusters: clusterTotal, pixels: pixelTotal });
    setStatistics(statisticData);
    setTrend(trendData);
    setRuns(runData);
    setSources(sourceData);
  }

  async function refreshLocations(selectedProvince: string, selectedKabupaten: string) {
    setLocations(await getLocations(selectedProvince, selectedKabupaten));
  }

  async function zoomToSelectedLocation() {
    if (!province && !kabupaten && !kecamatan) {
      return;
    }
    const response = await getLocationBounds(province, kabupaten, kecamatan);
    if (!response.bbox) {
      return;
    }
    fitMapToBbox(response.bbox);
  }

  async function refreshViewportHotspots() {
    const filters = currentFilters();
    const bbox = currentMapBbox();
    const hotspotRequestId = ++latestHotspotRequestRef.current;
    if (!shouldFetchHotspotFeatures(filters, bbox)) {
      setHotspots(emptyHotspotCollection());
      return;
    }
    const hotspotData = await getHotspots(filters, bbox);
    if (hotspotRequestId === latestHotspotRequestRef.current) {
      setHotspots(hotspotData);
    }
  }

  function scheduleViewportHotspotRefresh() {
    if (viewportRefreshTimeoutRef.current) {
      window.clearTimeout(viewportRefreshTimeoutRef.current);
    }
    viewportRefreshTimeoutRef.current = window.setTimeout(() => {
      void refreshViewportHotspots();
    }, 250);
  }

  function currentFilters() {
    return filtersRef.current ?? activeFilters;
  }

  function currentMapBbox(): HotspotBbox | null {
    const bounds = mapRef.current?.getBounds();
    if (!bounds) {
      return null;
    }
    const west = clampLongitude(bounds.getWest());
    const east = clampLongitude(bounds.getEast());
    return [
      Math.min(west, east),
      clampLatitude(bounds.getSouth()),
      Math.max(west, east),
      clampLatitude(bounds.getNorth())
    ];
  }

  function fitMapToBbox([west, south, east, north]: HotspotBbox) {
    const map = mapRef.current;
    if (!map || west === east || south === north) {
      return;
    }
    map.fitBounds(
      [
        [west, south],
        [east, north]
      ],
      {
        duration: 700,
        maxZoom: kecamatan ? 12 : kabupaten ? 10 : 7,
        padding: {
          top: 100,
          bottom: bottomRailOpen ? 260 : 80,
          left: sidebarCollapsed ? 100 : 380,
          right: rightRailOpen ? 420 : 100
        }
      }
    );
  }

  function shouldFetchHotspotFeatures(filters: HotspotFilters, bbox: HotspotBbox | null) {
    if (!bbox) {
      return false;
    }
    return (
      defaultDateInitializedRef.current ||
      Boolean(filters.observedFrom.trim() || filters.observedTo.trim())
    );
  }

  function toggleBboxSelection() {
    setBboxSelection((current) =>
      current.active
        ? inactiveBboxSelection()
        : { active: true, dragging: false, start: null, current: null }
    );
  }

  function startBboxSelection(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) {
      return;
    }
    const point = pointerPoint(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    setBboxSelection({ active: true, dragging: true, start: point, current: point });
  }

  function moveBboxSelection(event: PointerEvent<HTMLDivElement>) {
    setBboxSelection((current) =>
      current.active && current.dragging
        ? { ...current, current: pointerPoint(event) }
        : current
    );
  }

  function finishBboxSelection(event: PointerEvent<HTMLDivElement>) {
    if (
      !bboxSelection.active ||
      !bboxSelection.dragging ||
      !bboxSelection.start ||
      !bboxSelection.current
    ) {
      return;
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const selectedBbox = selectedMapBbox(bboxSelection.start, bboxSelection.current);
    if (!selectedBbox) {
      setBboxSelection({ active: true, dragging: false, start: null, current: null });
      return;
    }
    setBboxSelection(inactiveBboxSelection());
    fitMapToBbox(selectedBbox);
  }

  function selectedMapBbox(start: ScreenPoint, current: ScreenPoint): HotspotBbox | null {
    const map = mapRef.current;
    if (!map) {
      return null;
    }
    const minX = Math.min(start.x, current.x);
    const maxX = Math.max(start.x, current.x);
    const minY = Math.min(start.y, current.y);
    const maxY = Math.max(start.y, current.y);
    if (maxX - minX < 10 || maxY - minY < 10) {
      return null;
    }
    const southwest = map.unproject([minX, maxY]);
    const northeast = map.unproject([maxX, minY]);
    return [
      Math.min(southwest.lng, northeast.lng),
      clampLatitude(Math.min(southwest.lat, northeast.lat)),
      Math.max(southwest.lng, northeast.lng),
      clampLatitude(Math.max(southwest.lat, northeast.lat))
    ];
  }

  function toggleSatellite(satellite: string) {
    setSatellites((current) =>
      current.includes(satellite)
        ? current.filter((item) => item !== satellite)
        : [...current, satellite]
    );
  }

  function toggleDetailSection(section: DetailSection) {
    setDetailSections((current) => ({ ...current, [section]: !current[section] }));
  }

  function updateProvince(value: string) {
    // Downstream administrative selections are only valid within their parent.
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
    if (!map?.getLayer(HOTSPOT_FILL_LAYER)) {
      return;
    }
    map.setPaintProperty(
      HOTSPOT_FILL_LAYER,
      "fill-color",
      hotspotColorExpression(province, kabupaten, kecamatan)
    );
    map.setPaintProperty(
      HOTSPOT_FILL_LAYER,
      "fill-opacity",
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
    <main className={`app-shell ${rightRailOpen ? "" : "rail-collapsed"} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <aside className={`sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
        <button className="brand brand-toggle" onClick={() => setSidebarCollapsed((collapsed) => !collapsed)} title="Toggle sidebar">
          <img className="brand-logo" src={hotspotIcon} alt="BRIN Hotspot Monitoring System" />
          {!sidebarCollapsed ? (
          <div>
            <p>BRIN Fire Hotspot</p>
            <span>Indonesia active fire monitoring</span>
          </div>
          ) : null}
        </button>

        {!sidebarCollapsed ? (
        <>
        <section className="panel metrics">
          <Metric icon={<Layers size={18} />} label="Clusters" value={currentCounts.clusters} />
          <Metric icon={<Flame size={18} />} label="Pixels" value={currentCounts.pixels} />
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
          <div className="control-group">
            <span>Clustering projection</span>
            <div className="segmented projection-switch">
              <button
                className={clusterProjection === "latitude_adjusted" ? "active" : ""}
                onClick={() => setClusterProjection("latitude_adjusted")}
              >
                Latitude-adjusted
              </button>
              <button
                className={clusterProjection === "epsg4087" ? "active" : ""}
                onClick={() => setClusterProjection("epsg4087")}
              >
                EPSG:4087
              </button>
            </div>
          </div>
          <label className="range-label">
            <span className="range-label-header">
              Minimum confidence <strong>{minConfidence}</strong>
            </span>
            <input min="0" max="9" value={minConfidence} onChange={(event) => setMinConfidence(Number(event.target.value))} type="range" />
            {/* Keep this unlabeled: the selected value is already shown above the slider. */}
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
                {satelliteLabel(satellite)}
              </button>
            ))}
          </div>
        </section>
        </>
        ) : null}
      </aside>

      <section className="map-area">
        <div className="map-toolbar">
          <div className="toolbar-count">
            <strong>{formatCount(visibleCount)}</strong>
            <span> visible {kind}s</span>
          </div>
          <div className="basemap-switch" aria-label="Basemap">
            <MapIcon className="segmented-icon" size={16} />
            <button className={basemap === "street" ? "active" : ""} onClick={() => setBasemap("street")}>
              Street
            </button>
            <button className={basemap === "satellite" ? "active" : ""} onClick={() => setBasemap("satellite")}>
              Satellite
            </button>
          </div>
          <button className="toolbar-button" onClick={() => setRightRailOpen((open) => !open)}>
            {rightRailOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
            Details
          </button>
          <button className="toolbar-button" onClick={() => setBottomRailOpen((open) => !open)}><BarChart3 size={16} /> Statistics</button>
          <button
            className={`toolbar-button ${bboxSelection.active ? "active" : ""}`}
            onClick={toggleBboxSelection}
          >
            <Crosshair size={16} /> Bbox
          </button>
          <button className="toolbar-button" onClick={() => void refresh()}><RefreshCw size={16} /> Refresh</button>
          <button className="toolbar-button" onClick={exportGeoJson}><Download size={16} /> GeoJSON</button>
        </div>
        <div ref={mapNodeRef} className="map" />
        {bboxSelection.active && (
          <div
            className="bbox-selection-layer"
            onPointerDown={startBboxSelection}
            onPointerMove={moveBboxSelection}
            onPointerUp={finishBboxSelection}
            onPointerCancel={() => setBboxSelection(inactiveBboxSelection())}
          >
            {bboxSelection.dragging && bboxSelection.start && bboxSelection.current && (
              <div
                className="bbox-selection-box"
                style={selectionBoxStyle(bboxSelection.start, bboxSelection.current)}
              />
            )}
          </div>
        )}
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
            <button className="panel-title collapsible-title" onClick={() => toggleDetailSection("status")}>
              <span><Layers size={16} /> Status</span>
              {detailSections.status ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            </button>
            {detailSections.status ? (
              <div className="collapsible-content">
                {sourceStatusRows.map((status) => (
                  <div className="status-row" key={`${status.satellite}-${status.status}`}>
                    <span>{satelliteLabel(status.satellite)} · {status.status}</span>
                    <strong>{status.count}</strong>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
          <section className="panel list-panel">
            <button className="panel-title collapsible-title" onClick={() => toggleDetailSection("runs")}>
              <span><Activity size={16} /> Recent Runs</span>
              {detailSections.runs ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            </button>
            {detailSections.runs ? (
              <div className="collapsible-content">
                {latestRunsBySatellite.map((run) => (
                  <Row
                    key={run.id}
                    title={`${satelliteLabel(run.satellite)} ${run.status}`}
                    meta={formatDate(run.started_at)}
                  />
                ))}
              </div>
            ) : null}
          </section>
          <section className="panel">
            <button className="panel-title collapsible-title" onClick={() => toggleDetailSection("sources")}>
              <span><Database size={16} /> Source Files</span>
              {detailSections.sources ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            </button>
            {detailSections.sources ? (
              <div className="collapsible-content">
                {latestSourcesBySatellite.map(([satellite, satelliteSources]) => (
                  <div className="satellite-group" key={satellite}>
                    <div className="group-title">{satelliteLabel(satellite)}</div>
                    {satelliteSources.map((source) => (
                      <Row
                        key={`${source.satellite}-${source.path}`}
                        title={source.status}
                        meta={source.path.split("/").at(-1) ?? source.path}
                      />
                    ))}
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        </aside>
      )}
    </main>
  );
}

function latestRunPerSatellite(runs: IngestionRun[]) {
  // The API returns recent runs globally; the right rail needs one latest item
  // per satellite to avoid letting busy satellites hide quieter ones.
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
  // Group source files by satellite so the operator can see recent checkpoint
  // activity across all enabled feeds.
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

function inactiveBboxSelection(): BboxSelectionState {
  return { active: false, dragging: false, start: null, current: null };
}

function pointerPoint(event: PointerEvent<HTMLDivElement>): ScreenPoint {
  const rect = event.currentTarget.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top
  };
}

function selectionBoxStyle(start: ScreenPoint, current: ScreenPoint) {
  const left = Math.min(start.x, current.x);
  const top = Math.min(start.y, current.y);
  return {
    left,
    top,
    width: Math.abs(current.x - start.x),
    height: Math.abs(current.y - start.y)
  };
}

/**
 * Mirrors the MapLibre confidence color expression for React-rendered controls.
 * Stops are intentionally shared by value with confidenceColorExpression().
 */
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

/**
 * MapLibre expression for hotspot confidence colors.
 * The same stop values are used by confidenceColor() for the sidebar scale.
 */
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
  // Keep selected-region hotspots on the confidence ramp and grey out
  // non-selected regions without removing them from spatial context.
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
  // Match the most specific administrative selection currently active.
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
            {satelliteLabel(satellite)}
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
                      title={`${satelliteLabel(satellite)}: ${formatCount(value)}`}
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
                  <span key={satellite} style={{ color: satelliteColor(satellite) }}>
                    {satelliteLabel(satellite)} {formatCount(item.satellites[satellite])}
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
  const satelliteTotals = satellites
    .map((satellite) => ({
      satellite,
      total: items.reduce((sum, item) => sum + (item.satellites[satellite] ?? 0), 0)
    }))
    .filter((item) => item.total > 0);
  // The backend returns satellite counts by day; the frontend adds the total
  // series so operators can compare individual feeds with aggregate activity.
  const series = [
    ...satellites.map((satellite) => ({
      key: satellite,
      label: satelliteLabel(satellite),
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
      <div className="trend-summary">
        <strong>{formatCount(items.reduce((sum, item) => sum + item.total, 0))} total</strong>
        {satelliteTotals.map((item) => (
          <span key={item.satellite} style={{ color: satelliteColor(item.satellite) }}>
            {satelliteLabel(item.satellite)} {formatCount(item.total)}
          </span>
        ))}
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
          <div className="trend-day-values">
            {items.map((item) => {
              const dailySatellites = satellites
                .map((satellite) => ({
                  satellite,
                  total: item.satellites[satellite] ?? 0
                }))
                .filter((dailyItem) => dailyItem.total > 0);
              return (
                <div className="trend-day" key={item.date}>
                  <strong>
                    {formatTrendDate(item.date)}
                    <span>{formatCount(item.total)} total</span>
                  </strong>
                  <div>
                    {dailySatellites.map((dailyItem) => (
                      <span key={dailyItem.satellite} style={{ color: satelliteColor(dailyItem.satellite) }}>
                        {satelliteLabel(dailyItem.satellite)} {formatCount(dailyItem.total)}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
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
  // Preserve a small visible bar for non-zero values in very skewed groups.
  return Math.max((total / maxTotal) * 100, 3);
}

type HotspotFootprintProperties = HotspotFeature["properties"] & {
  center_latitude: number;
  center_longitude: number;
};

function hotspotFootprints(
  collection: HotspotCollection,
  _kind: HotspotKind,
  zoom: number
): GeoJSON.FeatureCollection<GeoJSON.Polygon, HotspotFootprintProperties> {
  return {
    type: "FeatureCollection",
    features: collection.features.flatMap((feature) => {
      const footprint = hotspotFootprint(feature, zoom);
      return footprint ? [footprint] : [];
    })
  };
}

function emptyHotspotCollection(): HotspotCollection {
  return { type: "FeatureCollection", total: 0, features: [] };
}

function hotspotFootprint(
  feature: HotspotFeature,
  zoom: number
): GeoJSON.Feature<GeoJSON.Polygon, HotspotFootprintProperties> | null {
  if (feature.geometry.type !== "Point") {
    return null;
  }
  const [longitude, latitude] = feature.geometry.coordinates;
  const radiusMeters =
    SATELLITE_PIXEL_RADIUS_METERS[feature.properties.satellite] ??
    feature.properties.radius_meters ??
    1000;
  const actualHalfSideMeters = footprintHalfSideMeters(radiusMeters);
  const visibleHalfSideMeters = minimumVisibleHalfSideMeters(latitude, zoom);
  const halfSideMeters = Math.max(actualHalfSideMeters, visibleHalfSideMeters);
  return {
    type: "Feature",
    id: feature.id,
    properties: {
      ...feature.properties,
      center_latitude: latitude,
      center_longitude: longitude
    },
    geometry: {
      type: "Polygon",
      coordinates: [squareCoordinates(longitude, latitude, halfSideMeters)]
    }
  };
}

function footprintHalfSideMeters(radiusMeters: number) {
  return Math.max(radiusMeters / 6, 120);
}

function minimumVisibleHalfSideMeters(latitude: number, zoom: number) {
  const metersPerPixel = 156543.03392 * Math.cos((latitude * Math.PI) / 180) / 2 ** zoom;
  return Math.min(metersPerPixel * 3, 20_000);
}

function squareCoordinates(
  longitude: number,
  latitude: number,
  halfSideMeters: number
): GeoJSON.Position[] {
  const latDelta = halfSideMeters / 111_320;
  const lonScale = Math.max(Math.cos((latitude * Math.PI) / 180), 0.15);
  const lonDelta = halfSideMeters / (111_320 * lonScale);
  const west = longitude - lonDelta;
  const east = longitude + lonDelta;
  const south = latitude - latDelta;
  const north = latitude + latDelta;
  return [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
    [west, south]
  ];
}

function satelliteColor(satellite: string) {
  return SATELLITE_COLORS[satellite] ?? "#627184";
}

function satelliteLabel(satellite: string) {
  return satellite.toLowerCase() === "tera" ? "TERRA" : satellite.toUpperCase();
}

function clampLatitude(value: number) {
  return Math.max(-90, Math.min(90, value));
}

function clampLongitude(value: number) {
  return Math.max(-180, Math.min(180, value));
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
  const coordinates = pointCoordinates(feature);
  return (
    <div className="inspector">
      <button onClick={onClose} aria-label="Close">×</button>
      <h2>{satelliteLabel(String(props.satellite ?? ""))} hotspot</h2>
      <dl>
        <dt>Coordinates</dt><dd>{formatCoordinates(coordinates)}</dd>
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

function pointCoordinates(feature: GeoJSON.Feature) {
  const props = feature.properties ?? {};
  if (
    typeof props.center_latitude === "number" &&
    typeof props.center_longitude === "number"
  ) {
    return { latitude: props.center_latitude, longitude: props.center_longitude };
  }
  if (!feature.geometry || feature.geometry.type !== "Point") {
    return null;
  }
  const [longitude, latitude] = feature.geometry.coordinates;
  return { latitude, longitude };
}

function formatCoordinates(coordinates: { latitude: number; longitude: number } | null) {
  if (!coordinates) {
    return "-";
  }
  return `${coordinates.latitude.toFixed(6)}, ${coordinates.longitude.toFixed(6)}`;
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
  // Summary timestamps include times; date inputs need only YYYY-MM-DD.
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
