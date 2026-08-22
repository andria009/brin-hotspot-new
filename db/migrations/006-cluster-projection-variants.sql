ALTER TABLE hotspot_cluster
ADD COLUMN IF NOT EXISTS cluster_projection text NOT NULL DEFAULT 'latitude_adjusted';

ALTER TABLE hotspot_cluster
DROP CONSTRAINT IF EXISTS hotspot_cluster_satellite_coordinate_observed_at_key;

ALTER TABLE hotspot_cluster
ADD CONSTRAINT hotspot_cluster_satellite_coordinate_observed_at_projection_key
UNIQUE (satellite, coordinate, observed_at, cluster_projection);

CREATE INDEX IF NOT EXISTS hotspot_cluster_projection_observed_at_idx
    ON hotspot_cluster (cluster_projection, observed_at);

INSERT INTO schema_migrations (version)
VALUES ('006-cluster-projection-variants')
ON CONFLICT (version) DO NOTHING;
