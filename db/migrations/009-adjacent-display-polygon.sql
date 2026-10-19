ALTER TABLE hotspot_cluster
ADD COLUMN IF NOT EXISTS display_geom geometry(MultiPolygon, 4326);

INSERT INTO schema_migrations (version)
VALUES ('009-adjacent-display-polygon')
ON CONFLICT (version) DO NOTHING;
