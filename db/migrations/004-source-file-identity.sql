ALTER TABLE source_files
    ADD COLUMN IF NOT EXISTS source_key text;

UPDATE source_files
SET source_key = COALESCE(scene_id, regexp_replace(path, '^.*/', ''))
WHERE source_key IS NULL;

CREATE INDEX IF NOT EXISTS source_files_satellite_source_key_idx
    ON source_files (satellite, source_key)
    WHERE source_key IS NOT NULL;

INSERT INTO schema_migrations (version)
VALUES ('004-source-file-identity')
ON CONFLICT (version) DO NOTHING;
