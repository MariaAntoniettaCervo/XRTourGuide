#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/backup.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Errore: file mancante: $ENV_FILE"
  echo "Crea il file con:"
  echo "  cp $SCRIPT_DIR/backup.env.example $ENV_FILE"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

CRON_HOUR="${CRON_HOUR:-23}"
CRON_MINUTE="${CRON_MINUTE:-50}"
LOG_DIR="${LOG_DIR:-/var/log/community_server}"
LOG_FILE="$LOG_DIR/backup.log"
BACKUP_SCRIPT="$SCRIPT_DIR/run_backup.sh"
CRON_MARKER="# COMMUNITY_SERVER_BACKUP_CRON"

mkdir -p "$LOG_DIR" 2>/dev/null || sudo mkdir -p "$LOG_DIR"

if [ ! -w "$LOG_DIR" ]; then
  sudo chown -R "$USER:$USER" "$LOG_DIR" || true
fi

chmod +x "$SCRIPT_DIR"/*.sh

NEW_CRON="$CRON_MINUTE $CRON_HOUR * * * $BACKUP_SCRIPT >> $LOG_FILE 2>&1 $CRON_MARKER"

TMP_CRON="$(mktemp)"

crontab -l 2>/dev/null | grep -v "$CRON_MARKER" > "$TMP_CRON" || true
echo "$NEW_CRON" >> "$TMP_CRON"

crontab "$TMP_CRON"
rm -f "$TMP_CRON"

echo "Cron installato:"
echo "$NEW_CRON"
