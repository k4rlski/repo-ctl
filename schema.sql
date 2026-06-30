-- repo-ctl: repo_alignment table (lives in infra_ctl on dbx, alongside tech_registry)
-- Tracks each repo's state across four planes:
--   GitHub  | Local-final (core-v5) | Local-current (stray clone) | Server (source of truth)
-- Written by `repo-ctl get-state` (read-only scan -> upsert). Keyed by slug.

CREATE TABLE IF NOT EXISTS repo_alignment (
    slug                VARCHAR(64)  NOT NULL PRIMARY KEY,
    repo                VARCHAR(128) NULL,            -- k4rlski/<repo>

    -- GitHub plane (from `git ls-remote`, token-free)
    gh_default_branch   VARCHAR(128) NULL,
    gh_head_sha         VARCHAR(40)  NULL,
    gh_head_date        DATETIME     NULL,           -- optional (API only)
    gh_pushed_at        DATETIME     NULL,           -- optional (API only)

    -- Local-final plane (core-v5/<slug> on osiris)
    lf_path             VARCHAR(512) NULL,
    lf_exists           TINYINT(1)   NOT NULL DEFAULT 0,
    lf_is_git           TINYINT(1)   NOT NULL DEFAULT 0,
    lf_branch           VARCHAR(128) NULL,
    lf_head_sha         VARCHAR(40)  NULL,
    lf_dirty            INT          NULL,
    lf_ahead            INT          NULL,
    lf_behind           INT          NULL,

    -- Local-current plane (stray clone: CURSOR/* , AUTO-CTL/* , top-level)
    lc_path             VARCHAR(512) NULL,
    lc_exists           TINYINT(1)   NOT NULL DEFAULT 0,
    lc_is_git           TINYINT(1)   NOT NULL DEFAULT 0,
    lc_branch           VARCHAR(128) NULL,
    lc_head_sha         VARCHAR(40)  NULL,
    lc_dirty            INT          NULL,
    lc_ahead            INT          NULL,
    lc_behind           INT          NULL,

    -- Server plane (source of truth)
    server_host         VARCHAR(128) NULL,
    server_path         VARCHAR(512) NULL,
    srv_exists          TINYINT(1)   NOT NULL DEFAULT 0,
    srv_is_git          TINYINT(1)   NOT NULL DEFAULT 0,
    srv_branch          VARCHAR(128) NULL,
    srv_head_sha        VARCHAR(40)  NULL,
    srv_dirty           INT          NULL,
    srv_ahead           INT          NULL,
    srv_behind          INT          NULL,

    -- Derived
    alignment_status    VARCHAR(16)  NOT NULL DEFAULT 'unknown',  -- aligned|drift|missing|stale|unknown
    notes               TEXT         NULL,
    scanned_at          DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
