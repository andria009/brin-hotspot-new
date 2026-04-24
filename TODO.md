# TODO

Remaining work for the modernized BRIN hotspot workspace.

## Priority

- Resolve the Python 3.14 MODIS HDF reader blocker. The current optional `pyhdf` Docker build reaches native compilation but fails against the Debian/HDF4 headers, so AQUA/TERRA production HDF ingestion needs a compatible reader, a patched `pyhdf`, or a sidecar conversion path.
- Add real AQUA and TERRA HDF4 sample fixtures once available, then verify parse, enrichment, clustering, CSV export, and PostGIS persistence end to end.
- Add a real GeoTIFF fixture for raster tests and assert actual XYZ tile output, not only command construction and empty-tree smoke checks.

## Operations

- Add worker deployment guidance for production-style schedules, retention, restart policy, and expected volume mounts.
- Add log retention and failure summary reporting around ingestion runs and source-file failures.
- Add backup/restore notes for the hotspot and raster PostgreSQL databases.
- Add environment-specific configuration examples for local, staging, and production deployments.

## Data Quality

- Validate duplicate filtering thresholds against representative SNPP, NOAA20, MODIS, and Landsat 8 sample sets.
- Validate administrative boundary imports against production province, kabupaten, kecamatan, and anomaly GeoJSON files.
- Add explicit data contracts for each satellite input family, including required fields, tolerated missing values, and filename expectations.

## Developer Experience

- Add CI commands for lint, tests, Docker build, and migration smoke checks.
- Add a small fixture-generation guide so new sample inputs can be added without leaking production data.
- Consider a leaner Docker image or multi-stage build once the HDF reader strategy is finalized.
