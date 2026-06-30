-- repo-ctl v0.3 schema delta: additive + idempotent columns on repo_alignment.
-- Adds RAG metadata, the MARS tool-page deep-link, and per-plane last-commit dates.
-- gh_head_date / gh_pushed_at already exist (schema.sql) and are intentionally NOT re-added.
-- MariaDB supports "ADD COLUMN IF NOT EXISTS"; on a server that does not, the apply
-- step guards each ALTER. Keep one statement per line, no mid-statement comments.
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS rag_name VARCHAR(128) NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS rag_link VARCHAR(512) NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS rag_last_updated DATE NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS rag_published_date DATE NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS rag_file_mtime DATETIME NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS tool_page_link VARCHAR(256) NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS srv_head_date DATETIME NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS lf_head_date DATETIME NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS lc_head_date DATETIME NULL;
