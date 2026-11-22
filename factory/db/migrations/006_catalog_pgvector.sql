-- pgvector kNN over catalog embeddings. Facts still come from agent_catalog_read.
CREATE INDEX IF NOT EXISTS product_embeddings_cosine_hnsw
    ON product_embeddings USING hnsw (embedding vector_cosine_ops);
