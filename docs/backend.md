# Backend Documentation

This document describes the backend services, command line tools, database model, ingestion workflow, API layer, configuration, and operational commands for BRIN Hotspot Modernization.

## Backend Responsibilities

The backend is responsible for turning satellite hotspot source files into queryable operational data. Its main responsibilities are:

- Discover source files for SNPP, NOAA20, AQUA, TERRA, and Landsat 8.
- Parse satellite-specific hotspot products into a shared detection model.
- Enrich detections with province, kota/kabupaten, and kecamatan reference polygons.
- Filter persistent anomalies and duplicate detections when enrichment/database mode is enabled.
- Cluster detections using satellite-specific spatial settings.
- Export cluster and pixel CSV files.
- Persist pixels, clusters, source-file checkpoints, ingestion runs, reference data, and raster metadata into PostgreSQL/PostGIS.
- Expose read-only data access through FastAPI.
- Run continuous ingestion through a worker loop.

## Source Layout

| Path | Responsibility |
| --- | --- |
| `src/brin_hotspot/cli.py` | Typer command line entry point for health checks, ingestion, admin, database, raster, worker, and API serving commands. |
| `src/brin_hotspot/config.py` | Runtime settings loaded from environment variables and `.env`. |
| `src/brin_hotspot/db.py` | Database connection checks. |
| `src/brin_hotspot/domain.py` | Shared domain models used by ingestion and persistence. |
| `src/brin_hotspot/migrations.py` | Migration runner for hotspot and raster databases. |
| `src/brin_hotspot/logging_config.py` | Structured logging setup. |
| `src/brin_hotspot/satellites/` | Satellite-specific discovery and parsing logic. |
| `src/brin_hotspot/ingestion/` | Shared ingestion orchestration, per-satellite wrappers, clustering, source-file handling, and CSV export. |
| `src/brin_hotspot/repositories/` | Database persistence and operational repositories. |
| `src/brin_hotspot/api/` | FastAPI app, response schemas, and read-only query repository. |
| `src/brin_hotspot/raster.py` | Raster discovery, footprint extraction, and tile generation. |
| `src/brin_hotspot/worker.py` | One-shot and repeated ingestion cycles. |
| `tools/modis_converter/convert_modis_hdf.py` | MODIS HDF4 to neutral CSV converter used by the converter sidecar. |

## Services

The backend is deployed through Docker Compose.

| Service | Image source | Purpose |
| --- | --- | --- |
| `db` | `postgis/postgis:16-3.4` | PostgreSQL/PostGIS databases for hotspot and raster data. |
| `worker` | `Dockerfile` | One-shot command container, defaulting to `hotspot health`. |
| `worker-service` | `Dockerfile` | Long-running ingestion loop for SNPP, NOAA20, and AQUA. |
| `api` | `Dockerfile` | FastAPI read-only data service. |
| `modis-converter` | `Dockerfile.modis-converter` | One-shot MODIS HDF4 conversion. |
| `modis-converter-service` | `Dockerfile.modis-converter` | Long-running AQUA converter loop. |

Start the core dissemination stack:

```bash
docker compose up --build db api frontend
```

Start ingestion services:

```bash
docker compose --profile service up -d modis-converter-service worker-service
```

Stop ingestion services:

```bash
docker compose --profile service stop worker-service modis-converter-service
```

Stop all services without deleting database volumes:

```bash
docker compose down
```

## Configuration

Backend configuration comes from environment variables and optional `.env`.

| Variable | Default | Description |
| --- | --- | --- |
| `HOTSPOT_ENV` | `development` | Runtime environment label. |
| `HOTSPOT_LOG_LEVEL` | `INFO` | Python logging level. |
| `HOTSPOT_LOG_FORMAT` | `json` | Log format. |
| `HOTSPOT_DB_HOST` | `localhost` locally, `db` in Compose | Hotspot database host. |
| `HOTSPOT_DB_PORT` | `5432` | Hotspot database port. |
| `HOTSPOT_DB_NAME` | `hotspot` | Hotspot database name. |
| `HOTSPOT_DB_USER` | `hotspot` | Hotspot database user. |
| `HOTSPOT_DB_PASSWORD` | `hotspot_dev` | Hotspot database password. |
| `HOTSPOT_RASTER_DB_NAME` | `raster` | Raster metadata database name. |
| `HOTSPOT_INPUT_DIR` | `data/input` locally, `/app/data/input` in Compose | Root input directory. |
| `HOTSPOT_OUTPUT_DIR` | `data/output` locally, `/app/data/output` in Compose | Output directory for CSV and derived products. |
| `HOTSPOT_LOG_DIR` | `logs` locally, `/app/logs` in Compose | Log directory. |
| `HOTSPOT_API_PORT` | `8000` | Host port for API service. |
| `HOTSPOT_FRONTEND_PORT` | `8080` | Host port for frontend service. |
| `HOTSPOT_WORKER_INTERVAL_SECONDS` | `300` | Worker-service polling interval. |
| `HOTSPOT_WORKER_MAX_CYCLES` | `0` | Worker-service cycle count. `0` means run forever. |
| `MODIS_CONVERTER_INTERVAL_SECONDS` | `300` | Converter-service polling interval. |

Check sanitized runtime configuration:

```bash
hotspot config
```

## Database Model

The hotspot database stores operational state and geospatial hotspot products.

| Table | Purpose |
| --- | --- |
| `hotspot_pixel` | Individual hotspot detections with coordinates, confidence, satellite, source metadata, and administrative enrichment fields. |
| `hotspot_cluster` | Clustered hotspot groups derived from filtered pixels. |
| `source_files` | Source-file checkpoints with satellite, path, scene id, observed time, status, timestamps, and last error. |
| `ingestion_runs` | Ingestion command or worker-cycle run history. |
| `prov_ar` | Province reference polygons. |
| `kab_kota_ar` | Kota/kabupaten reference polygons. |
| `kec_ar` | Kecamatan reference polygons. |
| `persistent_anomaly_ar` | Persistent anomaly polygons used for filtering. |

The raster database stores raster metadata and footprints for future scene-overlay and tile workflows.

Apply migrations:

```bash
docker compose run --rm worker hotspot db migrate
```

Check source-file status:

```bash
docker compose exec db psql -U hotspot -d hotspot -c "
select satellite, status, count(*)
from source_files
group by satellite, status
order by satellite, status;
"
```

## Source-File Checkpointing

Checkpointing is database-backed and lives in `source_files`.

Common statuses:

| Status | Meaning |
| --- | --- |
| `pending` | File is known and ready to process. |
| `running` | File is currently being processed. |
| `completed` | File has completed successfully and will be skipped in later database-backed runs. |
| `failed` | File failed and can be inspected or replayed. |

The ingestion flow marks each source item independently:

1. Discover candidate source files.
2. Skip files already marked `completed`.
3. Reset stale `running` files to `pending` at ingestion startup.
4. Mark the current source file as `running`.
5. Parse, normalize, enrich, filter, cluster, export, and persist.
6. Mark the source file `completed` after persistence succeeds.
7. Mark the source file `failed` if processing raises an error.

A valid source file whose detections are fully removed by filtering is still marked `completed`. This prevents endless replay of files that were processed correctly.

Replay one source:

```bash
docker compose run --rm worker hotspot admin replay-source \
  --satellite snpp \
  --path /app/data/input/snpp/path/to/source.txt
```

Replay a satellite by previous status:

```bash
docker compose run --rm worker hotspot admin replay-satellite --satellite snpp --status completed
docker compose run --rm worker hotspot admin replay-satellite --satellite snpp --status failed
```

Reset interrupted files:

```bash
docker compose run --rm worker hotspot admin reset-running
```

## Ingestion Workflow

The shared ingestion engine is used by every satellite family. Satellite-specific modules only handle discovery and parsing.

1. Discover source items.
2. Parse detections into a common hotspot pixel model.
3. Optionally enrich pixels with PostGIS reference polygons.
4. Optionally filter persistent anomalies and duplicates.
5. Cluster remaining pixels.
6. Write CSV outputs.
7. Optionally persist pixels and clusters to PostGIS.
8. Update source-file and ingestion-run status.

Run ingestion without persistence:

```bash
hotspot ingest snpp --input-dir data/input/snpp
```

Run ingestion with persistence and enrichment:

```bash
hotspot ingest snpp --input-dir data/input/snpp --database --enrich
hotspot ingest noaa20 --input-dir data/input/noaa20 --database --enrich
hotspot ingest aqua --input-dir data/output/modis-converted/aqua --database --enrich
```

`--enrich` requires `--database` because enrichment, anomaly filtering, duplicate filtering, and source-file checkpointing depend on PostGIS.

## Satellite Inputs

| Satellite | Supported input | Notes |
| --- | --- | --- |
| SNPP | `AFIMG_npp*.txt` | VIIRS text products. |
| NOAA20 | `AFIMG_j01*.txt` | VIIRS text products. |
| AQUA | `a1*.mod14.hdf`, `a1*.mod14.hotspots.csv` | MODIS HDF4 or converted CSV. Worker-service reads converted CSV. |
| TERRA | `t1*.mod14.hdf`, `t1*.mod14.hotspots.csv` | MODIS HDF4 or converted CSV. |
| Landsat 8 | `LC08*firepixels.txt`, `LO08*firepixels.txt` | Fire-pixel text files grouped by acquisition date and WRS path. |

## MODIS Converter

The main Python runtime avoids direct HDF4 dependency complexity by using a converter sidecar for MODIS files.

One-shot conversion:

```bash
docker compose run --rm modis-converter \
  --input-dir /app/data/input/aqua \
  --output-dir /app/data/output/modis-converted/aqua \
  --satellite aqua \
  --skip-existing
```

Service mode:

```bash
docker compose --profile service up -d modis-converter-service
```

The converter writes `*.mod14.hotspots.csv` files. Header-only CSV files are produced for valid MODIS granules with no fire pixels. Output replacement is atomic so the worker does not ingest half-written files.

## Reference Data

Reference polygons are imported from GeoJSON.

```bash
hotspot admin import-geojson province \
  --file data/reference/provinces.geojson \
  --id-field gid \
  --name-field wa

hotspot admin import-geojson kabupaten \
  --file data/reference/kabupaten.geojson \
  --id-field gid \
  --name-field wa \
  --prov-id-field prov_id

hotspot admin import-geojson kecamatan \
  --file data/reference/kecamatan.geojson \
  --id-field gid \
  --name-field wa \
  --prov-id-field prov_id \
  --kab-id-field kab_id
```

After importing or changing reference data, replay completed sources for the affected satellite to backfill enrichment fields:

```bash
hotspot admin replay-satellite --satellite snpp --status completed
hotspot ingest snpp --input-dir data/input/snpp --database --enrich
```

## Raster Metadata

Raster commands are separate from hotspot ingestion.

Scan rasters:

```bash
hotspot raster scan --input-dir data/input/rasters
hotspot raster scan --input-dir data/input/rasters --database
```

Generate XYZ tiles:

```bash
hotspot raster tile --input-dir data/input/rasters --output-dir data/output/tiles --zoom 5-12
```

Raster support currently indexes metadata and can generate tiles. Loading actual source scenes as map overlays requires scene indexing and tile-serving integration beyond the current frontend basemap switcher.

## API Layer

The API is implemented with FastAPI in `src/brin_hotspot/api/app.py`.

Serve locally:

```bash
hotspot serve --host 0.0.0.0 --port 8000
```

Serve through Docker Compose:

```bash
docker compose up --build api
```

API documentation is generated automatically:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

The API is read-only. It does not expose mutation endpoints for ingestion, replay, reference import, or administrative database operations.

See [API Reference](api-reference.md) for endpoint details.

## Worker Operations

Run one ingestion cycle:

```bash
hotspot worker run-once --database --enrich
```

Run one satellite:

```bash
hotspot worker run-once --satellite noaa20 --database --enrich
```

Run a continuous loop:

```bash
hotspot worker loop \
  --satellite snpp \
  --satellite noaa20 \
  --satellite aqua \
  --input aqua=/app/data/output/modis-converted/aqua \
  --interval-seconds 300 \
  --max-cycles 0 \
  --database \
  --enrich
```

`--max-cycles 0` means run forever. Use a positive value for smoke tests.

## Testing

Run the backend test suite:

```bash
pytest -q
```

Run linting:

```bash
ruff check .
```

Run a Docker health check:

```bash
docker compose run --rm worker hotspot health --database
```
