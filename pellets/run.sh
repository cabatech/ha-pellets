#!/bin/sh
set -e
# Premier démarrage : reprend la base de l'ancienne installation si elle a été déposée dans /share.
if [ ! -f /data/pellets.db ] && [ -f /share/pellets/pellets.db ]; then
  cp /share/pellets/pellets.db /data/pellets.db
  echo "Base importée depuis /share/pellets/pellets.db"
fi
exec uvicorn app.main:app --host "$PELLETS_HOST" --port "$PELLETS_PORT"
