#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "ERRORE alla linea $LINENO: comando fallito con exit code $?" >&2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/backup.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Errore: file di configurazione mancante: $ENV_FILE"
  echo "Crea il file con:"
  echo "  cp $SCRIPT_DIR/backup.env.example $ENV_FILE"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

APP_DIR="${APP_DIR:-/home/ater/progetti/XRTourGuide/xr_tour_guide}"
BACKUP_ROOT="${BACKUP_ROOT:-/srv/backups/xr_tour_guide}"
BACKUP_RETENTION="${BACKUP_RETENTION:-2}"
DOCKER_NETWORK="${DOCKER_NETWORK:-backend_net}"
ENABLE_RCLONE_UPLOAD="${ENABLE_RCLONE_UPLOAD:-false}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
AUTO_INSTALL_RCLONE="${AUTO_INSTALL_RCLONE:-true}"
LOG_DIR="${LOG_DIR:-/var/log/xr_tour_guide}"

TS="$(date +%Y%m%d_%H%M%S)"
MYSQL_BACKUP_DIR="$BACKUP_ROOT/mysql"
MINIO_BACKUP_DIR="$BACKUP_ROOT/minio/$TS"

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
    log "Directory non scrivibile dall'utente corrente, provo chown: $dir"
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
    log "Installazione rclone tramite apt-get"
    sudo apt-get update
    sudo apt-get install -y rclone
  elif command -v dnf >/dev/null 2>&1; then
    log "Installazione rclone tramite dnf"
    sudo dnf install -y rclone
  elif command -v yum >/dev/null 2>&1; then
    log "Installazione rclone tramite yum"
    sudo yum install -y rclone
  elif command -v curl >/dev/null 2>&1; then
    log "Installazione rclone tramite script ufficiale"
    curl https://rclone.org/install.sh | sudo bash
  else
    fail "Impossibile installare rclone automaticamente: mancano apt/dnf/yum/curl"
  fi

  if ! command -v rclone >/dev/null 2>&1; then
    fail "Installazione rclone fallita"
  fi

  log "rclone installato correttamente"
}

ensure_rclone_remote() {
  if [ "$ENABLE_RCLONE_UPLOAD" != "true" ]; then
    return 0
  fi

  install_rclone_if_missing

  if [ -z "$RCLONE_REMOTE" ]; then
    fail "ENABLE_RCLONE_UPLOAD=true ma RCLONE_REMOTE non è configurato"
  fi

  local remote_name
  remote_name="$(echo "$RCLONE_REMOTE" | cut -d':' -f1)"

  if ! rclone listremotes | grep -qx "${remote_name}:"; then
    echo ""
    echo "Remote rclone non configurato: $remote_name"
    echo ""
    echo "Esegui una volta sulla macchina host:"
    echo ""
    echo "  rclone config"
    echo ""
    echo "Crea un remote chiamato:"
    echo ""
    echo "  $remote_name"
    echo ""
    echo "Poi verifica con:"
    echo ""
    echo "  rclone lsd ${remote_name}:"
    echo ""
    fail "Remote rclone mancante: $remote_name"
  fi

  log "Remote rclone trovato: $remote_name"
}

ensure_rclone_directories() {
  if [ "$ENABLE_RCLONE_UPLOAD" != "true" ]; then
    return 0
  fi

  log "Verifica/creazione directory remote rclone"

  rclone mkdir "$RCLONE_REMOTE" || true
  rclone mkdir "$RCLONE_REMOTE/mysql" || true
  rclone mkdir "$RCLONE_REMOTE/minio" || true
}

ensure_environment() {
  log "Verifica ambiente"

  ensure_command docker
  ensure_command gzip
  ensure_command sort
  ensure_command tail
  ensure_command xargs

  if ! docker compose version >/dev/null 2>&1; then
    fail "Docker Compose plugin non disponibile: comando 'docker compose' non funziona"
  fi

  if [ ! -d "$APP_DIR" ]; then
    fail "APP_DIR non esiste: $APP_DIR"
  fi

  if [ ! -f "$APP_DIR/docker-compose.yml" ]; then
    fail "docker-compose.yml non trovato in APP_DIR: $APP_DIR"
  fi

  if [ ! -f "$APP_DIR/.env" ]; then
    fail "File .env non trovato in APP_DIR: $APP_DIR/.env"
  fi

  ensure_directory "$BACKUP_ROOT"
  ensure_directory "$MYSQL_BACKUP_DIR"
  ensure_directory "$BACKUP_ROOT/minio"
  ensure_directory "$MINIO_BACKUP_DIR"
  ensure_directory "$LOG_DIR"

  if ! docker network inspect "$DOCKER_NETWORK" >/dev/null 2>&1; then
    fail "Network Docker non trovato: $DOCKER_NETWORK"
  fi

  cd "$APP_DIR"

  if ! docker compose ps db >/dev/null 2>&1; then
    fail "Servizio Docker Compose 'db' non trovato o compose non valido"
  fi

  if ! docker compose ps minio >/dev/null 2>&1; then
    fail "Servizio Docker Compose 'minio' non trovato o compose non valido"
  fi

  ensure_rclone_remote
  ensure_rclone_directories
}

backup_mysql() {
  log "Backup MySQL"

  cd "$APP_DIR"

  docker compose exec -T db sh -c '
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump \
  -uroot \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --databases "$MYSQL_DATABASE"
' | gzip > "$MYSQL_BACKUP_DIR/mysql_$TS.sql.gz"

  if [ ! -s "$MYSQL_BACKUP_DIR/mysql_$TS.sql.gz" ]; then
    fail "Backup MySQL creato ma vuoto: $MYSQL_BACKUP_DIR/mysql_$TS.sql.gz"
  fi

  log "Backup MySQL completato: $MYSQL_BACKUP_DIR/mysql_$TS.sql.gz"
}

get_container_env() {
  local service="$1"
  local var="$2"

  docker compose exec -T "$service" printenv "$var" | tr -d '\r'
}

backup_minio() {
  log "Backup MinIO"

  cd "$APP_DIR"

  local minio_user
  local minio_password
  local bucket_name

  minio_user="$(get_container_env minio MINIO_ROOT_USER)"
  minio_password="$(get_container_env minio MINIO_ROOT_PASSWORD)"
  bucket_name="$(get_container_env web AWS_STORAGE_BUCKET_NAME)"

  if [ -z "$minio_user" ] || [ -z "$minio_password" ]; then
    fail "Impossibile ottenere le variabili d'ambiente MinIO dal container minio"
  fi

  if [ -z "$bucket_name" ]; then
    fail "Impossibile ottenere le variabili d'ambiente MinIO dal container web"
  fi

  log "Avvio container minio/mc"

  if ! docker run --rm \
    --network "$DOCKER_NETWORK" \
    -e MINIO_ROOT_USER="$minio_user" \
    -e MINIO_ROOT_PASSWORD="$minio_password" \
    -e AWS_STORAGE_BUCKET_NAME="$bucket_name" \
    -v "$MINIO_BACKUP_DIR:/backup" \
    --entrypoint /bin/sh \
    minio/mc@sha256:aead63c77f9db9107f1696fb08ecb0faeda23729cde94b0f663edf4fe09728e3 \
    -c '
      set -eux
      echo "Setting up MinIO alias..."
      mc alias set myminio http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
      echo "Starting MinIO backup..."
      mc mirror --overwrite myminio/"$AWS_STORAGE_BUCKET_NAME" /backup/"$AWS_STORAGE_BUCKET_NAME"
    '; then
    fail "Backup MinIO fallito"
  fi

  log "Backup MinIO completato: $MINIO_BACKUP_DIR"
}

upload_to_rclone() {
  if [ "$ENABLE_RCLONE_UPLOAD" != "true" ]; then
    log "Upload rclone disabilitato"
    return 0
  fi

  log "Upload MySQL su rclone: $RCLONE_REMOTE"

  rclone copy "$MYSQL_BACKUP_DIR/mysql_$TS.sql.gz" \
    "$RCLONE_REMOTE/mysql/" \
    --transfers 4 \
    --checkers 8

  log "Upload MinIO su rclone: $RCLONE_REMOTE"

  rclone copy "$MINIO_BACKUP_DIR" \
    "$RCLONE_REMOTE/minio/$TS/" \
    --transfers 4 \
    --checkers 8

  log "Upload rclone completato"
}

apply_local_retention() {
  log "Retention locale MySQL: mantengo ultimi $BACKUP_RETENTION backup"

  ls -1t "$MYSQL_BACKUP_DIR"/mysql_*.sql.gz 2>/dev/null \
    | tail -n +"$((BACKUP_RETENTION + 1))" \
    | xargs -r rm -f

  log "Retention locale MinIO: mantengo ultimi $BACKUP_RETENTION backup"

  ls -1dt "$BACKUP_ROOT"/minio/* 2>/dev/null \
    | tail -n +"$((BACKUP_RETENTION + 1))" \
    | xargs -r rm -rf
}

apply_remote_retention() {
  if [ "$ENABLE_RCLONE_UPLOAD" != "true" ]; then
    return 0
  fi

  log "Retention remota MySQL: mantengo ultimi $BACKUP_RETENTION backup"

  rclone lsf "$RCLONE_REMOTE/mysql/" \
    --files-only \
    | sort -r \
    | tail -n +"$((BACKUP_RETENTION + 1))" \
    | while read -r file; do
        if [ -n "$file" ]; then
          rclone deletefile "$RCLONE_REMOTE/mysql/$file"
        fi
      done

  log "Retention remota MinIO: mantengo ultimi $BACKUP_RETENTION backup"

  rclone lsf "$RCLONE_REMOTE/minio/" \
    --dirs-only \
    | sort -r \
    | tail -n +"$((BACKUP_RETENTION + 1))" \
    | while read -r dir; do
        if [ -n "$dir" ]; then
          rclone purge "$RCLONE_REMOTE/minio/$dir"
        fi
      done
}

main() {
  log "Avvio backup XR Tour Guide"
  log "Timestamp: $TS"

  ensure_environment
  backup_mysql
  backup_minio
  upload_to_rclone
  apply_local_retention
  apply_remote_retention

  log "Backup completato correttamente"
}

main "$@"
