\connect raster

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS raster_meta_infox_raster_type_idx
    ON raster_meta (infox, raster_type);

CREATE INDEX IF NOT EXISTS raster_meta_source_file_idx
    ON raster_meta (source_file);

CREATE UNIQUE INDEX IF NOT EXISTS raster_meta_infox_type_source_file_uq
    ON raster_meta (infox, raster_type, source_file);

INSERT INTO schema_migrations (version)
VALUES ('003-raster-operational-indexes')
ON CONFLICT (version) DO NOTHING;
