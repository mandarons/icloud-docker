#!/bin/sh
PUID=${PUID:-1000}
PGID=${PGID:-1000}
echo '
====================================================
To support this project, please consider sponsoring.
https://github.com/sponsors/mandarons/
====================================================
'
echo "Using UID as ${PUID} and GID as ${PGID} ..."
addgroup --gid $PGID icd;
adduser -D --uid $PUID icd -G icd; \
echo "icd ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/icd && sudo chmod 0440 /etc/sudoers.d/icd
echo "Changing ownership of /app ..."
chown -R icd:icd /app
su - icd -c "cd /app && export PYTHONPATH=/app && export PATH=/venv/bin:$PATH && python ./src/main.py"