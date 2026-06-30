#!/usr/bin/env bash
# repo-ctl get-state cron wrapper (osiris). Authoritative read-only alignment
# sweep -> infra_ctl.repo_alignment via the claw tunnel. Runs alongside the
# twice-daily auto-ingest cron. Logs to ~/.local/log/repo-ctl-get-state.log.
set -uo pipefail

export PATH=/usr/bin:/bin:/usr/local/bin
REPO_DIR="$HOME/DEVOPS Dropbox/DEVOPS-KARL/core-v5/repo-ctl"
LOG="$HOME/.local/log/repo-ctl-get-state.log"
mkdir -p "$(dirname "$LOG")"

cd "$REPO_DIR" || exit 1
export REPO_CTL_CONFIG="$REPO_DIR/config/repo-ctl.yml"

echo "=== get-state $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$LOG"
PYTHONPATH="$REPO_DIR/src" /usr/bin/python3 -m repo_ctl.main get-state >> "$LOG" 2>&1
echo "exit=$? $(date -u +%H:%M:%SZ)" >> "$LOG"
