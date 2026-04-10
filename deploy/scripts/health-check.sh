#!/bin/bash
# Quick health check for all StockSight services

echo "=== StockSight Health Check ==="
echo "Date: $(date)"
echo ""

# Web app
curl -sf http://localhost:5000/api/predictions/latest > /dev/null \
    && echo "[OK]   Web app" \
    || echo "[FAIL] Web app"

# Database
DB_SIZE=$(du -h /opt/stocksight/data/predictions.db 2>/dev/null | cut -f1)
echo "[INFO] Database: ${DB_SIZE:-not found}"

# Disk usage
echo "[INFO] Disk: $(df -h / | tail -1 | awk '{print $5}') used"

# Memory
echo "[INFO] RAM: $(free -h | grep Mem | awk '{print $3 "/" $2}')"

# Timer status
echo ""
echo "=== Timer Status ==="
systemctl list-timers 'stocksight-*' --no-pager 2>/dev/null || echo "No timers found"

# Recent service failures
echo ""
echo "=== Recent Failures (last 24h) ==="
journalctl -u 'stocksight-*' --since "24 hours ago" -p err --no-pager -q 2>/dev/null | tail -10 || echo "None"
