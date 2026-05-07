# BRIN Hotspot Enhancement Plan

## Current Understanding

This repository contains a legacy hotspot processing pipeline for Indonesia fire detections. It ingests satellite hotspot products, filters and enriches them with administrative boundaries, stores pixel and cluster records in PostGIS, generates CSV outputs, creates map tiles from raster fire imagery, and sends notification emails.

Main subsystems:

- `Hotspot_sys`: hotspot ingestion for SNPP, NOAA20, Landsat-8, MODIS Aqua, and MODIS Tera.
- `Tile_sys`: GeoTIFF-to-tile generation and raster metadata registration.
- `L8_fireproduct`, `MODIS_fireproduct`, `VIIRS_fireproduct`: satellite fire product processing areas.
- `Notifikasi`: email notification and error notification scripts.
- `backup_hotspot.sql`: PostGIS schema and data dump for vector hotspot data.
- `backup_raster.sql`: PostGIS schema and data dump for raster footprint metadata.

## Modernization Direction

The preferred approach is stabilization and modernization, not a full rewrite at the start. The existing pipeline appears operational, so the first priority is preserving behavior while making the system safer, reproducible, observable, and easier to evolve.

## Target Runtime

- Python: 3.14
- PostgreSQL: modern supported version, preferably PostgreSQL 16 or newer after compatibility testing.
- PostGIS: version compatible with the selected PostgreSQL image.
- GDAL, PROJ, HDF, NumPy, SciPy, pyproj, psycopg, Pillow, OpenCV, and related geospatial libraries must be pinned and tested together.

Python 3.14 should be treated as the target application runtime. Geospatial dependencies need careful validation because GDAL, PROJ, HDF, and raster reprojection behavior can change across versions.

## Phase 1: Baseline Current Behavior

Before changing versions or runtime architecture:

- Capture representative sample inputs for each satellite.
- Record expected hotspot pixel inserts, cluster inserts, CSV outputs, and tile outputs.
- Document current cron schedules, file paths, mount points, and operational assumptions.
- Add smoke tests that compare field-level outputs for known samples.
- Keep production data dumps separate from clean schema definitions.

## Phase 2: Containerized Development Environment

Create a Docker Compose stack with:

- Postgres/PostGIS database service.
- Python worker image using Python 3.14.
- Mounted input, output, tile, CSV, and log directories.
- Optional static file service for generated tiles and CSVs.
- Environment-based configuration through `.env`.

The current separate `hotspot` and `raster` databases can either remain as two databases in the same container or be migrated into separate schemas in one database after review.

## Phase 3: Configuration And Secrets

- Move hardcoded database credentials, SMTP credentials, paths, and sensor constants into configuration.
- Use environment variables locally and a secrets manager or protected deployment variables in production.
- Create one shared configuration module for satellite settings, database DSNs, output paths, and processing parameters.

## Phase 4: Schema Cleanup

- Convert database dumps into migration files.
- Add missing relational constraints, especially `hotspot_pixel.cluster_id -> hotspot_cluster.cid`.
- Review and add spatial indexes for hotspot coordinates and frequent query paths.
- Replace fixed-width `character(n)` columns where padding has no value.
- Add operational metadata such as `source_file`, `scene_id`, `created_at`, and `ingested_at`.
- Store source file processing state in the database instead of relying only on log files.

## Phase 5: Pipeline Refactor

Extract common ingestion logic into shared modules:

- satellite input parsing
- Indonesia boundary filtering
- administrative boundary lookup
- persistent anomaly filtering
- duplicate detection
- clustering
- database insertion
- CSV export

Keep satellite-specific code small and focused on parsing and sensor-specific settings.

## Phase 6: Operations And Observability

- Replace scattered `print()` usage with structured logging.
- Add clear failure states, retry tracking, and dead-letter handling for failed files.
- Add health checks for last successful ingest per satellite and last successful tile generation.
- Improve notification emails so they include actionable context.
- Consider replacing cron with a container-friendly scheduler after the CLI workflow is stable.

## Migration Strategy

Run the modernized pipeline in parallel with the existing cron pipeline first:

1. Process sample data in Docker.
2. Compare outputs against the legacy system.
3. Migrate one satellite pipeline as the reference implementation.
4. Validate database and CSV equivalence.
5. Move the remaining satellite pipelines into the same pattern.
6. Switch production scheduling only after the new pipeline proves stable.

