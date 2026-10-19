CREATE INDEX IF NOT EXISTS hotspot_cluster_method_projection_date_satellite_idx
    ON hotspot_cluster (cluster_method, cluster_projection, observed_at, satellite);

CREATE INDEX IF NOT EXISTS hotspot_pixel_latest_enriched_idx
    ON hotspot_pixel (observed_at DESC) WHERE provinsi IS NOT NULL;
