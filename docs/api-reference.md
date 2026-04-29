# API Reference

The BRIN Hotspot API is a read-only FastAPI service for downstream systems and the frontend dashboard.

Base URL in Docker Compose:

```text
http://localhost:8000/api/v1
```

Frontend proxy path:

```text
http://localhost:8080/api/v1
```

Generated API documentation:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI schema: `http://localhost:8000/openapi.json`

## Common Query Parameters

Hotspot, statistics, and trend endpoints share the same filtering model.

| Parameter | Type | Description |
| --- | --- | --- |
| `kind` | `cluster` or `pixel` | Select cluster or individual pixel records. Default: `cluster`. |
| `satellite` | repeatable string | Satellite filter. Example: `satellite=snpp&satellite=noaa20`. |
| `observed_from` | ISO datetime | Inclusive observation start time. |
| `observed_to` | ISO datetime | Inclusive observation end time. |
| `min_confidence` | integer `0..9` | Minimum confidence level. |
| `province` | string | Case-insensitive province match. |
| `kabupaten` | string | Case-insensitive kota/kabupaten match. |
| `kecamatan` | string | Case-insensitive kecamatan match. |

The frontend date controls are date-only. It converts dates into full-day API ranges:

- from date: `YYYY-MM-DDT00:00:00`
- to date: `YYYY-MM-DDT23:59:59`

## `GET /health`

Returns API health status.

Example:

```bash
curl http://localhost:8000/api/v1/health
```

Response:

```json
{
  "status": "ok",
  "service": "brin-hotspot-api"
}
```

## `GET /summary`

Returns operational summary counts per satellite and source-file status counts.

Example:

```bash
curl http://localhost:8000/api/v1/summary
```

Response fields:

| Field | Description |
| --- | --- |
| `generated_at` | Timestamp when the response was generated. |
| `satellites` | Per-satellite cluster, pixel, enriched-pixel, and latest observation totals. |
| `source_statuses` | Per-satellite source-file status counts. |

## `GET /hotspots`

Returns a GeoJSON FeatureCollection of hotspot clusters or pixels.

Additional query parameters:

| Parameter | Type | Description |
| --- | --- | --- |
| `bbox` | `west,south,east,north` | Optional bounding box filter in EPSG:4326. |
| `limit` | integer `1..5000` | Maximum returned features. Default: `1000`. |

Example:

```bash
curl "http://localhost:8000/api/v1/hotspots?kind=cluster&satellite=snpp&satellite=noaa20&min_confidence=7&limit=1000"
```

Filtered example:

```bash
curl "http://localhost:8000/api/v1/hotspots?kind=pixel&satellite=snpp&observed_from=2026-04-24T00:00:00&observed_to=2026-04-24T23:59:59&province=Riau&kabupaten=Pelalawan"
```

Response:

```json
{
  "type": "FeatureCollection",
  "total": 12345,
  "features": [
    {
      "type": "Feature",
      "id": "cluster-1001",
      "geometry": {
        "type": "Point",
        "coordinates": [101.24, -0.62]
      },
      "properties": {
        "cid": 1001,
        "kind": "cluster",
        "satellite": "snpp",
        "confidence": 8,
        "province": "Riau",
        "kabupaten": "Pelalawan",
        "kecamatan": "Pangkalan Kerinci",
        "radius_meters": 375,
        "source_station": "parepare",
        "observed_at": "2026-04-24T05:43:59+07:00",
        "source_file": "/app/data/input/snpp/example.txt",
        "scene_id": "20260424T054359"
      }
    }
  ]
}
```

`total` is the actual filtered count in the database. It may be greater than `features.length` because `limit` controls the returned payload size.

## `GET /statistics`

Returns grouped hotspot totals for stacked bar charts.

Additional query parameters:

| Parameter | Type | Description |
| --- | --- | --- |
| `limit` | integer `1..50` | Maximum returned groups. Default: `20`. |

Grouping is selected automatically from administrative filters:

| Active filter | Grouping level |
| --- | --- |
| no `province` | province |
| `province` | kota/kabupaten |
| `kabupaten` | kecamatan |
| `kecamatan` | satellite |

Example:

```bash
curl "http://localhost:8000/api/v1/statistics?kind=cluster&satellite=snpp&satellite=noaa20&province=Riau"
```

Response:

```json
{
  "level": "kabupaten",
  "items": [
    {
      "label": "Pelalawan",
      "total": 128,
      "satellites": {
        "snpp": 80,
        "noaa20": 48
      }
    }
  ]
}
```

## `GET /trend`

Returns daily hotspot counts for the selected filters.

Example:

```bash
curl "http://localhost:8000/api/v1/trend?kind=cluster&satellite=snpp&satellite=noaa20&observed_from=2026-04-24T00:00:00&observed_to=2026-04-27T23:59:59"
```

Response:

```json
{
  "items": [
    {
      "date": "2026-04-24",
      "total": 300,
      "satellites": {
        "snpp": 180,
        "noaa20": 120
      }
    }
  ]
}
```

## `GET /runs`

Returns ingestion run records.

Query parameters:

| Parameter | Type | Description |
| --- | --- | --- |
| `satellite` | string | Optional satellite filter. |
| `status` | string | Optional run status filter. |
| `limit` | integer `1..200` | Maximum records. Default: `50`. |

Example:

```bash
curl "http://localhost:8000/api/v1/runs?satellite=snpp&limit=20"
```

## `GET /source-files`

Returns source-file checkpoint records.

Query parameters:

| Parameter | Type | Description |
| --- | --- | --- |
| `satellite` | string | Optional satellite filter. |
| `status` | string | Optional source-file status filter. |
| `limit` | integer `1..200` | Maximum records. Default: `50`. |

Example:

```bash
curl "http://localhost:8000/api/v1/source-files?status=failed&limit=20"
```

## `GET /locations`

Returns province, kota/kabupaten, and kecamatan options used by the frontend filters.

Query parameters:

| Parameter | Type | Description |
| --- | --- | --- |
| `province` | string | Restricts returned kota/kabupaten and kecamatan options. |
| `kabupaten` | string | Restricts returned kecamatan options. |

Example:

```bash
curl "http://localhost:8000/api/v1/locations?province=Riau&kabupaten=Pelalawan"
```

Response:

```json
{
  "provinces": ["Aceh", "Riau"],
  "kabupaten": ["Pelalawan", "Siak"],
  "kecamatan": ["Pangkalan Kerinci"]
}
```

## Developer Integration Notes

- Use repeated `satellite` query parameters for multi-satellite filters.
- Use `/openapi.json` as the source of truth for client generation.
- Treat API responses as read-only operational views.
- Use `total` from `/hotspots` for visible-count UI; do not assume `features.length` is the complete filtered count.
- Use `/statistics` for grouped bar charts instead of grouping `/hotspots` client-side.
- Use `/trend` for daily time-series charts instead of deriving time series from limited map features.
