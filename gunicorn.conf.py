"""Gunicorn configuration for production deployment."""

import os

bind = "127.0.0.1:5000"
workers = 3
timeout = 120
accesslog = "/var/log/stocksight/web-access.log"
errorlog = "/var/log/stocksight/web-error.log"
preload_app = True

# Signal to app.py to pre-load models during Gunicorn startup
os.environ["GUNICORN_PRELOAD"] = "1"
