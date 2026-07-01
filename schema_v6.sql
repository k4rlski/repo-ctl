-- repo-ctl v0.6 Phase 1 schema delta: additive + idempotent.
-- Adds operator-editable clone/enhancement columns on repo_alignment (scans must
-- NEVER overwrite them; same pattern as hidden / statrepo / rolerepo / statprod /
-- tooltype) plus two new tables backing the clone-job queue and clone log.
-- MariaDB 10.5 supports "ADD COLUMN IF NOT EXISTS". Keep one statement per line,
-- no mid-statement comments.
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS proposed_upgrades TEXT NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS enhancement_issue_number INT NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS enhancement_issue_url VARCHAR(255) NULL;
ALTER TABLE repo_alignment ADD COLUMN IF NOT EXISTS clonelocal VARCHAR(24) NULL;

CREATE TABLE IF NOT EXISTS repo_clone_jobs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(64) NOT NULL,
  host VARCHAR(64) NOT NULL DEFAULT 'osiris',
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  requested_by VARCHAR(64) NULL,
  claimed_by VARCHAR(64) NULL,
  claimed_at DATETIME NULL,
  finished_at DATETIME NULL,
  message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_pending (host, status),
  KEY idx_slug (slug)
);

CREATE TABLE IF NOT EXISTS repo_clone_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(64) NOT NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  duration_sec DECIMAL(10,2) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'running',
  error_msg TEXT NULL,
  host VARCHAR(64) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_slug (slug),
  KEY idx_created (created_at)
);
