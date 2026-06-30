"""
tool_pages.py - slug -> MARS dashboard page path map.

Derived from the mars-status nav menu + tool-links resolver in
`static/ui-ctl.js`. Most tools live at `/tools/<slug>`, but several use
`/ops/<x>`, `/adm/<x>`, `/tool/<x>`, `/tool-page/<x>`, or a bespoke path.
`page_link(slug)` returns the full https URL for the canonical page, falling
back to `/tools/<slug>` for any slug not explicitly mapped.

Source of truth: mars-status `static/ui-ctl.js` (READ-ONLY reference). Keep in
sync when the MARS nav changes.
"""

MARS_BASE = "https://mars.auto-ctl.io"

# slug -> page path (exact paths copied from ui-ctl.js nav + TOOL_META resolver).
TOOL_PAGE_PATHS = {
    "abbr-ctl": "/tools/abbr-ctl",
    "ad-buys-ctl": "/tool-page/ad-buys-ctl",
    "api-ctl": "/tools/api-ctl",
    "apx-ctl": "/tools/apx-ctl",
    "apx-sched-ctl": "/adm/apx-sched-ctl",
    "auto-assign": "/ops/auto-assign",
    "bkup-ctl": "/tools/bkup-ctl",
    "biz-admin-ctl": "/ops/biz-adm",
    "cascade-ctl": "/tools/cascade-ctl",
    "chat-ctl": "/tools/chat-ctl",
    "chroma-ctl": "/chromadb",
    "code-ctl": "/tools/code-ctl",
    "confirmed-ctl": "/tools/confirmed-ctl",
    "cp-ctl": "/cp-ctl",
    "cursor-export-ctl": "/tools/cursor-export-ctl",
    "data-ctl": "/tools/data-ctl",
    "db-ctl": "/tools/db-ctl",
    "dbox-ctl": "/tools/dbox-ctl",
    "diagram-ctl": "/tools/diagram-ctl",
    "dns-ctl": "/tools/dns-ctl",
    "dropbox-ctl": "/adm/dropbox-ctl",
    "espo-ctl": "/tools/espo-ctl",
    "espo-crm": "/tools/espo-ctl",
    "field-ctl": "/tools/field-ctl",
    "file-ctl": "/tools/file-ctl",
    "fin-ctl": "/ops/fin-ctl",
    "gat-ctl": "/tool-page/gat-ctl",
    "geo-ctl": "/tools/geo-ctl",
    "gmail-ctl": "/tools/gmail-ctl",
    "hermes-ctl": "/tools/hermes-ctl",
    "infra-ctl": "/tools/infra-ctl",
    "job-board-ctl": "/tool/job-board-ctl",
    "mail-ctl": "/tools/mail-ctl",
    "notify-ctl": "/tools/notify-ctl",
    "plaid-ctl": "/tools/plaid-ctl",
    "plan-ctl": "/tools/plan-ctl",
    "price-ctl": "/tools/price-ctl",
    "quote-ctl": "/tool/quote-ctl",
    "rag-ctl": "/tools/rag-ctl",
    "repo-ctl": "/tools/repo-ctl",
    "search-ctl": "/adm/search-ctl",
    "security-ctl": "/tools/security-ctl",
    "server-ctl": "/tools/server-ctl",
    "service-ctl": "/tool/service-ctl",
    "site-ctl": "/tool-page/site-ctl",
    "snapshot-ctl": "/tools/snapshot-ctl",
    "ssl-ctl": "/tool/ssl-ctl",
    "stripe-ctl": "/tools/stripe-ctl",
    "swa-ctl": "/tool/swa-ctl",
    "sync-ctl": "/tools/sync-ctl",
    "tax-ctl": "/tools/tax-ctl",
    "trx-ctl": "/ops/trx-ctl",
    "ui-ctl": "/tools/ui-ctl-page",
    "vendor-ctl": "/tools/vendor-ctl",
    "vpn-ctl": "/tools/vpn-ctl",
    "zip-media-ctl": "/tools/zip-media-ctl",
}


def page_path(slug):
    """Return the MARS page path for a slug (default `/tools/<slug>`)."""
    return TOOL_PAGE_PATHS.get(slug, f"/tools/{slug}")


def page_link(slug):
    """Return the full https MARS deep-link for a slug."""
    return f"{MARS_BASE}{page_path(slug)}"
