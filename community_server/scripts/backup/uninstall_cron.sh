#!/usr/bin/env bash
set -euo pipefail

CRON_MARKER="# COMMUNITY_SERVER_BACKUP_CRON"
TMP_CRON="$(mktemp)"

crontab -l 2>/dev/null | grep -v "$CRON_MARKER" > "$TMP_CRON" || true
crontab "$TMP_CRON"
rm -f "$TMP_CRON"

echo "Cron backup community_server rimosso"
