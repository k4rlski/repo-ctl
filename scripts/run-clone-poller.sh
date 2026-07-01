#!/usr/bin/env bash
# repo-ctl clone-local pull-agent cron wrapper (osiris/ares/raven). Claims ONE
# pending job from infra_ctl.repo_clone_jobs (via the claw tunnel) and clones the
# repo into its core-v5/<slug> home. flock -n guards the whole body so an
# overrunning run can never overlap the next (2-minute) cron tick. Appends to
# ~/.local/log/repo-ctl-clone-poller.log. (Phase 4 installs the crontab.)
set -uo pipefail

export PATH=/usr/bin:/bin:/usr/local/bin
REPO_DIR="$HOME/DEVOPS Dropbox/DEVOPS-KARL/core-v5/repo-ctl"
LOG="$HOME/.local/log/repo-ctl-clone-poller.log"
LOCK="$HOME/.local/log/repo-ctl-clone-poller.lock"
mkdir -p "$(dirname "$LOG")"

# Non-blocking lock: if a previous run is still going, skip this tick.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "=== clone-poller $(date -u +%Y-%m-%dT%H:%M:%SZ) SKIP (locked) ===" >> "$LOG"
  exit 0
fi

cd "$REPO_DIR" || exit 1
export REPO_CTL_CONFIG="$REPO_DIR/config/repo-ctl.yml"

echo "=== clone-poller $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$LOG"
PYTHONPATH="$REPO_DIR/src" /usr/bin/python3 -m repo_ctl.main clone-local >> "$LOG" 2>&1
echo "exit=$? $(date -u +%H:%M:%SZ)" >> "$LOG"
