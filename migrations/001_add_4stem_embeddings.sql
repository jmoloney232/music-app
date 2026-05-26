ALTER TABLE embeddings
    ADD COLUMN IF NOT EXISTS muq_drums vector(512),
    ADD COLUMN IF NOT EXISTS muq_bass vector(512),
    ADD COLUMN IF NOT EXISTS muq_other vector(512);
