#!/usr/bin/env bash
# Runs the MRM tests against a real PostgreSQL/PostGIS database (never SQLite).
# Usage:  ./run_tests_postgres.sh            # starts the compose database, runs the tests
#         DB_HOST=... DB_PORT=... DB_USER=... DB_PASSWORD=... DB_NAME=... ./run_tests_postgres.sh   # use your own server
set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${DB_HOST:-}" ]; then
  docker compose -f docker-compose.postgis.yml up -d --wait
  export DB_HOST=localhost DB_PORT=5433 DB_NAME=uoms DB_USER=uoms DB_PASSWORD=uoms_test_password
fi
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-test-only-secret-key}"

python manage.py check
python manage.py makemigrations --check --dry-run      # must report "No changes detected"
# The Django test runner creates/destroys its own throw-away "test_<DB_NAME>" database,
# so the DB user needs CREATEDB (and permission to CREATE EXTENSION postgis).
python manage.py test apps.mrm "$@"
