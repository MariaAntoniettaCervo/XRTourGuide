#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Uso:"
  echo "  $0 /percorso/backup/mysql_YYYYMMDD_HHMMSS.sql.gz"
  exit 1
fi

BACKUP_FILE="$1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/backup.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Errore: file mancante: $ENV_FILE"
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Errore: backup MySQL non trovato: $BACKUP_FILE"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

APP_DIR="${APP_DIR:-/home/ater/progetti/XRTourGuide/xr_tour_guide}"

cd "$APP_DIR"

echo "Restore MySQL da: $BACKUP_FILE"
echo "ATTENZIONE: il database corrente verrà sovrascritto/importato."
echo "Continuo tra 5 secondi..."
sleep 5

gunzip -c "$BACKUP_FILE" \
  | docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot'

echo "Restore MySQL completato"
