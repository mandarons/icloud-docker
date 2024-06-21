#!/bin/sh
echo '
====================================================
To support this project, please consider sponsoring.
https://github.com/sponsors/mandarons
https://www.buymeacoffee.com/mandarons
====================================================
'
cd /app && export PYTHONPATH=/app && export PATH=/venv/bin:$PATH && python ./src/main.py