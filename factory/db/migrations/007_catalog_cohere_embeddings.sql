-- Cohere embed-v4 vectors in pgvector. Facts still come from agent_catalog_read.
DROP INDEX IF EXISTS product_embeddings_cosine_hnsw;
ALTER TABLE product_embeddings DROP COLUMN IF EXISTS embedding;
ALTER TABLE product_embeddings ADD COLUMN embedding vector(1024);
CREATE INDEX IF NOT EXISTS product_embeddings_cosine_hnsw
    ON product_embeddings USING hnsw (embedding vector_cosine_ops);
