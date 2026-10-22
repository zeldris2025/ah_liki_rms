#!/bin/sh
# Azure App Service startup command (Configuration → General settings → Startup Command):  sh startup.sh
# Live data goes under /home/data, App Service's persistent storage, so new deployments never replace it:
#   /home/data/db.sqlite3   the database (copied from the deployed db.sqlite3 on the very first start)
#   /home/data/media        uploaded photos     /home/data/exports  daily sales files
set -e
cd "$(dirname "$0")"

# The same paths settings.py uses on App Service
DATA_DIR="${DATA_DIR:-/home/data}"
export DATABASE_PATH="${DATABASE_PATH:-$DATA_DIR/db.sqlite3}"
MEDIA_ROOT="${MEDIA_ROOT:-$DATA_DIR/media}"
export SEED_DATABASE="$PWD/db.sqlite3"
mkdir -p "$DATA_DIR" "$MEDIA_ROOT" "$DATA_DIR/exports/orders"

# Photos that came with the code: copy any that aren't there yet (never overwrites uploads)
if [ -d media ]; then
    cp -rn media/. "$MEDIA_ROOT"/ || true
fi

# Resend failed FE order WhatsApp messages in the background, once the migrations below have run
if [ -n "$WAHA_URL" ]; then
    (sleep 90; exec python manage.py whatsapp retry --loop) &
fi

# entrypoint.sh: seed the database on first start, migrate, collect static files; then the app server.
# --timeout 230 matches App Service's own request limit.
exec sh entrypoint.sh gunicorn retail_management_system.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" --workers "${GUNICORN_WORKERS:-2}" --timeout 230 --access-logfile -
