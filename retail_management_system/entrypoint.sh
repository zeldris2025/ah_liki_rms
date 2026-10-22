#!/bin/sh
set -e

# First start: bring the existing database (users, logins, clients, sales...) into the Docker volume.
# Copies ./db.sqlite3 when the volume's database is missing or has no users yet; never overwrites one in use.
export SEED_DATABASE="${SEED_DATABASE:-/app/db.sqlite3}"
if [ -n "$DATABASE_PATH" ] && [ "$DATABASE_PATH" != "$SEED_DATABASE" ] && [ -f "$SEED_DATABASE" ]; then
    python - <<'EOF'
import os, sqlite3

target, seed = os.environ['DATABASE_PATH'], os.environ['SEED_DATABASE']


def users(path):
    try:
        with sqlite3.connect(path) as db:
            return db.execute('SELECT COUNT(*) FROM auth_user').fetchone()[0]
    except sqlite3.Error:
        return 0


if not os.path.exists(target) or users(target) == 0:
    os.makedirs(os.path.dirname(target), exist_ok=True)
    src, dst = sqlite3.connect(seed), sqlite3.connect(target)
    src.backup(dst)   # a consistent copy even if the local server is writing to it
    src.close(), dst.close()
    print(f'Copied {seed} into {target} ({users(target)} users).')
EOF
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear || true

exec "$@"
