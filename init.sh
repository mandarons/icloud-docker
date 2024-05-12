#!/bin/sh
PUID=${PUID:-1000}
PGID=${PGID:-1000}
echo "Using UID as ${PUID} and GID as ${PGID} ..."
doas groupmod -o -g "$PGID" icd
doas usermod -o -u "$PUID" icd
echo "Changing ownership of /app/icloud ..."
doas chown -R icd:icd /app/icloud
python -u ./src/main.py