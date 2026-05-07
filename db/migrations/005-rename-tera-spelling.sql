UPDATE ingestion_runs
SET satellite = 'tera'
WHERE satellite = 'terra';

UPDATE source_files
SET satellite = 'tera'
WHERE satellite = 'terra';

UPDATE hotspot_cluster
SET satellite = 'tera'
WHERE satellite = 'terra';

UPDATE hotspot_pixel
SET satellite = 'tera'
WHERE satellite = 'terra';
