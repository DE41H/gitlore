#!/bin/sh
set -e

python manage.py migrate --skip-checks

exec "$@"
