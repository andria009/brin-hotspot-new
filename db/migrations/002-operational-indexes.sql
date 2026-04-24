CREATE INDEX IF NOT EXISTS ingestion_runs_satellite_started_at_idx
    ON ingestion_runs (satellite, started_at DESC);

CREATE INDEX IF NOT EXISTS ingestion_runs_status_started_at_idx
    ON ingestion_runs (status, started_at DESC);

CREATE INDEX IF NOT EXISTS source_files_satellite_status_observed_at_idx
    ON source_files (satellite, status, observed_at DESC);

INSERT INTO schema_migrations (version)
VALUES ('002-operational-indexes')
ON CONFLICT (version) DO NOTHING;
