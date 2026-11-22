-- 047 conversation media enrichment: transcript / summary (ADR-015 Fase E).

ALTER TABLE conversation_media
    ADD COLUMN IF NOT EXISTS transcript_text text,
    ADD COLUMN IF NOT EXISTS summary_text text,
    ADD COLUMN IF NOT EXISTS enrichment_status text NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS enrichment_error text;

ALTER TABLE conversation_media DROP CONSTRAINT IF EXISTS conversation_media_enrichment_status_check;
ALTER TABLE conversation_media ADD CONSTRAINT conversation_media_enrichment_status_check
    CHECK (enrichment_status IN ('none', 'pending', 'ready', 'failed'));
