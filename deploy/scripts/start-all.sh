#!/bin/bash
# Start all StockSight services and timers

echo "Starting StockSight services..."

sudo systemctl start stocksight-web.service
echo "  [OK] Web dashboard"

sudo systemctl start stocksight-price-tracker.timer
sudo systemctl start stocksight-news-tracker.timer
sudo systemctl start stocksight-catalyst.timer
sudo systemctl start stocksight-daily-collector.timer
sudo systemctl start stocksight-batch-predict.timer
sudo systemctl start stocksight-backup.timer
echo "  [OK] All 6 timers started"

echo ""
echo "Active timers:"
systemctl list-timers 'stocksight-*' --no-pager
