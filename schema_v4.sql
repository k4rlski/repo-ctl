-- repo-ctl v0.4 schema delta: additive + idempotent columns on repo_alignment.
-- Adds display name + full GitHub URL (scanner-derived) plus three manually-curated
-- columns (hidden / statrepo / rolerepo) that scans must never overwrite.
-- MariaDB 10.5 supports "ADD COLUMN IF NOT EXISTS". Keep one statement per line,
-- no mid-statement comments.
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS name VARCHAR(128) NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS github_link VARCHAR(256) NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS hidden TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS statrepo VARCHAR(16) NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS rolerepo VARCHAR(24) NULL;
