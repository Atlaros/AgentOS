-- Category display order. Photo bytes stay out of this database.

ALTER TABLE categories
  ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0;
