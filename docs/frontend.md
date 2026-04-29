# Frontend Documentation

This document describes the React frontend for BRIN Hotspot Modernization.

## Frontend Responsibilities

The frontend is an operational map dashboard for hotspot visualization. It is responsible for:

- Displaying hotspot clusters or pixels on an interactive MapLibre map.
- Fetching read-only data from the FastAPI backend.
- Providing filters for date, confidence, satellite, province, kota/kabupaten, and kecamatan.
- Switching between OpenStreetMap street tiles and ESRI World Imagery satellite tiles.
- Showing operational status, recent ingestion runs, and recent source files.
- Showing hotspot statistics and daily trends.
- Exporting the current map GeoJSON payload.

## Source Layout

| Path | Responsibility |
| --- | --- |
| `frontend/src/main.tsx` | React application entry point. |
| `frontend/src/App.tsx` | Main dashboard, map setup, filters, rails, charts, and helper functions. |
| `frontend/src/api.ts` | API client, query-string construction, date conversion, and mock fallback. |
| `frontend/src/types.ts` | TypeScript types matching API responses. |
| `frontend/src/mockData.ts` | Local fallback data used when the API is unavailable. |
| `frontend/src/styles.css` | Application layout and component styling. |
| `frontend/src/assets/hotspot-logo.png` | Dashboard logo. |
| `frontend/nginx.conf` | Nginx config for static frontend serving and `/api/*` proxying. |
| `frontend/Dockerfile` | Multi-stage production image build. |

## Runtime Architecture

The frontend is built with:

- React
- TypeScript
- Vite
- MapLibre GL
- Lucide React icons
- Nginx for production serving

Production container flow:

1. `frontend/Dockerfile` installs dependencies with `npm ci`.
2. Vite builds static assets into `dist/`.
3. Nginx serves the built assets on port `80`.
4. Nginx proxies `/api/*` requests to the API service inside the Docker Compose network.

The browser accesses the frontend at:

```text
http://localhost:8080
```

## API Client

`frontend/src/api.ts` uses this API base:

```ts
const API_BASE = import.meta.env.VITE_HOTSPOT_API_BASE ?? "/api/v1";
```

In Docker Compose, `/api/v1` is proxied by Nginx to the `api` container. For local Vite development, set `VITE_HOTSPOT_API_BASE` if the API is served elsewhere.

Example:

```bash
VITE_HOTSPOT_API_BASE=http://localhost:8000/api/v1 npm --prefix frontend run dev
```

Every API call falls back to mock data if the request fails. This keeps UI development possible when the database or API is not running.

## Main Data Flow

The main dashboard state is stored in `App.tsx`.

Important state groups:

| State | Purpose |
| --- | --- |
| `summary` | Operational summary totals and source-file statuses. |
| `hotspots` | GeoJSON map features and actual filtered total. |
| `statistics` | Grouped hotspot totals for the stacked bar chart. |
| `trend` | Daily hotspot totals for the line chart. |
| `runs` | Recent ingestion runs. |
| `sources` | Recent source-file checkpoint records. |
| `kind` | `cluster` or `pixel`. |
| `satellites` | Selected satellite filters. |
| `minConfidence` | Minimum confidence threshold. |
| `observedFrom`, `observedTo` | Date-only filters. |
| `province`, `kabupaten`, `kecamatan` | Administrative filters. |
| `rightRailOpen` | Right rail visibility. |
| `bottomRailOpen` | Statistics rail visibility. |
| `basemap` | `street` or `satellite`. |

When filters change, `refresh()` fetches summary, hotspots, statistics, trend, runs, and source files in parallel.

The map source is updated when `hotspots` changes. Region highlighting and basemap visibility are applied through MapLibre paint/layout updates.

## Default Date Behavior

On first load, the frontend requests `/summary`, finds the latest available observation date across satellites, and sets both date fields to that day. This means the default view is filtered to the last day of available data rather than the current calendar date.

The date preset buttons update the same from/to date fields:

| Button | Behavior |
| --- | --- |
| Last 24 hours | Sets a two-date range ending today because the UI is date-only. |
| Last 7 days | Sets a seven-date range ending today. |

The API client expands date-only values to full-day datetime bounds.

## Map

The map is initialized once with MapLibre.

Basemaps:

| Basemap | Source |
| --- | --- |
| Street | OpenStreetMap raster tiles. |
| Satellite | ESRI World Imagery raster tiles. |

Hotspots are rendered as a single `circle` layer from a GeoJSON source named `hotspots`.

Map interactions:

- Clicking a hotspot opens the feature inspector.
- Hovering over a hotspot changes the cursor.
- Switching basemap toggles raster layer visibility.
- Selecting province, kota/kabupaten, or kecamatan keeps matching hotspots colored and greys out non-selected hotspots.

## Hotspot Colors and Confidence Scale

Confidence values are numeric from `0` to `9`.

The map and sidebar use the same continuous color ramp:

```text
0 = white
6 = yellow
8 = orange
9 = red
```

The sidebar displays ten unlabeled circles below the minimum-confidence slider. The selected numeric value is shown above the slider, so the circles only communicate the color ramp. Circles below the current threshold are muted.

The React helper `confidenceColor()` mirrors the MapLibre expression returned by `confidenceColorExpression()`. Keep those stop values aligned when changing the ramp.

## Filters

The dashboard supports these filters:

| Filter | UI | API behavior |
| --- | --- | --- |
| Cluster/pixel | Segmented control | Sends `kind=cluster` or `kind=pixel`. |
| Minimum confidence | Slider | Sends `min_confidence`. |
| From date | Date input | Sends `observed_from` as start of day. |
| To date | Date input | Sends `observed_to` as end of day. |
| Province | Searchable datalist input | Sends `province`; resets kabupaten and kecamatan when changed. |
| Kota/kabupaten | Searchable datalist input | Sends `kabupaten`; enabled after province selection; resets kecamatan when changed. |
| Kecamatan | Searchable datalist input | Sends `kecamatan`; enabled after kabupaten selection. |
| Satellites | Toggle buttons | Sends repeated `satellite` query parameters. |

When no satellite is selected, the frontend returns empty hotspot/statistics/trend responses locally instead of querying the API.

## Rails and Panels

The right rail is hidden by default. It contains:

1. Status counts by satellite and source-file status.
2. Latest ingestion run per satellite.
3. Latest two source files per satellite.

The bottom rail is hidden by default. It contains:

1. A stacked bar chart.
2. A daily trend line chart.

Both rails are controlled from the map toolbar.

## Statistics Chart

The stacked bar chart uses `/statistics`.

Grouping level depends on administrative selection:

| Selection | Chart grouping |
| --- | --- |
| no province | hotspots by province |
| province | hotspots by kota/kabupaten |
| kota/kabupaten | hotspots by kecamatan |
| kecamatan | hotspots by satellite |

Bars are stacked by selected satellites and show values for each chart row.

## Daily Trend Chart

The line chart uses `/trend`.

It shows:

- one line per selected satellite
- one total line
- daily counts for the current filter range

The chart uses the same filters as the map and statistics panel.

## GeoJSON Export

The GeoJSON export button downloads the current `hotspots` payload from frontend state. The payload is limited by the API request limit, but includes the API `total` value for the actual filtered count.

Use the API directly for complete data extraction when the filtered count is greater than the returned feature limit.

## Local Development

Install dependencies:

```bash
npm --prefix frontend install
```

Run the Vite dev server:

```bash
VITE_HOTSPOT_API_BASE=http://localhost:8000/api/v1 npm --prefix frontend run dev
```

Build the frontend:

```bash
npm --prefix frontend run build
```

Build the Docker image:

```bash
docker compose build frontend
```

Run the frontend service:

```bash
docker compose up -d frontend
```

Run API and frontend together:

```bash
docker compose up --build db api frontend
```

## Production Notes

- Rebuild the frontend image after frontend code or asset changes.
- Restart the frontend container after rebuilding if it is already running.
- Keep API and frontend versions aligned because TypeScript types mirror API response schemas.
- The frontend currently requests at most 2000 hotspot features for map display; use API `total` for the actual filtered count.
- ESRI World Imagery is a basemap only. Actual source-scene overlays require future backend raster tile serving and frontend scene-layer controls.

## Verification

Use these checks before handing off frontend changes:

```bash
npm --prefix frontend run build
docker compose build frontend
```

For visual changes, run the stack and inspect:

```bash
docker compose up -d db api frontend
```

Open:

```text
http://localhost:8080
```
