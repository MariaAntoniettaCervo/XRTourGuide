# Backup XR Tour Guide

Sistema di backup per:

- MySQL
- MinIO
- upload opzionale su Google Drive tramite rclone
- retention configurabile

## Setup sulla macchina remota

Da dentro `xr_tour_guide`:

```bash
cp scripts/backup/backup.env.example scripts/backup/backup.env
nano scripts/backup/backup.env
chmod +x scripts/backup/*.sh
