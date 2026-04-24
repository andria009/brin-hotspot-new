# BRIN Hotspot Modernization

Modernized hotspot processing workspace for the BRIN/LAPAN Indonesia fire detection pipeline.

This project is intentionally separate from the legacy `hotspot` folder. The legacy folder remains the reference implementation while this workspace adds a reproducible runtime, isolated configuration, traceable logs, and a cleaner ingestion architecture.

## What Has Been Implemented

- Python 3.14 target runtime.
- Docker Compose development stack using generic Python and PostgreSQL/PostGIS images.
- Environment-based configuration through `.env` / `HOTSPOT_*` variables.
- Structured JSON logs with traceable `run_id` values.
- PostgreSQL/PostGIS schema initialization for hotspot, source-file, ingestion-run, reference-boundary, anomaly, and raster metadata tables.
- Versioned schema migration runner for hotspot and raster databases.
- CLI health and sanitized configuration commands.
- Shared hotspot ingestion engine for parsing, enrichment, clustering, CSV export, idempotency, and persistence.
- SNPP and NOAA20 VIIRS text ingestion.
- AQUA and TERRA MODIS HDF fire-pixel ingestion.
- Landsat 8 `firepixels.txt` ingestion with grouped scene handling.
- Admin/reference GeoJSON importer for province, kabupaten, kecamatan, and persistent anomaly polygons.
- PostGIS enrichment using administrative boundaries.
- Persistent-anomaly filtering.
- Duplicate hotspot filtering using satellite-specific spatial buffers and +/- 10 minute observation windows.
- Operational admin commands for run/source status and source-file replay.
- Raster metadata scanner for GeoTIFF footprint registration.
- Raster tile generation wrapper using `gdal2tiles.py`.
- Worker orchestration commands for one-shot and repeated ingestion cycles.
- Unit tests for configuration, clustering, parsing, reference import, geospatial enrichment, raster parsing, migrations, and ingestion flows.

## Supported Inputs

| Command | Input Type | Notes |
| --- | --- | --- |
| `hotspot ingest snpp` | `AFIMG_npp*.txt` | VIIRS text hotspot files. |
| `hotspot ingest noaa20` | `AFIMG_j01*.txt` | VIIRS text hotspot files. |
| `hotspot ingest aqua` | `a1*.mod14.hdf` | MODIS HDF fire-pixel files. |
| `hotspot ingest terra` | `t1*.mod14.hdf` | MODIS HDF fire-pixel files. |
| `hotspot ingest landsat8` | `LC08*firepixels.txt`, `LO08*firepixels.txt` | Grouped by acquisition date and WRS path. |

MODIS HDF parsing requires `pyhdf` in runtime environments that process real AQUA/TERRA HDF4 files. The parser imports `pyhdf` lazily so the rest of the CLI and tests remain usable without HDF4 support installed.

The Docker image installs GDAL and compatible HDF4 native libraries. To try installing the optional Python `pyhdf` package during image build, use:

```bash
docker compose build --build-arg INSTALL_HDF=true worker
```

Current Python 3.14 status: the optional HDF build reaches native compilation but fails inside the upstream `pyhdf` C wrapper against the current Debian/HDF4 headers. Real AQUA/TERRA HDF ingestion is therefore ported at the application layer but still needs a Python 3.14-compatible HDF4 reader strategy before production use.

## Architecture

The modernized code separates satellite-specific parsing from shared ingestion behavior:

- `src/brin_hotspot/satellites/`: filename discovery and parser logic for each input family.
- `src/brin_hotspot/ingestion/hotspot.py`: shared ingestion orchestration.
- `src/brin_hotspot/ingestion/clustering.py`: connected-neighbor clustering.
- `src/brin_hotspot/ingestion/csv_export.py`: cluster and pixel CSV outputs.
- `src/brin_hotspot/repositories/`: PostGIS persistence, enrichment, and reference-data import.
- `src/brin_hotspot/migrations.py`: versioned schema migration execution.
- `src/brin_hotspot/raster.py`: GeoTIFF discovery, footprint extraction, and tile command execution.
- `src/brin_hotspot/worker.py`: scheduled ingestion loop and one-shot ingestion cycle dispatch.
- `src/brin_hotspot/config.py`: separated runtime configuration.
- `src/brin_hotspot/logging_config.py`: structured logging setup.

The shared ingestion flow is:

1. Discover input source files.
2. Skip already-completed source files when database persistence is enabled.
3. Parse satellite-specific detections.
4. Optionally enrich detections with PostGIS administrative boundaries.
5. Optionally filter persistent anomalies and duplicate pixels.
6. Cluster detections using satellite-specific resolution rules.
7. Write cluster and pixel CSV outputs.
8. Optionally persist clusters, pixels, source-file status, and ingestion-run status into PostGIS.

## Local Python

If using the prepared pyenv virtual environment:

```bash
pyenv activate hotspot
python -m pip install -e ".[dev]"
hotspot --help
```

Run checks:

```bash
pytest
ruff check .
```

## Docker

OrbStack can run the Docker Compose stack:

```bash
docker compose up --build
```

Run a health check through the worker:

```bash
docker compose run --rm worker hotspot health
```

Check database connectivity:

```bash
docker compose run --rm worker hotspot health --database
```

Apply schema migrations:

```bash
docker compose run --rm worker hotspot db migrate
```

Stop the stack without deleting the database volume:

```bash
docker compose down
```

## Ingestion Commands

Run SNPP ingestion:

```bash
hotspot ingest snpp --input-dir data/input/snpp
```

Persist parsed SNPP clusters and pixels into PostGIS:

```bash
hotspot ingest snpp --input-dir data/input/snpp --database
```

Apply PostGIS admin-boundary enrichment plus persistent-anomaly and duplicate filtering:

```bash
hotspot ingest snpp --input-dir data/input/snpp --database --enrich
```

Run NOAA20 ingestion:

```bash
hotspot ingest noaa20 --input-dir data/input/noaa20
hotspot ingest noaa20 --input-dir data/input/noaa20 --database --enrich
```

Run AQUA and TERRA MODIS ingestion:

```bash
hotspot ingest aqua --input-dir data/input/aqua
hotspot ingest terra --input-dir data/input/terra
```

Run Landsat 8 ingestion:

```bash
hotspot ingest landsat8 --input-dir data/input/landsat8
hotspot ingest landsat8 --input-dir data/input/landsat8 --database --enrich
```

## Operational Admin

List recent ingestion runs:

```bash
hotspot admin runs --limit 20
hotspot admin runs --satellite snpp --status completed
```

List source-file status:

```bash
hotspot admin sources --limit 20
hotspot admin sources --satellite landsat8 --status completed
```

Replay a source file by marking it pending:

```bash
hotspot admin replay-source --satellite snpp --path data/input/snpp/2026/04/24/054359000/AFIMG_npp_d20260424_t0543590_e0550000.txt
```

The next `hotspot ingest ... --database` run will process a replayed source again because only `completed` source files are skipped.

## Raster Metadata

Scan GeoTIFF fire-index rasters and derive footprints with `gdalinfo`:

```bash
hotspot raster scan --input-dir data/input/rasters
```

Persist raster metadata into the raster PostGIS database:

```bash
hotspot raster scan --input-dir data/input/rasters --database
```

Supported raster filename families include `SNPP_*_FI.tif`, `NOAA20_*_FI.tif`, `AQUA_*_FI.tif`, `TERRA_*_FI.tif`, and `L8_*_FI.tif`.

Generate XYZ web tiles for discovered rasters:

```bash
hotspot raster tile --input-dir data/input/rasters --output-dir data/output/tiles --zoom 5-12
```

Tiles are written under one directory per raster source file. Existing tiles are resumed by GDAL, so interrupted tile jobs can be run again.

## Worker

Run one ingestion cycle across all enabled satellite families:

```bash
hotspot worker run-once --database --enrich
```

Limit a cycle to a specific satellite:

```bash
hotspot worker run-once --satellite noaa20 --database --enrich
```

Run a repeated worker loop:

```bash
hotspot worker loop --interval-seconds 300 --database --enrich
```

The worker uses the same source-file idempotency tables as direct ingestion commands, so completed database-backed files are skipped unless they are explicitly replayed.

## Reference Data

Import reference polygons from GeoJSON:

```bash
hotspot admin import-geojson province --file data/reference/provinces.geojson --id-field gid --name-field wa
hotspot admin import-geojson kabupaten --file data/reference/kabupaten.geojson --id-field gid --name-field wa --prov-id-field prov_id
hotspot admin import-geojson kecamatan --file data/reference/kecamatan.geojson --id-field gid --name-field wa --prov-id-field prov_id --kab-id-field kab_id
hotspot admin import-geojson anomaly --file data/reference/anomalies.geojson --id-field gid --name-field name
```

Reference GeoJSON files must be valid `FeatureCollection` documents. Imported geometries are stored as `MultiPolygon` SRID 4326 geometries.

## Configuration

Copy `.env.example` to `.env` and adjust values for the local environment.

No credentials should be committed to this repository.

## Verification Status

The current implementation has been verified with:

```bash
PYENV_VERSION=hotspot pytest -o cache_dir=/tmp/hotspot-new-pytest-cache
PYENV_VERSION=hotspot RUFF_CACHE_DIR=/tmp/hotspot-new-ruff-cache ruff check .
docker compose build worker
docker compose run --rm worker hotspot db migrate
docker compose run --rm worker hotspot health --database
docker compose run --rm --volume /path/to/hotspot-new/tests:/app/tests:ro worker hotspot ingest landsat8 --input-dir /app/tests/fixtures/landsat8 --database --enrich
docker compose run --rm --volume /path/to/hotspot-new/tests:/app/tests:ro --env HOTSPOT_INPUT_DIR=/app/tests/fixtures worker hotspot worker run-once --satellite noaa20 --no-database
docker compose run --rm worker hotspot admin runs --limit 5
docker compose run --rm worker hotspot admin sources --limit 5
docker compose run --rm --volume /path/to/hotspot-new/tests:/app/tests:ro worker hotspot raster scan --input-dir /app/tests --no-database
docker compose run --rm --volume /path/to/hotspot-new/tests:/app/tests:ro worker hotspot raster tile --input-dir /app/tests --output-dir /tmp/hotspot-tiles --zoom 5
```

Latest local result:

- `pytest`: 33 passed.
- `ruff check .`: passed.
- Docker worker image rebuilt successfully.
- Docker migrations applied successfully and then skipped on repeat.
- Docker/PostGIS Landsat 8 persistence smoke passed.
- Docker NOAA20 worker smoke passed.
- Docker admin run/source status commands passed.
- Docker raster scanner smoke passed.
- Docker raster tile smoke passed on an empty fixture tree.
- Optional Docker HDF build failed at `pyhdf` native compilation under Python 3.14, after HDF4 libraries and `gcc` were installed.
- Docker Compose stack was shut down afterward with `docker compose down`.

## What Is Next

- Resolve the Python 3.14 MODIS HDF reader blocker by patching or replacing `pyhdf`, pinning a compatible build image for HDF conversion, or isolating MODIS HDF extraction in a sidecar converter.
- Add real sample fixtures for AQUA/TERRA HDF files once available, then run end-to-end parse and PostGIS persistence smoke tests for both.
- Add a real GeoTIFF fixture and assert generated tile output beyond the current command/smoke coverage.
- Add operational observability around log retention and alerting/failure summaries.
