#!/bin/sh
PUID=${PUID:-1000}
PGID=${PGID:-1000}
UMASK=${UMASK:-022}
echo '
====================================================
To support this project, please consider sponsoring.
https://github.com/sponsors/mandarons
https://www.buymeacoffee.com/mandarons 
====================================================
'
echo "Using UID as ${PUID}, GID as ${PGID} and UMASK as ${UMASK}..."
addgroup --gid $PGID icd;
adduser -D --uid $PUID icd -G icd; \
echo "icd ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/icd && sudo chmod 0440 /etc/sudoers.d/icd
echo "Changing ownership of /app ... This operation may take significantly longer depending on number of files in your local copy of icloud."
chown -R icd:icd /app
umask $UMASK
su - icd -c "umask $UMASK && cd /app && export PYTHONPATH=/app && export PATH=/venv/bin:$PATH && python ./src/main.py"