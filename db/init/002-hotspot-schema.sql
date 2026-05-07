\connect hotspot

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id uuid PRIMARY KEY,
    satellite text NOT NULL,
    status text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    source_path text,
    message text
);

CREATE TABLE IF NOT EXISTS source_files (
    id bigserial PRIMARY KEY,
    satellite text NOT NULL,
    path text NOT NULL,
    source_key text,
    scene_id text,
    observed_at timestamp without time zone,
    status text NOT NULL DEFAULT 'pending',
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    last_error text,
    UNIQUE (satellite, path)
);

CREATE INDEX IF NOT EXISTS source_files_satellite_source_key_idx
    ON source_files (satellite, source_key)
    WHERE source_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS prov_ar (
    gid serial PRIMARY KEY,
    wa text NOT NULL,
    geom geometry(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS kab_kota_ar (
    gid serial PRIMARY KEY,
    wa text NOT NULL,
    prov_id integer REFERENCES prov_ar (gid),
    geom geometry(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS kec_ar (
    gid serial PRIMARY KEY,
    wa text NOT NULL,
    prov_id integer REFERENCES prov_ar (gid),
    kab_id integer REFERENCES kab_kota_ar (gid),
    geom geometry(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS persistent_anomalies_buffer_500m (
    gid serial PRIMARY KEY,
    name text,
    geom geometry(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS hotspot_cluster (
    cid bigserial PRIMARY KEY,
    satellite text NOT NULL,
    coordinate geography(Point, 4326) NOT NULL,
    conf_lvl integer NOT NULL,
    provinsi text,
    kabupaten text,
    kecamatan text,
    radius integer,
    source_station text,
    observed_at timestamp without time zone NOT NULL,
    source_file text,
    scene_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (satellite, coordinate, observed_at)
);

CREATE TABLE IF NOT EXISTS hotspot_pixel (
    hid bigserial PRIMARY KEY,
    satellite text NOT NULL,
    coordinate geography(Point, 4326) NOT NULL,
    conf_lvl_org text,
    conf_lvl integer NOT NULL,
    cluster_id bigint REFERENCES hotspot_cluster (cid),
    provinsi text,
    kabupaten text,
    kecamatan text,
    source_station text,
    radius integer,
    observed_at timestamp without time zone NOT NULL,
    source_file text,
    scene_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (satellite, coordinate, observed_at)
);

CREATE INDEX IF NOT EXISTS hotspot_cluster_coordinate_idx
    ON hotspot_cluster USING gist (coordinate);

CREATE INDEX IF NOT EXISTS hotspot_pixel_coordinate_idx
    ON hotspot_pixel USING gist (coordinate);

CREATE INDEX IF NOT EXISTS hotspot_pixel_cluster_id_idx
    ON hotspot_pixel (cluster_id);

CREATE INDEX IF NOT EXISTS hotspot_pixel_satellite_observed_at_idx
    ON hotspot_pixel (satellite, observed_at);

CREATE INDEX IF NOT EXISTS prov_ar_geom_idx
    ON prov_ar USING gist (geom);

CREATE INDEX IF NOT EXISTS kab_kota_ar_geom_idx
    ON kab_kota_ar USING gist (geom);

CREATE INDEX IF NOT EXISTS kec_ar_geom_idx
    ON kec_ar USING gist (geom);

CREATE INDEX IF NOT EXISTS persistent_anomalies_buffer_500m_geom_idx
    ON persistent_anomalies_buffer_500m USING gist (geom);
