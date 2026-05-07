# TODO

Remaining work for the modernized BRIN hotspot workspace.

## Priority

- Get real TERA HDF4 samples and verify the `modis-converter` output against expected fire-pixel latitude, longitude, confidence, observation time, and source metadata.
- Add sanitized real AQUA converted CSV/HDF4 fixtures from the tested production sample, plus TERA fixtures once available.
- Add a real GeoTIFF fire-index fixture and assert actual XYZ tile output, not only command construction and empty-tree smoke checks.
- Validate real province, kabupaten, kecamatan, and persistent-anomaly GeoJSON imports against the production schema and enrichment queries.
- Tune duplicate filtering buffers and clustering behavior using representative SNPP, NOAA20, AQUA/MODIS, and Landsat 8 data.

## Operations

- Validate the long-running `worker-service` against live SNPP, NOAA20, and converted AQUA folders after completed backfill ingestion.
- Add operational checks for `worker-service` health, recent cycles, source-file failures, and enrichment coverage.
- Add Tera to `worker-service` after Tera source data and MODIS conversion output are ready.
- Add worker deployment guidance for production-style schedules, expected volume mounts, restart policy, and operational runbooks.
- Add log retention and failure summary reporting around ingestion runs and source-file failures.
- Add backup/restore notes for the hotspot and raster PostgreSQL databases.
- Add environment-specific configuration examples for local, staging, and production deployments.

## Data Quality

- Validate duplicate filtering thresholds against representative SNPP, NOAA20, AQUA/MODIS, TERA/MODIS, and Landsat 8 sample sets.
- Validate administrative boundary imports against production province, kabupaten, kecamatan, and anomaly GeoJSON files, including expected null-enrichment cases for offshore/outside-boundary pixels.
- Add explicit data contracts for each satellite input family, including required fields, tolerated missing values, and filename expectations.

## Developer Experience

- Add CI commands for lint, tests, Docker build, migration smoke checks, and a no-database ingestion smoke.
- Add a small fixture-generation guide so new sample inputs can be added without leaking production data.
- Consider a leaner Docker image or multi-stage build for the worker and MODIS converter images.
