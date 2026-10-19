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
  LogIn,
  LogOut,
  Map as MapIcon,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Satellite,
  Search,
  UserPlus
} from "lucide-react";
import maplibregl from "maplibre-gl";
import { type PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  getHotspots,
  getHotspotTotal,
  getLatestObservation,
  getLocationBounds,
  getLocations,
  getRuns,
  getSources,
  getStatistics,
  getSummary,
  getTrend,
  getAccess,
  requestAccess,
  requestScene,
  type SharedAccess,
  type HotspotBbox,
  type HotspotFilters
} from "./api";
import hotspotIcon from "./assets/hotspot-icon.png";
import type {
  ClusterProjection,
  ClusterMethod,
  HotspotCollection,
  HotspotFeature,
  HotspotStatistics,
  HotspotTrend,
  HotspotKind,
  IngestionRun,
  LocationOptions,
  OperationalSummary,
  SceneResponse,
  SourceFile
} from "./types";
import {
  initializeAuthentication,
  login,
  logout,
  register,
  tokenProfile
} from "./keycloak";

const SATELLITES = ["snpp", "noaa20", "aqua", "tera", "landsat8"];
const SATELLITE_COLORS: Record<string, string> = {
  snpp: "#b7192b",
  noaa20: "#e76f2c",
  aqua: "#2f80ed",
  tera: "#287c56",
  landsat8: "#6f4dbf"
};
const SATELLITE_PIXEL_SIZE_METERS: Record<string, number> = {
  snpp: 375,
  noaa20: 375,
  aqua: 1000,
  tera: 1000,
  landsat8: 30
};
// The confidence scale is discrete in the source data, but colors are interpolated
// so the map and sidebar legend read as one continuous low-to-high risk ramp.
const CONFIDENCE_VALUES = Array.from({ length: 10 }, (_, index) => index);
const HOTSPOT_FILL_LAYER = "hotspot-footprints";
const HOTSPOT_BRIDGE_LAYER = "hotspot-footprint-bridges";
const HOTSPOT_FOOTPRINT_EDGE_LAYER = "hotspot-footprint-visibility";
const HOTSPOT_CENTER_LAYER = "hotspot-centers";
const HOTSPOT_ADJACENT_MARKER_LAYER = "hotspot-adjacent-markers";
const SCENE_OVERLAY_SOURCE = "geocatalog-scene-overlay";
const SCENE_OVERLAY_LAYER = "geocatalog-scene-overlay";
const DEFAULT_MAP_CENTER: [number, number] = [118, -2.5];
const DEFAULT_MAP_ZOOM = 4.3;
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
  const bottomRailRef = useRef<HTMLElement | null>(null);
  const railResizeRef = useRef<{ y: number; height: number } | null>(null);
  const defaultDateInitializedRef = useRef(false);
  const viewportRefreshTimeoutRef = useRef<number | null>(null);
  const latestHotspotRequestRef = useRef(0);
  const latestFilterRequestRef = useRef(0);
  const filtersRef = useRef<HotspotFilters | null>(null);
  const [summary, setSummary] = useState<OperationalSummary | null>(null);
  const [hotspots, setHotspots] = useState<HotspotCollection | null>(null);
  const [statistics, setStatistics] = useState<HotspotStatistics | null>(null);
  const [statisticsRefreshKey, setStatisticsRefreshKey] = useState(0);
  const [trend, setTrend] = useState<HotspotTrend | null>(null);
  const [statisticsSearch, setStatisticsSearch] = useState("");
  const [trendSelection, setTrendSelection] = useState<{
    level: "province" | "kabupaten" | "kecamatan";
    value: string;
    label: string;
  } | null>(null);
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [sources, setSources] = useState<SourceFile[]>([]);
  const [kind, setKind] = useState<HotspotKind>("cluster");
  const [clusterMethod, setClusterMethod] = useState<ClusterMethod>("distance");
  const clusterProjection: ClusterProjection = clusterMethod === "adjacent" ? "local_utm" : "epsg4087";
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
  const [previewVisible, setPreviewVisible] = useState(false);
  const [hotspotsHidden, setHotspotsHidden] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [rightRailOpen, setRightRailOpen] = useState(false);
  const [bottomRailOpen, setBottomRailOpen] = useState(false);
  const [bottomRailHeight, setBottomRailHeight] = useState<number | null>(null);
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
  const [isExporting, setIsExporting] = useState(false);
  const [currentCounts, setCurrentCounts] = useState({ clusters: 0, pixels: 0 });
  const [authenticated, setAuthenticated] = useState(false);
  const [access, setAccess] = useState<SharedAccess | null>(null);
  const [accessRole, setAccessRole] = useState<"explorer" | "mage" | "sage">("explorer");
  const [accessError, setAccessError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [accessLoading, setAccessLoading] = useState(true);
  const activeFilters = useMemo<HotspotFilters>(
    () => ({
      kind,
      clusterProjection,
      clusterMethod,
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
      clusterMethod,
      satellites,
      minConfidence,
      observedFrom,
      observedTo,
      province,
      kabupaten,
      kecamatan
    ]
  );
  const trendFilters = useMemo<HotspotFilters>(() => {
    if (!trendSelection) return activeFilters;
    return { ...activeFilters, [trendSelection.level]: trendSelection.value };
  }, [activeFilters, trendSelection]);

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
  const membership = access?.memberships.find(
    (item) => item.application === "hotspot-new" && item.status === "active"
  );

  useEffect(() => {
    void initializeAuthentication()
      .then(async (isAuthenticated) => {
        setAuthenticated(isAuthenticated);
        if (isAuthenticated) {
          setAccess(await getAccess());
        }
      })
      .catch((error) => {
        setAccessError(error instanceof Error ? error.message : "Authentication failed");
      })
      .finally(() => setAccessLoading(false));
  }, []);

  async function submitAccessRequest() {
    setAccessLoading(true);
    setAccessError("");
    try {
      await requestAccess(accessRole);
      setAccess(await getAccess());
    } catch (error) {
      setAccessError(error instanceof Error ? error.message : "Access request failed");
    } finally {
      setAccessLoading(false);
    }
  }

  useEffect(() => {
    if (!mapNodeRef.current || mapRef.current) {
      return;
    }
    // The map style is defined inline so street and satellite basemaps can be
    // switched by toggling layer visibility without rebuilding the map.
    mapRef.current = new maplibregl.Map({
      container: mapNodeRef.current,
      center: DEFAULT_MAP_CENTER,
      zoom: DEFAULT_MAP_ZOOM,
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
      // Hotspots share one source; distance centers render above their translucent extents.
      mapRef.current?.addSource("hotspots", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      mapRef.current?.addLayer({
        id: HOTSPOT_BRIDGE_LAYER,
        type: "line",
        source: "hotspots",
        filter: ["==", ["get", "is_adjacent_bridge"], true],
        layout: { "line-cap": "square", "line-join": "miter" },
        paint: {
          "line-color": confidenceColorExpression(),
          "line-opacity": hotspotOpacityExpression("", "", ""),
          "line-width": ["get", "display_bridge_width_px"]
        }
      });
      mapRef.current?.addLayer({
        id: HOTSPOT_FILL_LAYER,
        type: "fill",
        source: "hotspots",
        filter: ["!=", ["get", "is_cluster_center"], true],
        paint: {
          "fill-color": confidenceColorExpression(),
          "fill-opacity": hotspotOpacityExpression("", "", "")
        }
      });
      mapRef.current?.addLayer({
        id: HOTSPOT_FOOTPRINT_EDGE_LAYER,
        type: "line",
        source: "hotspots",
        filter: ["==", ["get", "is_adjacent_footprint"], true],
        layout: { "line-join": "miter" },
        paint: {
          "line-color": confidenceColorExpression(),
          "line-opacity": hotspotOpacityExpression("", "", ""),
          "line-width": ["get", "display_stroke_px"]
        }
      });
      mapRef.current?.addLayer({
        id: HOTSPOT_CENTER_LAYER,
        type: "fill",
        source: "hotspots",
        filter: ["==", ["get", "is_cluster_center"], true],
        paint: {
          "fill-color": confidenceColorExpression(),
          "fill-opacity": hotspotOpacityExpression("", "", "")
        }
      });
      mapRef.current?.addLayer({
        id: HOTSPOT_ADJACENT_MARKER_LAYER,
        type: "circle",
        source: "hotspots",
        filter: ["==", ["get", "is_adjacent_marker"], true],
        paint: {
          "circle-color": confidenceColorExpression(),
          "circle-opacity": adjacentMarkerOpacityExpression("", "", ""),
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 0, 6, 8, 6, 10, 3, 12, 0],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1,
          "circle-stroke-opacity": adjacentMarkerOpacityExpression("", "", "")
        }
      });
      for (const layer of [HOTSPOT_BRIDGE_LAYER, HOTSPOT_FILL_LAYER, HOTSPOT_FOOTPRINT_EDGE_LAYER,
                           HOTSPOT_CENTER_LAYER, HOTSPOT_ADJACENT_MARKER_LAYER]) {
        mapRef.current?.on("click", layer, (event) => {
          clearScenePreview();
          setSelected(event.features?.[0] ?? null);
        });
        mapRef.current?.on("mouseenter", layer, () => {
          mapRef.current!.getCanvas().style.cursor = "pointer";
        });
        mapRef.current?.on("mouseleave", layer, () => {
          mapRef.current!.getCanvas().style.cursor = "";
        });
      }
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
    void refreshOperational();
  }, []);

  useEffect(() => {
    if (defaultDateInitializedRef.current || observedFrom || observedTo) {
      void refresh();
    }
  }, [activeFilters]);

  useEffect(() => {
    if (!defaultDateInitializedRef.current && !observedFrom && !observedTo) return;
    let current = true;
    const timeout = window.setTimeout(() => {
      void getTrend(trendFilters)
        .then((data) => { if (current) setTrend(data); })
        .catch((error) => {
          console.error("Could not load daily trend", error);
          if (current) setTrend(null);
        });
    }, trendSelection?.value.startsWith("%") ? 250 : 0);
    return () => { current = false; window.clearTimeout(timeout); };
  }, [trendFilters]);

  useEffect(() => {
    setStatisticsSearch("");
    setTrendSelection(null);
  }, [province, kabupaten, kecamatan]);

  useEffect(() => {
    if (!defaultDateInitializedRef.current && !observedFrom && !observedTo) return;
    let current = true;
    const timeout = window.setTimeout(() => {
      void getStatistics(activeFilters, statisticsSearch)
        .then((data) => { if (current) setStatistics(data); })
        .catch((error) => {
          console.error("Could not load statistics", error);
          if (current) setStatistics(null);
        });
    }, statisticsSearch ? 250 : 0);
    return () => { current = false; window.clearTimeout(timeout); };
  }, [activeFilters, statisticsSearch, statisticsRefreshKey]);

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
      source.setData(hotspotFootprints(hotspots, kind, clusterMethod,
        mapRef.current?.getZoom() ?? DEFAULT_MAP_ZOOM));
    }
  }, [hotspots, kind, clusterMethod]);

  useEffect(() => {
    updateMapRegionHighlight();
  }, [province, kabupaten, kecamatan]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const layer of [HOTSPOT_BRIDGE_LAYER, HOTSPOT_FILL_LAYER, HOTSPOT_FOOTPRINT_EDGE_LAYER,
                         HOTSPOT_CENTER_LAYER, HOTSPOT_ADJACENT_MARKER_LAYER]) {
      if (map.getLayer(layer)) {
        map.setLayoutProperty(layer, "visibility", hotspotsHidden ? "none" : "visible");
      }
    }
  }, [hotspotsHidden]);

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

  function initializeDefaultDate(latestDate: string | undefined) {
    if (!defaultDateInitializedRef.current &&
        !filtersRef.current?.observedFrom && !filtersRef.current?.observedTo && latestDate) {
      defaultDateInitializedRef.current = true;
      setObservedFrom(latestDate);
      setObservedTo(latestDate);
    }
  }

  function refreshOperational() {
    void getLatestObservation().then((value) => {
      initializeDefaultDate(value?.slice(0, 10));
    }).catch((error) => console.error("Could not load latest observation", error));
    void getSources().then(setSources)
      .catch((error) => console.error("Could not load source files", error));
    void getRuns().then(setRuns).catch((error) => console.error("Could not load runs", error));
    void getSummary().then((data) => {
      setSummary(data);
      initializeDefaultDate(latestAvailableDate(data));
    }).catch((error) => {
      console.error("Could not load summary", error);
      setLoadError("Summary is unavailable. Try Refresh.");
    });
  }

  function refresh() {
    const filters = activeFilters;
    const bbox = currentMapBbox();
    const hotspotRequestId = ++latestHotspotRequestRef.current;
    const filterRequestId = ++latestFilterRequestRef.current;
    const hotspotRequest = shouldFetchHotspotFeatures(filters, bbox)
      ? getHotspots(filters, bbox)
      : Promise.resolve(emptyHotspotCollection());
    void hotspotRequest.then((data) => {
      if (hotspotRequestId === latestHotspotRequestRef.current) {
        setHotspots(data);
        setLoadError("");
      }
    }).catch((error) => {
      console.error("Could not load hotspots", error);
      if (hotspotRequestId === latestHotspotRequestRef.current) {
        setHotspots(emptyHotspotCollection());
        setLoadError("Hotspots are unavailable. Try Refresh.");
      }
    });
    for (const totalKind of ["cluster", "pixel"] as const) {
      void getHotspotTotal(filters, totalKind).then((total) => {
        if (filterRequestId === latestFilterRequestRef.current) {
          setCurrentCounts((counts) => ({ ...counts,
            [totalKind === "cluster" ? "clusters" : "pixels"]: total }));
        }
      }).catch((error) => {
        console.error(`Could not load ${totalKind} total`, error);
        if (filterRequestId === latestFilterRequestRef.current) {
          setCurrentCounts((counts) => ({ ...counts,
            [totalKind === "cluster" ? "clusters" : "pixels"]: 0 }));
        }
      });
    }
  }

  async function refreshLocations(selectedProvince: string, selectedKabupaten: string) {
    try {
      setLocations(await getLocations(selectedProvince, selectedKabupaten));
    } catch (error) {
      console.error("Could not load locations", error);
    }
  }

  async function zoomToSelectedLocation() {
    if (!province && !kabupaten && !kecamatan) {
      return;
    }
    try {
      const response = await getLocationBounds(province, kabupaten, kecamatan);
      if (response.bbox) fitMapToBbox(response.bbox);
    } catch (error) {
      console.error("Could not load location bounds", error);
    }
  }

  async function refreshViewportHotspots() {
    const filters = currentFilters();
    const bbox = currentMapBbox();
    const hotspotRequestId = ++latestHotspotRequestRef.current;
    if (!shouldFetchHotspotFeatures(filters, bbox)) {
      setHotspots(emptyHotspotCollection());
      return;
    }
    try {
      const hotspotData = await getHotspots(filters, bbox);
      if (hotspotRequestId === latestHotspotRequestRef.current) {
        setHotspots(hotspotData);
        setLoadError("");
      }
    } catch (error) {
      console.error("Could not load viewport hotspots", error);
      if (hotspotRequestId === latestHotspotRequestRef.current) {
        setHotspots(emptyHotspotCollection());
        setLoadError("Hotspots are unavailable. Try Refresh.");
      }
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

  function resetMapView() {
    clearScenePreview();
    setSelected(null);
    mapRef.current?.flyTo({ center: DEFAULT_MAP_CENTER, zoom: DEFAULT_MAP_ZOOM, duration: 700 });
  }

  function resizeStatistics(event: PointerEvent<HTMLButtonElement>) {
    if (!railResizeRef.current) return;
    setBottomRailHeight(Math.max(200, Math.min(
      window.innerHeight - 80,
      railResizeRef.current.height + railResizeRef.current.y - event.clientY
    )));
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
    const point = pointerPoint(event);
    setBboxSelection((current) =>
      current.active && current.dragging
        ? { ...current, current: point }
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

  function clearScenePreview() {
    removeSceneOverlay(mapRef.current);
    setPreviewVisible(false);
    setHotspotsHidden(false);
  }

  function updateMapRegionHighlight() {
    const map = mapRef.current;
    if (!map?.getLayer(HOTSPOT_FILL_LAYER)) {
      return;
    }
    for (const layer of [HOTSPOT_FILL_LAYER, HOTSPOT_CENTER_LAYER]) {
      map.setPaintProperty(layer, "fill-color", hotspotColorExpression(province, kabupaten, kecamatan));
      map.setPaintProperty(layer, "fill-opacity", hotspotOpacityExpression(province, kabupaten, kecamatan));
    }
    map.setPaintProperty(HOTSPOT_FOOTPRINT_EDGE_LAYER, "line-color",
      hotspotColorExpression(province, kabupaten, kecamatan));
    map.setPaintProperty(HOTSPOT_FOOTPRINT_EDGE_LAYER, "line-opacity",
      hotspotOpacityExpression(province, kabupaten, kecamatan));
    map.setPaintProperty(HOTSPOT_BRIDGE_LAYER, "line-color",
      hotspotColorExpression(province, kabupaten, kecamatan));
    map.setPaintProperty(HOTSPOT_BRIDGE_LAYER, "line-opacity",
      hotspotOpacityExpression(province, kabupaten, kecamatan));
    map.setPaintProperty(HOTSPOT_ADJACENT_MARKER_LAYER, "circle-color",
      hotspotColorExpression(province, kabupaten, kecamatan));
    for (const property of ["circle-opacity", "circle-stroke-opacity"] as const) {
      map.setPaintProperty(HOTSPOT_ADJACENT_MARKER_LAYER, property,
        adjacentMarkerOpacityExpression(province, kabupaten, kecamatan));
    }
  }

  async function exportGeoJson() {
    setIsExporting(true);
    try {
      // Map rendering is bbox-aware, but export must represent the complete
      // sidebar filter set. Intentionally omit bbox here.
      const filteredHotspots = await getHotspots(activeFilters, null);
      const blob = new Blob([JSON.stringify(filteredHotspots, null, 2)], {
        type: "application/geo+json"
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = geoJsonExportName(activeFilters);
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <main className={`app-shell ${rightRailOpen ? "" : "rail-collapsed"} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <aside className={`sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
        <div className="brand">
          <button className="brand-logo-button" onClick={() => setSidebarCollapsed((collapsed) => !collapsed)} title="Toggle sidebar" aria-label="Toggle sidebar">
            <img className="brand-logo" src={hotspotIcon} alt="" />
          </button>
          {!sidebarCollapsed ? (
          <button className="brand-title" onClick={resetMapView} title="Reset map to Indonesia">
            <span className="brand-name">BRIN Fire Hotspot</span>
            <span className="brand-subtitle">Indonesia active fire monitoring</span>
          </button>
          ) : null}
        </div>

        {!sidebarCollapsed ? (
        <>
        <section className="panel access-panel">
          {accessLoading ? <p>Checking account…</p> : null}
          {!accessLoading && !authenticated ? (
            <>
              <strong>Satellite scene access</strong>
              <p>Sign in to request imagery and download scene assets.</p>
              <div className="access-actions">
                <button onClick={() => void login()}><LogIn size={14} /> Sign in</button>
                <button onClick={() => void register()}><UserPlus size={14} /> Register</button>
              </div>
            </>
          ) : null}
          {!accessLoading && authenticated && membership ? (
            <>
              <strong>{tokenProfile().name || tokenProfile().email}</strong>
              <p>{membership.role}{membership.role === "mage" ? ` · ${formatCount(membership.token_balance)} tokens` : ""}</p>
              <button onClick={() => void logout()}><LogOut size={14} /> Sign out</button>
            </>
          ) : null}
          {!accessLoading && authenticated && !membership ? (
            <>
              <strong>{tokenProfile().name || tokenProfile().email}</strong>
              {access?.pending_requests.some((item) => item.application === "hotspot-new") ? (
                <p>Your Hotspot access request is awaiting approval.</p>
              ) : (
                <div className="access-request-row">
                  <select
                    value={accessRole}
                    onChange={(event) => setAccessRole(event.target.value as typeof accessRole)}
                  >
                    <option value="explorer">Explorer</option>
                    <option value="mage">Mage</option>
                    <option value="sage">Sage</option>
                  </select>
                  <button onClick={() => void submitAccessRequest()}>Request access</button>
                </div>
              )}
              <button className="link-button" onClick={() => void logout()}>Sign out</button>
            </>
          ) : null}
          {accessError ? <p className="access-error">{accessError}</p> : null}
        </section>
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
        {loadError && <p className="panel access-error" role="alert">{loadError}</p>}

        <section className="panel controls">
          <div className="panel-title">
            <Search size={16} />
            <span>Filters</span>
          </div>
          <div className="segmented">
            <button className={kind === "cluster" ? "active" : ""} onClick={() => { clearScenePreview(); setSelected(null); setKind("cluster"); }}>Cluster</button>
            <button className={kind === "pixel" ? "active" : ""} onClick={() => { clearScenePreview(); setSelected(null); setKind("pixel"); }}>Pixel</button>
          </div>
          {kind === "cluster" ? (
            <div className="segmented cluster-methods" aria-label="Cluster view">
              <button className={clusterMethod === "distance" ? "active" : ""} onClick={() => { clearScenePreview(); setSelected(null); setClusterMethod("distance"); }}>Center and circle</button>
              <button className={clusterMethod === "adjacent" ? "active" : ""} onClick={() => { clearScenePreview(); setSelected(null); setClusterMethod("adjacent"); }}>Connected footprints</button>
            </div>
          ) : null}
          {kind === "cluster" && clusterMethod === "distance" ? (
            <p className="helper-text">Circles enclose detected pixels, not fire area; they are enlarged at low zoom for visibility.</p>
          ) : null}
          {kind === "cluster" && clusterMethod === "adjacent" ? (
            <p className="helper-text">Within a scene, SNPP and NOAA20 footprints with gaps under one pixel width on both axes share a cluster; overlaps merge. Visual bridges fill small gaps, but reported area excludes them. Enlarged low-zoom shapes may appear to overlap.</p>
          ) : null}
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
            <strong>{formatCount(hotspotsHidden ? 0 : visibleCount)}</strong>
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
          <button className="toolbar-button" onClick={() => {
            void refreshOperational();
            void refresh();
            setStatisticsRefreshKey((key) => key + 1);
            void getTrend(trendFilters)
              .then(setTrend).catch((error) => console.error("Could not load daily trend", error));
          }}><RefreshCw size={16} /> Refresh</button>
          {previewVisible ? (
            <button className="toolbar-button" aria-pressed={hotspotsHidden} onClick={() => setHotspotsHidden((hidden) => !hidden)}>
              {hotspotsHidden ? "Show" : "Hide"} hotspot {kind === "cluster" ? "clusters" : "pixels"}
            </button>
          ) : null}
          <button className="toolbar-button" onClick={() => void exportGeoJson()} disabled={isExporting}>
            <Download size={16} /> {isExporting ? "Exporting" : "GeoJSON"}
          </button>
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
        {selected && (
          <FeatureInspector
            key={JSON.stringify([selected.id, selected.geometry, selected.properties?.scene_id, selected.properties?.observed_at])}
            feature={selected}
            previewVisible={previewVisible}
            onClose={() => {
              clearScenePreview();
              setSelected(null);
            }}
            onScenePreview={(scene) => {
              if (scene) {
                showSceneOverlay(mapRef.current, scene);
                setPreviewVisible(true);
                setHotspotsHidden(false);
              } else {
                clearScenePreview();
              }
            }}
          />
        )}
        {bottomRailOpen && (
          <section className="bottom-rail" ref={bottomRailRef}
            style={bottomRailHeight === null ? undefined : { height: bottomRailHeight }}>
            <button className="statistics-resize-handle"
              aria-label="Resize statistics panel"
              title="Drag to resize statistics panel"
              onPointerDown={(event) => {
                railResizeRef.current = {
                  y: event.clientY,
                  height: bottomRailRef.current?.offsetHeight ?? 0
                };
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerMove={resizeStatistics}
              onPointerUp={() => { railResizeRef.current = null; }}
              onPointerCancel={() => { railResizeRef.current = null; }}
              onKeyDown={(event) => {
                if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
                event.preventDefault();
                setBottomRailHeight(Math.max(200, Math.min(window.innerHeight - 80,
                  (bottomRailRef.current?.offsetHeight ?? 200) + (event.key === "ArrowUp" ? 40 : -40)
                )));
              }}
            />
            <div className="statistics-grid">
              <StatisticsPanel
                kind={kind}
                statistics={statistics}
                satellites={satellites}
                province={province}
                kabupaten={kabupaten}
                kecamatan={kecamatan}
                search={statisticsSearch}
                selectedValue={trendSelection?.value ?? ""}
                onSearch={(value) => {
                  setStatisticsSearch(value);
                  const level = statistics?.level;
                  if (level && level !== "satellite") {
                    setTrendSelection(value ? { level, value: `%${value}%`, label: value } : null);
                  }
                }}
                onSelect={(value) => {
                  setStatisticsSearch(value);
                  const level = statistics?.level;
                  if (level && level !== "satellite") {
                    setTrendSelection({ level, value, label: value });
                  }
                }}
              />
              <TrendPanel kind={kind} trend={trend} satellites={satellites}
                location={trendSelection?.label || kecamatan || kabupaten || province} />
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

function geoJsonExportName(filters: HotspotFilters) {
  const datePart =
    filters.observedFrom && filters.observedTo && filters.observedFrom === filters.observedTo
      ? filters.observedFrom
      : [filters.observedFrom || "start", filters.observedTo || "end"].join("_");
  return `brin-hotspots-${filters.kind}-${datePart}.geojson`;
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
  const extent: maplibregl.ExpressionSpecification = ["==", ["get", "is_cluster_extent"], true];
  const normalOpacity: maplibregl.ExpressionSpecification = ["case", extent, 0.2, 0.9];
  if (!regionMatch) {
    return normalOpacity;
  }
  return ["case", regionMatch, normalOpacity, ["case", extent, 0.08, 0.32]];
}

function adjacentMarkerOpacityExpression(
  province: string,
  kabupaten: string,
  kecamatan: string
): maplibregl.ExpressionSpecification {
  const opacity = hotspotOpacityExpression(province, kabupaten, kecamatan);
  return ["interpolate", ["linear"], ["zoom"], 0, opacity, 8, opacity, 12, 0];
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
  kecamatan,
  search,
  selectedValue,
  onSearch,
  onSelect
}: {
  kind: HotspotKind;
  statistics: HotspotStatistics | null;
  satellites: string[];
  province: string;
  kabupaten: string;
  kecamatan: string;
  search: string;
  selectedValue: string;
  onSearch: (value: string) => void;
  onSelect: (value: string) => void;
}) {
  const isAdministrativeLevel = statistics?.level !== "satellite";
  const searchLabel = statistics?.level === "kabupaten" ? "Search kota/kabupaten"
    : statistics?.level === "kecamatan" ? "Search kecamatan" : "Search provinsi";
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
      {isAdministrativeLevel && (
        <label className="province-search">
          <Search size={15} />
          <input type="search" placeholder={searchLabel} aria-label={searchLabel}
            value={search}
            onChange={(event) => onSearch(event.target.value)} />
        </label>
      )}
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
          <button type="button" className="chart-row province-chart-row" key={item.label}
            aria-pressed={isAdministrativeLevel && selectedValue === item.label}
            disabled={!isAdministrativeLevel}
            onClick={() => onSelect(item.label)}>
            <span className="chart-row-label">
              <span>{item.label}</span>
              <strong>{formatCount(item.total)}</strong>
            </span>
            <span className="chart-track">
              <span className="chart-stack" style={{ width: `${barWidth(item.total, maxTotal)}%` }}>
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
              </span>
            </span>
            <span className="chart-values">
              {satellites
                .filter((satellite) => (item.satellites[satellite] ?? 0) > 0)
                .map((satellite) => (
                  <span key={satellite} style={{ color: satelliteColor(satellite) }}>
                    {satelliteLabel(satellite)} {formatCount(item.satellites[satellite])}
                  </span>
                ))}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function TrendPanel({
  kind,
  trend,
  satellites,
  location
}: {
  kind: HotspotKind;
  trend: HotspotTrend | null;
  satellites: string[];
  location: string;
}) {
  const items = trend?.items ?? [];
  const confidenceBands = [
    { label: "Low", values: CONFIDENCE_VALUES.filter((value) => value <= 7) },
    { label: "Medium", values: [8] },
    { label: "High", values: [9] }
  ];
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
        <span>{location || "Selected satellites and total"}</span>
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
                <details className="trend-day" key={item.date}>
                  <summary>
                    <strong>
                      <span className="trend-day-date">{formatTrendDate(item.date)}</span>
                      <span>{formatCount(item.total)} total</span>
                    </strong>
                    <span className="trend-day-platforms">
                    {dailySatellites.map((dailyItem) => (
                      <span key={dailyItem.satellite} style={{ color: satelliteColor(dailyItem.satellite) }}>
                        {satelliteLabel(dailyItem.satellite)} {formatCount(dailyItem.total)}
                      </span>
                    ))}
                    </span>
                  </summary>
                  <div className="confidence-table-wrap">
                    <strong>{kind === "pixel" ? "Pixels" : "Clusters"} by confidence</strong>
                    <table className="confidence-table">
                      <thead><tr><th scope="col">Platform</th>
                        {confidenceBands.map((band, index) =>
                          <th scope="col" key={band.label}
                            style={{ color: confidenceColor(index + 7) }}>{band.label}</th>)}
                        <th scope="col">Total</th>
                      </tr></thead>
                      <tbody>
                        {[
                          ...SATELLITES.filter((satellite) => satellites.includes(satellite) &&
                            (item.satellites[satellite] ?? 0) > 0).map((satellite) => ({
                            label: satelliteLabel(satellite),
                            counts: item.satellite_confidences[satellite] ?? {},
                            total: item.satellites[satellite] ?? 0
                          })),
                          { label: "Total", counts: item.confidences, total: item.total }
                        ].map((row) => (
                          <tr key={row.label}>
                            <th scope="row">{row.label}</th>
                            {confidenceBands.map((band) => <td key={band.label}>
                              {formatCount(band.values.reduce((sum, value) => sum + (row.counts[value] ?? 0), 0))}
                            </td>)}
                            <td>{formatCount(row.total)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
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
  is_cluster_extent?: boolean;
  is_cluster_center?: boolean;
  is_adjacent_footprint?: boolean;
  is_adjacent_bridge?: boolean;
  is_adjacent_marker?: boolean;
  display_stroke_px?: number;
  display_bridge_width_px?: number;
};

function hotspotFootprints(
  collection: HotspotCollection,
  kind: HotspotKind,
  method: ClusterMethod,
  zoom: number
): GeoJSON.FeatureCollection<
  GeoJSON.Point | GeoJSON.Polygon | GeoJSON.MultiPolygon | GeoJSON.LineString,
  HotspotFootprintProperties
> {
  return {
    type: "FeatureCollection",
    features: collection.features.flatMap((feature) => hotspotFootprint(feature, kind, method, zoom))
  };
}

function emptyHotspotCollection(): HotspotCollection {
  return { type: "FeatureCollection", total: 0, features: [] };
}

function hotspotFootprint(
  feature: HotspotFeature,
  kind: HotspotKind,
  method: ClusterMethod,
  zoom: number
): GeoJSON.Feature<
  GeoJSON.Point | GeoJSON.Polygon | GeoJSON.MultiPolygon | GeoJSON.LineString,
  HotspotFootprintProperties
>[] {
  if (feature.geometry.type === "MultiPolygon") {
    if (typeof feature.properties.center_latitude !== "number" ||
        typeof feature.properties.center_longitude !== "number") return [];
    const latitude = feature.properties.center_latitude;
    const pixelSizeMeters = SATELLITE_PIXEL_SIZE_METERS[feature.properties.satellite] ?? 1000;
    const actualHalfSideMeters = pixelSizeMeters / 2;
    const visibleHalfSideMeters = zoom >= 12 ? actualHalfSideMeters
      : Math.max(actualHalfSideMeters, minimumVisibleHalfSideMeters(latitude, zoom));
    const footprint: GeoJSON.Feature<GeoJSON.MultiPolygon, HotspotFootprintProperties> = {
      type: "Feature",
      id: feature.id,
      geometry: feature.geometry,
      properties: {
        ...feature.properties,
        center_latitude: latitude,
        center_longitude: feature.properties.center_longitude,
        is_adjacent_footprint: true,
        display_stroke_px: 2 * (visibleHalfSideMeters - actualHalfSideMeters) /
          metersPerPixel(latitude, zoom)
      }
    };
    const bridges: GeoJSON.Feature<GeoJSON.LineString, HotspotFootprintProperties>[] =
      footprintBridgeSegments(feature.geometry, pixelSizeMeters, latitude,
        feature.properties.satellite === "snpp" || feature.properties.satellite === "noaa20")
        .map((coordinates, index): GeoJSON.Feature<GeoJSON.LineString, HotspotFootprintProperties> => ({
          type: "Feature",
          id: feature.id === undefined ? undefined : `${feature.id}-bridge-${index}`,
          geometry: { type: "LineString", coordinates },
          properties: {
            ...footprint.properties,
            is_adjacent_footprint: false,
            is_adjacent_bridge: true,
            display_bridge_width_px: 2 * visibleHalfSideMeters / metersPerPixel(latitude, zoom)
          }
        }));
    return [footprint, ...bridges, {
      type: "Feature",
      id: feature.id === undefined ? undefined : `${feature.id}-marker`,
      geometry: {
        type: "Point",
        coordinates: [feature.properties.center_longitude, latitude]
      },
      properties: {
        ...footprint.properties,
        is_adjacent_footprint: false,
        is_adjacent_marker: true
      }
    }];
  }
  if (feature.geometry.type !== "Point") {
    return [];
  }
  const [longitude, latitude] = feature.geometry.coordinates;
  const pixelSizeMeters =
    SATELLITE_PIXEL_SIZE_METERS[feature.properties.satellite] ??
    (feature.properties.radius_meters ? feature.properties.radius_meters / 3 : 1000);
  const actualHalfSideMeters = pixelSizeMeters / 2;
  const visibleHalfSideMeters = minimumVisibleHalfSideMeters(latitude, zoom);
  const halfSideMeters =
    zoom >= 12 ? actualHalfSideMeters : Math.max(actualHalfSideMeters, visibleHalfSideMeters);
  const circle = kind === "cluster" && method === "distance";
  const radiusMeters = Math.max(feature.properties.radius_meters ?? pixelSizeMeters / Math.SQRT2,
    zoom >= 12 ? 0 : halfSideMeters * 2);
  const extent: GeoJSON.Feature<GeoJSON.Polygon, HotspotFootprintProperties> = {
    type: "Feature",
    id: feature.id,
    properties: {
      ...feature.properties,
      center_latitude: latitude,
      center_longitude: longitude,
      is_cluster_extent: circle
    },
    geometry: {
      type: "Polygon",
      coordinates: [circle
        ? circleCoordinates(longitude, latitude, radiusMeters)
        : squareCoordinates(longitude, latitude, halfSideMeters)]
    }
  };
  if (!circle) return [extent];
  return [extent, {
    ...extent,
    id: feature.id === undefined ? undefined : `${feature.id}-center`,
    properties: { ...extent.properties, is_cluster_extent: false, is_cluster_center: true },
    geometry: {
      type: "Polygon",
      coordinates: [circleCoordinates(longitude, latitude, halfSideMeters)]
    }
  }];
}

function footprintBridgeSegments(
  geometry: GeoJSON.MultiPolygon,
  pixelSizeMeters: number,
  latitude: number,
  viirs: boolean
): GeoJSON.Position[][] {
  if (geometry.coordinates.length < 2) return [];
  // shortcut: component bounds stand in for pixel edges; use source centers if concave parts misbridge.
  const boxes = geometry.coordinates.map((polygon) => {
    const box = { west: Infinity, east: -Infinity, south: Infinity, north: -Infinity };
    for (const [longitude, lat] of polygon[0]) {
      box.west = Math.min(box.west, longitude);
      box.east = Math.max(box.east, longitude);
      box.south = Math.min(box.south, lat);
      box.north = Math.max(box.north, lat);
    }
    return box;
  });
  const longitudeMeters = 111_320 * Math.cos(latitude * Math.PI / 180);
  const candidates: { left: number; right: number; gap: number; coordinates: GeoJSON.Position[] }[] = [];
  for (let left = 0; left < boxes.length; left++) {
    for (let right = left + 1; right < boxes.length; right++) {
      const a = boxes[left], b = boxes[right];
      const dx = Math.max(0, a.west - b.east, b.west - a.east) * longitudeMeters;
      const dy = Math.max(0, a.south - b.north, b.south - a.north) * 111_320;
      if (viirs ? dx >= pixelSizeMeters * 1.05 || dy >= pixelSizeMeters * 1.05
        : Math.hypot(dx, dy) > pixelSizeMeters * 0.525) continue;
      const nearX = (Math.max(a.west, b.west) + Math.min(a.east, b.east)) / 2;
      const nearY = (Math.max(a.south, b.south) + Math.min(a.north, b.north)) / 2;
      const clamp = (value: number, low: number, high: number) =>
        Math.max(low, Math.min(high, value));
      const coordinates = [
        [clamp(nearX, a.west, a.east), clamp(nearY, a.south, a.north)],
        [clamp(nearX, b.west, b.east), clamp(nearY, b.south, b.north)]
      ];
      if (coordinates[0][0] === coordinates[1][0] &&
          coordinates[0][1] === coordinates[1][1]) continue;
      candidates.push({ left, right, gap: dx * dx + dy * dy, coordinates });
    }
  }
  candidates.sort((a, b) => a.gap - b.gap);
  const parent = boxes.map((_, index) => index);
  const root = (index: number): number => {
    while (parent[index] !== index) index = parent[index] = parent[parent[index]];
    return index;
  };
  const bridges: GeoJSON.Position[][] = [];
  for (const candidate of candidates) {
    const left = root(candidate.left), right = root(candidate.right);
    if (left === right) continue;
    parent[right] = left;
    bridges.push(candidate.coordinates);
  }
  return bridges;
}

function minimumVisibleHalfSideMeters(latitude: number, zoom: number) {
  return Math.min(metersPerPixel(latitude, zoom) * 3, 20_000);
}

function metersPerPixel(latitude: number, zoom: number) {
  return 156543.03392 * Math.cos((latitude * Math.PI) / 180) / 2 ** zoom;
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

function circleCoordinates(longitude: number, latitude: number, radiusMeters: number): GeoJSON.Position[] {
  const longitudeScale = Math.max(Math.cos((latitude * Math.PI) / 180), 0.15);
  return Array.from({ length: 33 }, (_, index) => {
    const angle = (index * Math.PI * 2) / 32;
    return [
      longitude + radiusMeters * Math.cos(angle) / (111_320 * longitudeScale),
      latitude + radiusMeters * Math.sin(angle) / 111_320
    ];
  });
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

function FeatureInspector({
  feature,
  previewVisible,
  onClose,
  onScenePreview
}: {
  feature: GeoJSON.Feature;
  previewVisible: boolean;
  onClose: () => void;
  onScenePreview: (scene: SceneResponse | null) => void;
}) {
  const props = feature.properties ?? {};
  const coordinates = pointCoordinates(feature);
  const [scene, setScene] = useState<SceneResponse | null>(null);
  const [sceneError, setSceneError] = useState("");
  const [sceneLoading, setSceneLoading] = useState(false);

  useEffect(() => {
    if (scene?.status !== "pending") {
      return;
    }
    const retry = window.setTimeout(
      () => void loadScene(false),
      (scene.retry_after_seconds ?? 60) * 1000
    );
    return () => window.clearTimeout(retry);
  }, [scene]);

  async function loadScene(acquire = false) {
    if (!coordinates || !props.observed_at || !props.satellite) {
      return;
    }
    setSceneLoading(true);
    setSceneError("");
    onScenePreview(null);
    try {
      const resolved = await requestScene({
        satellite: String(props.satellite),
        observed_at: String(props.observed_at),
        longitude: coordinates.longitude,
        latitude: coordinates.latitude,
        scene_id: props.scene_id ? String(props.scene_id) : null,
        pixel_size_meters: SATELLITE_PIXEL_SIZE_METERS[String(props.satellite)] ?? 1000,
        acquire
      });
      setScene(resolved);
    } catch (error) {
      setSceneError(error instanceof Error ? error.message : "Could not request satellite scene");
    } finally {
      setSceneLoading(false);
    }
  }

  return (
    <div className="inspector">
      <button className="inspector-close" onClick={onClose} aria-label="Close">×</button>
      <h2>{satelliteLabel(String(props.satellite ?? ""))} hotspot</h2>
      <dl>
        <dt>Coordinates</dt><dd>{formatCoordinates(coordinates)}</dd>
        <dt>Confidence</dt><dd>{String(props.confidence ?? "-")}</dd>
        <dt>Observed</dt><dd>{formatDate(String(props.observed_at ?? ""))}</dd>
        <dt>Province</dt><dd>{String(props.province ?? "-")}</dd>
        <dt>Kabupaten</dt><dd>{String(props.kabupaten ?? "-")}</dd>
        <dt>Kecamatan</dt><dd>{String(props.kecamatan ?? "-")}</dd>
        <dt>Scene</dt><dd>{String(props.scene_id ?? "-")}</dd>
        {typeof props.pixel_count === "number" ? (
          <><dt>Detected pixels</dt><dd>{props.pixel_count}</dd></>
        ) : null}
        {(props.is_cluster_extent === true || props.is_cluster_center === true) &&
         typeof props.radius_meters === "number" ? (
          <><dt>Approximate enclosing radius</dt>
          <dd>{props.radius_meters.toLocaleString()} m</dd></>
        ) : null}
        {typeof props.footprint_area_m2 === "number" ? (
          <><dt>Approximate active-fire detection footprint area</dt>
          <dd>{(props.footprint_area_m2 / 10_000).toFixed(2)} ha</dd></>
        ) : null}
      </dl>
      <button
        className="scene-request-button"
        disabled={sceneLoading || !coordinates || !props.observed_at}
        onClick={() => void loadScene(false)}
      >
        {sceneLoading ? "Checking GeoCatalog…" : "Load satellite scene"}
      </button>
      {scene?.status === "ready" && scene.asset_url ? (
        <p className="scene-status">
          {scene.can_acquire ? "Radiance available." : "Scene ready."} <a href={scene.asset_url} target="_blank" rel="noreferrer">Download radiance</a>
        </p>
      ) : null}
      {scene?.status === "ready" && scene.dataset ? (
        <p className="scene-status">Catalog dataset: {scene.dataset.title}</p>
      ) : null}
      {scene?.status === "ready" && (scene.reason || !scene.overlay_url) ? (
        <p className="scene-status">{scene.reason || "No map preview is available for this dataset."}</p>
      ) : null}
      {scene?.status === "ready" && scene.overlay_url && scene.overlay_bbox ? (
        <button
          className="scene-preview-toggle"
          role="switch"
          aria-checked={previewVisible}
          onClick={() => onScenePreview(previewVisible ? null : scene)}
        >
          {previewVisible ? "Hide preview from map" : "Show preview on map"}
        </button>
      ) : null}
      {scene?.status === "ready" && scene.can_acquire ? (
        <button className="scene-preview-toggle" disabled={sceneLoading} onClick={() => void loadScene(true)}>
          {sceneLoading ? "Requesting…" : "Re-acquire incomplete scene bundle"}
        </button>
      ) : null}
      {scene?.status === "ready" && scene.bundle_url ? (
        <p className="scene-status">
          <a href={scene.bundle_url}>Download complete bundle (.tar)</a>
        </p>
      ) : null}
      {scene?.status === "ready" && scene.assets.length > 0 ? (
        <ul className="scene-assets">
          {scene.assets.map((asset) => (
            <li key={asset.id}>
              <a href={asset.download_url}>{sceneAssetLabel(asset.role)}</a>
              <span>{asset.title}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {scene?.status === "pending" ? (
        <p className="scene-status">
          {scene.job?.provider === "local"
            ? "GeoCatalog is rendering the fire image from the ground-station pass…"
            : "GeoCatalog queued this scene for download and indexing."}
        </p>
      ) : null}
      {scene?.status === "unavailable" ? (
        <>
          <p className="scene-status">{scene.reason}</p>
          {scene.can_acquire ? (
            <div className="scene-acquisition-choice">
              <button disabled={sceneLoading} onClick={() => void loadScene(true)}>
                {sceneLoading ? "Requesting…" : "Queue acquisition"}
              </button>
              <button disabled={sceneLoading} onClick={() => setScene(null)}>Not now</button>
            </div>
          ) : null}
        </>
      ) : null}
      {sceneError ? <p className="scene-status scene-error">{sceneError}</p> : null}
    </div>
  );
}

function removeSceneOverlay(map: maplibregl.Map | null) {
  if (!map) return;
  if (map.getLayer(SCENE_OVERLAY_LAYER)) {
    map.removeLayer(SCENE_OVERLAY_LAYER);
  }
  if (map.getSource(SCENE_OVERLAY_SOURCE)) {
    map.removeSource(SCENE_OVERLAY_SOURCE);
  }
}

function showSceneOverlay(map: maplibregl.Map | null, scene: SceneResponse) {
  if (!map || !scene.overlay_url || !scene.overlay_bbox) {
    return;
  }
  removeSceneOverlay(map);
  const [west, south, east, north] = scene.overlay_bbox;
  map.addSource(SCENE_OVERLAY_SOURCE, {
    type: "image",
    url: scene.overlay_url,
    coordinates: [
      [west, north],
      [east, north],
      [east, south],
      [west, south]
    ]
  });
  map.addLayer(
    {
      id: SCENE_OVERLAY_LAYER,
      type: "raster",
      source: SCENE_OVERLAY_SOURCE,
      paint: { "raster-opacity": 0.82 }
    },
    HOTSPOT_FILL_LAYER
  );
  map.fitBounds(
    [
      [west, south],
      [east, north]
    ],
    { padding: 64, maxZoom: 12 }
  );
}

function sceneAssetLabel(role: string) {
  return {
    radiance: "Radiance",
    geolocation: "Geolocation",
    overlay: "Map overlay GeoTIFF",
    "overlay-preview": "Map preview PNG"
  }[role] ?? "Scene asset";
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
    month: "short",
    year: "numeric"
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
