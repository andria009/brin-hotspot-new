ALTER TABLE hotspot_cluster
ADD COLUMN IF NOT EXISTS cluster_method text NOT NULL DEFAULT 'distance';

ALTER TABLE hotspot_cluster
ADD COLUMN IF NOT EXISTS footprint_geom geometry(MultiPolygon, 4326);

ALTER TABLE hotspot_cluster
ADD COLUMN IF NOT EXISTS footprint_area_m2 double precision;

ALTER TABLE hotspot_cluster
ADD COLUMN IF NOT EXISTS pixel_count integer;

ALTER TABLE hotspot_cluster
DROP CONSTRAINT IF EXISTS hotspot_cluster_satellite_coordinate_observed_at_projection_key;

ALTER TABLE hotspot_cluster
DROP CONSTRAINT IF EXISTS hotspot_cluster_unique_variant;

ALTER TABLE hotspot_cluster
ADD CONSTRAINT hotspot_cluster_unique_variant
UNIQUE (satellite, coordinate, observed_at, cluster_projection, cluster_method);

CREATE INDEX IF NOT EXISTS hotspot_cluster_footprint_idx
ON hotspot_cluster USING gist (footprint_geom)
WHERE footprint_geom IS NOT NULL;

INSERT INTO schema_migrations (version)
VALUES ('007-adjacent-footprint-clusters')
ON CONFLICT (version) DO NOTHING;
