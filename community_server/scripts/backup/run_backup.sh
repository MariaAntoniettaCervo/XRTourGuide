#!/usr/bin/env bash
set -Eeuo pipefail

trap 'echo "ERRORE alla linea $LINENO: comando fallito con exit code $?" >&2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/backup.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Errore: file configurazione mancante: $ENV_FILE"
  echo "Crea il file con:"
  echo "  cp $SCRIPT_DIR/backup.env.example $ENV_FILE"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

APP_DIR="${APP_DIR:-/home/ater/progetti/XRTourGuide/community_server}"
BACKUP_ROOT="${BACKUP_ROOT:-/srv/backups/community_server}"
BACKUP_RETENTION="${BACKUP_RETENTION:-2}"
DB_SERVICE="${DB_SERVICE:-db_cs}"
ENABLE_RCLONE_UPLOAD="${ENABLE_RCLONE_UPLOAD:-false}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
AUTO_INSTALL_RCLONE="${AUTO_INSTALL_RCLONE:-true}"
LOG_DIR="${LOG_DIR:-/var/log/community_server}"

TS="$(date +%Y%m%d_%H%M%S)"
MYSQL_BACKUP_DIR="$BACKUP_ROOT/mysql"
MYSQL_BACKUP_FILE="$MYSQL_BACKUP_DIR/community_mysql_$TS.sql.gz"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

fail() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERRORE: $*" >&2
  exit 1
}

ensure_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    fail "Comando mancante: $cmd"
  fi
}

ensure_directory() {
  local dir="$1"

  if [ ! -d "$dir" ]; then
    log "Directory mancante, creazione: $dir"
    mkdir -p "$dir" 2>/dev/null || sudo mkdir -p "$dir"
  fi

  if [ ! -w "$dir" ]; then
    sudo chown -R "$USER:$USER" "$dir" || true
  fi

  if [ ! -w "$dir" ]; then
    fail "Directory non scrivibile: $dir"
  fi
}

install_rclone_if_missing() {
  if command -v rclone >/dev/null 2>&1; then
    log "rclone già installato"
    return 0
  fi

  if [ "$AUTO_INSTALL_RCLONE" != "true" ]; then
    fail "rclone non installato e AUTO_INSTALL_RCLONE=false"
  fi

  log "rclone non trovato, provo installazione automatica"

  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y rclone
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y rclone
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y rclone
  elif command -v curl >/dev/null 2>&1; then
    curl https://rclone.org/install.sh | sudo bash
  else
    fail "Impossibile installare rclone automaticamente"
  fi
}

ensure_rclone() {
  if [ "$ENABLE_RCLONE_UPLOAD" != "true" ]; then
    return 0
  fi

  install_rclone_if_missing

  if [ -z "$RCLONE_REMOTE" ]; then
    fail "RCLONE_REMOTE non configurato"
  fi

  local remote_name
  remote_name="$(echo "$RCLONE_REMOTE" | cut -d':' -f1)"

  if ! rclone listremotes | grep -qx "${remote_name}:"; then
    fail "Remote rclone non configurato: $remote_name. Esegui prima: rclone config"
  fi

  rclone mkdir "$RCLONE_REMOTE" || true
  rclone mkdir "$RCLONE_REMOTE/mysql" || true
}

ensure_environment() {
  log "Verifica ambiente"

  ensure_command docker
  ensure_command gzip
  ensure_command sort
  ensure_command tail
  ensure_command xargs

  if ! docker compose version >/dev/null 2>&1; then
    fail "Docker Compose plugin non disponibile"
  fi

  if [ ! -d "$APP_DIR" ]; then
    fail "APP_DIR non esiste: $APP_DIR"
  fi

  if [ ! -f "$APP_DIR/docker-compose.yml" ]; then
    fail "docker-compose.yml non trovato in: $APP_DIR"
  fi

  ensure_directory "$BACKUP_ROOT"
  ensure_directory "$MYSQL_BACKUP_DIR"
  ensure_directory "$LOG_DIR"

  cd "$APP_DIR"

  if [ -z "$(docker compose ps -q "$DB_SERVICE")" ]; then
    fail "Container servizio DB non trovato: $DB_SERVICE"
  fi

  ensure_rclone
}

backup_mysql() {
  log "Backup MySQL community_server"

  cd "$APP_DIR"

  docker compose exec -T "$DB_SERVICE" sh -c '
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump \
  -uroot \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --databases "$MYSQL_DATABASE"
' | gzip > "$MYSQL_BACKUP_FILE"

  if [ ! -s "$MYSQL_BACKUP_FILE" ]; then
    fail "Backup MySQL vuoto: $MYSQL_BACKUP_FILE"
  fi

  log "Backup MySQL completato: $MYSQL_BACKUP_FILE"
}

upload_to_rclone() {
  if [ "$ENABLE_RCLONE_UPLOAD" != "true" ]; then
    log "Upload rclone disabilitato"
    return 0
  fi

  log "Upload su rclone: $RCLONE_REMOTE"

  rclone copy "$MYSQL_BACKUP_FILE" \
    "$RCLONE_REMOTE/mysql/" \
    --transfers 4 \
    --checkers 8

  log "Upload rclone completato"
}

apply_local_retention() {
  log "Retention locale: mantengo ultimi $BACKUP_RETENTION backup"

  ls -1t "$MYSQL_BACKUP_DIR"/community_mysql_*.sql.gz 2>/dev/null \
    | tail -n +"$((BACKUP_RETENTION + 1))" \
    | xargs -r rm -f
}

apply_remote_retention() {
  if [ "$ENABLE_RCLONE_UPLOAD" != "true" ]; then
    return 0
  fi

  log "Retention remota: mantengo ultimi $BACKUP_RETENTION backup"

  rclone lsf "$RCLONE_REMOTE/mysql/" \
    --files-only \
    | sort -r \
    | tail -n +"$((BACKUP_RETENTION + 1))" \
    | while read -r file; do
        if [ -n "$file" ]; then
          rclone deletefile "$RCLONE_REMOTE/mysql/$file"
        fi
      done
}

main() {
  log "Avvio backup community_server"
  log "Timestamp: $TS"

  ensure_environment
  backup_mysql
  upload_to_rclone
  apply_local_retention
  apply_remote_retention

  log "Backup community_server completato correttamente"
}

main "$@"
