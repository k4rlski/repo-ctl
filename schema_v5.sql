-- repo-ctl v0.5 schema delta: additive + idempotent columns on repo_alignment.
-- Adds two manually-curated columns (statprod / tooltype) that scans must never
-- overwrite (same pattern as hidden / statrepo / rolerepo from v0.4).
-- MariaDB 10.5 supports "ADD COLUMN IF NOT EXISTS". Keep one statement per line,
-- no mid-statement comments.
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS statprod VARCHAR(16) NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS tooltype VARCHAR(16) NULL;
