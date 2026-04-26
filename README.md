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
- Shared hotspot ingestion engine for parsing, enrichment, clustering, CSV export, idempotency, and per-source persistence.
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
- Worker orchestration commands and a Docker Compose service profile for one-shot and repeated ingestion cycles.
- MODIS HDF4 conversion sidecar that keeps legacy HDF dependencies outside the Python 3.14 worker.
- Unit tests for configuration, clustering, parsing, reference import, geospatial enrichment, raster parsing, migrations, and ingestion flows.

## Supported Inputs

| Command | Input Type | Notes |
| --- | --- | --- |
| `hotspot ingest snpp` | `AFIMG_npp*.txt` | VIIRS text hotspot files. |
| `hotspot ingest noaa20` | `AFIMG_j01*.txt` | VIIRS text hotspot files. |
| `hotspot ingest aqua` | `a1*.mod14.hdf`, `a1*.mod14.hotspots.csv` | MODIS fire-pixel files. Converted CSV is preferred when both exist. |
| `hotspot ingest terra` | `t1*.mod14.hdf`, `t1*.mod14.hotspots.csv` | MODIS fire-pixel files. Converted CSV is preferred when both exist. |
| `hotspot ingest landsat8` | `LC08*firepixels.txt`, `LO08*firepixels.txt` | Grouped by acquisition date and WRS path. |

MODIS HDF parsing requires `pyhdf` in runtime environments that process real AQUA/TERRA HDF4 files. The parser imports `pyhdf` lazily so the rest of the CLI and tests remain usable without HDF4 support installed.

The Docker image installs GDAL and compatible HDF4 native libraries. To try installing the optional Python `pyhdf` package during image build, use:

```bash
docker compose build --build-arg INSTALL_HDF=true worker
```

Current Python 3.14 status: the optional HDF build reaches native compilation but fails inside the upstream `pyhdf` C wrapper against the current Debian/HDF4 headers. To keep the main application on Python 3.14, raw HDF4 conversion is isolated in a `modis-converter` sidecar image that writes neutral CSV files for the main ingestion pipeline.

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
7. Write cluster and pixel CSV outputs for each source item.
8. Optionally persist each source item independently into PostGIS.
9. Mark each source file `completed` only after its clusters and pixels are stored.

This source-level checkpointing is important for operational runs. If a long ingestion is interrupted, files already marked `completed` are skipped on the next run, stale `running` files are reset to `pending`, and remaining or failed files can be retried without replaying the whole tree.

## Hotspot Detection Process

SNPP and NOAA20 use the same VIIRS active-fire text flow:

1. The worker scans each real input tree recursively.
   - SNPP reads `AFIMG_npp*.txt`.
   - NOAA20 reads `AFIMG_j01*.txt`.
2. Each text file is treated as one source item. With database persistence enabled, the file is skipped when `source_files.status = completed`.
3. Observation time is derived from the production filename, for example `d20250101_t0407536`.
4. Each valid hotspot row is normalized into a common pixel record containing latitude, longitude, confidence, observed time, satellite, scene id, source station, and source file.
5. With `--enrich`, each pixel is matched against the imported PostGIS province, kabupaten, and kecamatan polygons. Pixels outside the imported boundary set remain valid hotspot pixels but keep null administrative fields.
6. Persistent anomaly filtering and duplicate filtering are applied when enrichment/database mode is enabled.
7. Remaining pixels are clustered using satellite-specific spatial resolution settings.
8. Cluster and pixel CSV files are written, then clusters and pixels are persisted to PostGIS. The source file is marked `completed` only after persistence succeeds.

AQUA uses a two-stage MODIS flow because production AQUA inputs are HDF4:

1. `modis-converter` or `modis-converter-service` scans raw AQUA HDF4 files recursively under `/app/data/input/aqua`.
2. It reads MOD14 fire-pixel datasets such as `FP_latitude`, `FP_longitude`, and `FP_confidence`.
3. Each HDF file is converted to a neutral `*.mod14.hotspots.csv` file under `/app/data/output/modis-converted/aqua`, preserving the relative input tree.
4. Empty MODIS granules become header-only CSV files. Failed granules are reported in converter logs and do not stop the whole conversion cycle.
5. The converter uses `--skip-existing` in service mode, so already converted files are not rewritten unless the source HDF is newer. Output replacement is atomic so the worker does not ingest half-written CSV files.
6. `worker-service` ingests AQUA from `/app/data/output/modis-converted/aqua`, not from the raw HDF directory.
7. AQUA converted CSV rows are normalized into the same common hotspot pixel model as VIIRS, then enrichment, filtering, clustering, CSV export, persistence, and source-file checkpointing use the shared ingestion engine.

Operationally, SNPP, NOAA20, and AQUA therefore converge into the same database model:

- `source_files` tracks whether each input file is `pending`, `running`, `completed`, or `failed`.
- `ingestion_runs` records each command or worker cycle run.
- `hotspot_pixel` stores individual detections.
- `hotspot_cluster` stores clustered hotspot groups.
- Administrative enrichment fields are updated on conflict, so replaying completed sources after reference-data import can backfill province, kabupaten, and kecamatan values.

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

If using raw MODIS HDF4 files, convert them first:

```bash
docker compose run --rm modis-converter --input-dir /app/data/input --output-dir /app/data/input
```

The converter writes `*.mod14.hotspots.csv` files next to the matching input tree. The main AQUA/TERRA ingestion commands prefer converted CSV files over matching raw HDF files, which avoids duplicate processing when both are present.

MODIS granules with no fire pixels are converted to header-only CSV files. Files that cannot be read are reported to stderr and do not stop the whole conversion run.

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

Replay completed files for a whole satellite, for example after importing reference data and wanting to rerun enrichment:

```bash
hotspot admin replay-satellite --satellite snpp --status completed
```

Reset interrupted `running` source files to `pending`:

```bash
hotspot admin reset-running --satellite snpp
```

Reset all interrupted `running` source files:

```bash
hotspot admin reset-running
```

Database-backed ingestion also resets stale `running` source files for the selected satellite at startup. This lets an interrupted service run continue on the next cycle without manual SQL.

Operational cleanup commands:

```bash
# Reset interrupted files before retrying a satellite.
docker compose run --rm worker hotspot admin reset-running --satellite snpp
docker compose run --rm worker hotspot admin reset-running --satellite noaa20
docker compose run --rm worker hotspot admin reset-running --satellite aqua

# Replay completed files after importing reference data or changing enrichment logic.
docker compose run --rm worker hotspot admin replay-satellite --satellite snpp --status completed
docker compose run --rm worker hotspot admin replay-satellite --satellite noaa20 --status completed
docker compose run --rm worker hotspot admin replay-satellite --satellite aqua --status completed

# Replay failed files after fixing parser/input issues.
docker compose run --rm worker hotspot admin replay-satellite --satellite snpp --status failed
```

Direct SQL checks are useful for cleanup decisions:

```bash
docker compose exec db psql -U hotspot -d hotspot -c "
select satellite, status, count(*)
from source_files
group by satellite, status
order by satellite, status;
"

docker compose exec db psql -U hotspot -d hotspot -c "
select satellite, status, count(*)
from ingestion_runs
group by satellite, status
order by satellite, status;
"
```

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

Use `--max-cycles 0` for a long-running service loop. `0` is the default for
`worker loop`; use a positive value for testing:

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

The worker uses the same source-file idempotency tables as direct ingestion commands. Completed database-backed files are skipped unless they are explicitly replayed, so the loop can safely revisit the same input folders and process newly-arrived files. `--input satellite=/path` overrides one satellite input directory, which is useful for AQUA/TERRA after HDF4 files have been converted to CSV by the MODIS converter sidecar.

Run the Docker Compose service profile:

```bash
docker compose --profile service up -d modis-converter-service worker-service
docker compose logs -f worker-service
docker compose --profile service stop worker-service modis-converter-service
```

The default service pair processes SNPP, NOAA20, and AQUA with enrichment enabled. `modis-converter-service` refreshes AQUA HDF4 files into `/app/data/output/modis-converted/aqua`, and `worker-service` ingests AQUA from that converted CSV directory. Add Terra later by adding a Terra converter service and editing the worker command after Terra source data is ready.

For production-style runs, mount each real satellite source directory directly:

```yaml
- /mnt/geomimo-data/DataProses/Suomi-NPP:/app/data/input/snpp:ro
- /mnt/geomimo-data/DataProses/NOAA-20:/app/data/input/noaa20:ro
- /mnt/geomimo-data/DataProses/AQUA:/app/data/input/aqua:ro
- /mnt/geomimo-data/DataProses/Terra:/app/data/input/terra:ro
```

Do not bind `./data/input:/app/data/input` at the same time for production ingestion. The local parent bind can create placeholder `snpp`, `noaa20`, `aqua`, and `terra` directories under `data/input`, which is confusing and can hide whether the container is reading the real `/mnt/geomimo-data` source.

Server workflow after code changes:

```bash
docker compose build worker
docker compose build modis-converter
docker compose run --rm worker hotspot health --database
docker compose run --rm worker hotspot admin reset-running
docker compose --profile service up -d modis-converter-service worker-service
```

Monitor the service:

```bash
docker compose ps
docker compose logs -f worker-service
docker compose logs -f modis-converter-service
docker compose exec db psql -U hotspot -d hotspot -c "
select satellite, status, count(*)
from source_files
group by satellite, status
order by satellite, status;
"
```

Stop or restart the service:

```bash
docker compose --profile service stop worker-service modis-converter-service
docker compose --profile service restart modis-converter-service worker-service
```

For a short service smoke test, override the cycle count:

```bash
HOTSPOT_WORKER_MAX_CYCLES=1 docker compose --profile service up worker-service
```

To smoke-test one converter cycle manually:

```bash
docker compose run --rm modis-converter \
  --input-dir /app/data/input/aqua \
  --output-dir /app/data/output/modis-converted/aqua \
  --satellite aqua \
  --skip-existing
```

The service is idempotent when `--database` is enabled: `completed` source files are skipped, interrupted `running` files are reset on startup, and newly-arrived files are processed on later cycles.

## Reference Data

Import reference polygons from GeoJSON:

```bash
hotspot admin import-geojson province --file data/reference/provinces.geojson --id-field gid --name-field wa
hotspot admin import-geojson kabupaten --file data/reference/kabupaten.geojson --id-field gid --name-field wa --prov-id-field prov_id
hotspot admin import-geojson kecamatan --file data/reference/kecamatan.geojson --id-field gid --name-field wa --prov-id-field prov_id --kab-id-field kab_id
hotspot admin import-geojson anomaly --file data/reference/anomalies.geojson --id-field gid --name-field name
```

Reference GeoJSON files must be valid `FeatureCollection` documents. Imported geometries are stored as `MultiPolygon` SRID 4326 geometries.

After reference data is imported, rerun ingestion with `--database --enrich`. Existing hotspot rows are updated with enriched administrative fields on conflict, so replaying completed source files can backfill province, kabupaten, and kecamatan values.

## Verification

Check application and database connectivity:

```bash
docker compose run --rm worker hotspot health --database
```

Check source-file progress:

```bash
docker compose exec db psql -U hotspot -d hotspot -c "
select satellite, status, count(*) as source_files
from source_files
group by satellite, status
order by satellite, status;
"
```

Check persisted pixels and enrichment coverage:

```bash
docker compose exec db psql -U hotspot -d hotspot -c "
select satellite,
       count(*) as pixels,
       count(provinsi) as with_province,
       count(kabupaten) as with_kabupaten,
       count(kecamatan) as with_kecamatan
from hotspot_pixel
group by satellite
order by satellite;
"
```

Check recent ingestion runs:

```bash
docker compose run --rm worker hotspot admin runs --limit 20
docker compose run --rm worker hotspot admin sources --limit 20
```

Check MODIS conversion output:

```bash
find data/output/modis-converted/aqua -type f -name '*.mod14.hotspots.csv' | wc -l
find data/output/modis-converted/aqua -type f -name '*.mod14.hotspots.csv' | head
```

Check worker-service logs and running containers:

```bash
docker compose ps
docker compose logs --tail 200 worker-service
docker compose logs --tail 200 modis-converter-service
```

## Configuration

Copy `.env.example` to `.env` and adjust values for the local environment.

No credentials should be committed to this repository.

## Verification Status

The current implementation has been verified with:

```bash
PYENV_VERSION=hotspot pytest -o cache_dir=/tmp/hotspot-new-pytest-cache
PYENV_VERSION=hotspot RUFF_CACHE_DIR=/tmp/hotspot-new-ruff-cache ruff check .
docker compose build worker
docker compose build modis-converter
docker compose run --rm modis-converter --input-dir /app/data/input --output-dir /app/data/output/modis-converted
docker compose run --rm worker hotspot db migrate
docker compose run --rm worker hotspot health --database
docker compose run --rm --volume /path/to/hotspot-new/tests:/app/tests:ro worker hotspot ingest aqua --input-dir /app/tests/fixtures/aqua --no-database
docker compose run --rm --volume /path/to/hotspot-new/tests:/app/tests:ro worker hotspot ingest landsat8 --input-dir /app/tests/fixtures/landsat8 --database --enrich
docker compose run --rm --volume /path/to/hotspot-new/tests:/app/tests:ro --env HOTSPOT_INPUT_DIR=/app/tests/fixtures worker hotspot worker run-once --satellite noaa20 --no-database
docker compose run --rm worker hotspot admin runs --limit 5
docker compose run --rm worker hotspot admin sources --limit 5
docker compose run --rm --volume /path/to/hotspot-new/tests:/app/tests:ro worker hotspot raster scan --input-dir /app/tests --no-database
docker compose run --rm --volume /path/to/hotspot-new/tests:/app/tests:ro worker hotspot raster tile --input-dir /app/tests --output-dir /tmp/hotspot-tiles --zoom 5
```

Latest local result:

- `pytest`: 47 passed.
- `ruff check .`: passed.
- Docker worker image rebuilt successfully.
- Docker MODIS converter image built successfully with `pyhdf` isolated on Python 3.12/bookworm.
- Docker MODIS converter empty-tree smoke passed.
- Docker AQUA converted CSV ingestion smoke passed.
- Real AQUA HDF4 conversion and converted AQUA ingestion were tested successfully with production-like data.
- Docker migrations applied successfully and then skipped on repeat.
- Docker/PostGIS Landsat 8 persistence smoke passed.
- Docker NOAA20 worker smoke passed.
- Docker admin run/source status commands passed.
- Docker raster scanner smoke passed.
- Docker raster tile smoke passed on an empty fixture tree.
- Optional main-worker HDF build failed at `pyhdf` native compilation under Python 3.14, after HDF4 libraries and `gcc` were installed.
- MODIS HDF conversion is now isolated in the `modis-converter` sidecar path; AQUA has been validated with real data, while TERRA still awaits ready source data.
- Docker Compose stack was shut down afterward with `docker compose down`.

## What Is Next

Priority validation:

- Finish current SNPP, NOAA20, and AQUA backfill ingestion with `--database --enrich`, then confirm source-file status and enrichment coverage.
- Get real TERRA HDF4 samples and use them to verify the `modis-converter` output against expected fire-pixel latitude, longitude, confidence, observation time, and source metadata.
- Add sanitized real AQUA converted CSV/HDF4 fixtures from the tested production sample, plus TERRA fixtures once available.
- Add a real GeoTIFF fire-index fixture and assert actual XYZ tile output, not only command construction and empty-tree smoke checks.
- Validate real province, kabupaten, kecamatan, and persistent-anomaly GeoJSON imports against the production schema and enrichment queries.
- Tune duplicate filtering buffers and clustering behavior using representative SNPP, NOAA20, AQUA/MODIS, and Landsat 8 data.

Operations:

- Validate the long-running `worker-service` against live SNPP, NOAA20, and converted AQUA folders after current backfill ingestion completes.
- Add operational checks for `worker-service` health, recent cycles, source-file failures, and enrichment coverage.
- Add Terra to `worker-service` after Terra source data and MODIS conversion output are ready.
- Add log retention and failure summary reporting around ingestion runs and source-file failures.
- Add backup/restore notes for the hotspot and raster PostgreSQL databases.
- Add environment-specific configuration examples for local, staging, and production deployments.

Developer experience:

- Add CI commands for lint, tests, Docker build, migration smoke checks, and a no-database ingestion smoke.
- Add a small fixture-generation guide so new sample inputs can be added without leaking production data.
- Consider a leaner Docker image or multi-stage build for the worker and MODIS converter images.
