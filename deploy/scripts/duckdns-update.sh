#!/bin/bash
# DuckDNS IP updater — runs via cron every 5 minutes
# Edit DOMAIN and TOKEN before first use

DOMAIN="stocksight"
TOKEN="YOUR_DUCKDNS_TOKEN_HERE"

curl -s "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=" \
    -o /var/log/stocksight/duckdns.log
