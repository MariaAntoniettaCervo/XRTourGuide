# Backup community_server

Sistema di backup per il database MySQL del `community_server`.

## Setup

```bash
cd /home/ater/progetti/XRTourGuide/community_server
chmod +x scripts/backup/*.sh
cp scripts/backup/backup.env.example scripts/backup/backup.env
nano scripts/backup/backup.env
```

## Backup manuale

```bash
./scripts/backup/run_backup.sh
```

I backup locali vengono salvati in:

```bash
/srv/backups/community_server/mysql/
```

## Cron giornaliero

```bash
./scripts/backup/install_cron.sh
```

Verifica:

```bash
crontab -l
```

## Rimozione cron

```bash
./scripts/backup/uninstall_cron.sh
```

## Log

```bash
tail -f /var/log/community_server/backup.log
```

## Restore

```bash
./scripts/backup/restore_mysql.sh /srv/backups/community_server/mysql/community_mysql_YYYYMMDD_HHMMSS.sql.gz
```

## Google Drive

Configurare `rclone` una volta:

```bash
rclone config
```

Nel file `backup.env`:

```bash
ENABLE_RCLONE_UPLOAD=true
RCLONE_REMOTE=gdrive:xr_tour_guide_backups/community_server
```
`