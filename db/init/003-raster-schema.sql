\connect raster

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raster_vertex (
    vid serial PRIMARY KEY,
    vertex geography(Polygon, 4326),
    infox text UNIQUE,
    satellite text,
    observed_at timestamp without time zone,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raster_meta (
    gid serial PRIMARY KEY,
    satellite text,
    observed_at timestamp without time zone,
    raster_type text,
    infox text,
    vertex_id integer REFERENCES raster_vertex (vid),
    source_file text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS raster_vertex_vertex_idx
    ON raster_vertex USING gist (vertex);

CREATE INDEX IF NOT EXISTS raster_meta_satellite_observed_at_idx
    ON raster_meta (satellite, observed_at);

CREATE INDEX IF NOT EXISTS raster_meta_source_file_idx
    ON raster_meta (source_file);

CREATE UNIQUE INDEX IF NOT EXISTS raster_meta_infox_type_source_file_uq
    ON raster_meta (infox, raster_type, source_file);
