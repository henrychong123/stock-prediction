#!/bin/bash
# Daily SQLite backup — safe even with WAL mode and concurrent access

BACKUP_DIR="/opt/stocksight/backups"
DB_PATH="/opt/stocksight/data/predictions.db"
DATE=$(date +%Y%m%d)

mkdir -p "$BACKUP_DIR"

# Use SQLite's .backup command (safe, handles WAL mode)
sqlite3 "$DB_PATH" ".backup '${BACKUP_DIR}/predictions-${DATE}.db'"

# Compress
gzip -f "${BACKUP_DIR}/predictions-${DATE}.db"

# Keep only last 7 days
find "$BACKUP_DIR" -name "predictions-*.db.gz" -mtime +7 -delete

echo "Backup complete: predictions-${DATE}.db.gz ($(du -h ${BACKUP_DIR}/predictions-${DATE}.db.gz | cut -f1))"
