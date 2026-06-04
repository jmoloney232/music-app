-- HNSW index on muq_full for fast approximate nearest-neighbor search.
-- Used to pre-filter candidates in /similar before weighted Python scoring.
-- m=16, ef_construction=64 are standard defaults; good recall/speed balance.
CREATE INDEX IF NOT EXISTS embeddings_muq_full_hnsw
ON embeddings
USING hnsw (muq_full vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
