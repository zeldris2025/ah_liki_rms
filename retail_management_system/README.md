# Retail Management System

This project is a Django application for shop management, orders, and sales reporting.

## Local Docker Desktop setup

1. Make sure Docker Desktop is running on your machine.
2. From the project root, copy the environment template if you need custom local settings:

```bash
copy .env.example .env
```

3. Build and run the app:

```bash
docker compose up --build
```

4. Open the app in your browser:

```text
http://localhost:8000
```

## Useful commands

```bash
docker compose up --build

docker compose down

docker compose logs -f web
```

## Data persistence

The SQLite database is stored in the Docker volume named `sqlite_data`, so data persists between container restarts.

On first start, `entrypoint.sh` copies `db.sqlite3` from the project folder into the volume (users, logins, clients,
sales, everything), as long as the volume's database is missing or has no users yet. After that the volume is the live
database: changes made in Docker don't go back to `db.sqlite3`, and later changes to `db.sqlite3` aren't copied in again.

To re-copy the local database into Docker (this **replaces** everything in the Docker database):

```bash
docker compose down
docker volume rm retail_management_system_sqlite_data
docker compose up -d
```

`docker compose down -v` also deletes the volume, so only use it when you mean to start over from `db.sqlite3`.

## Notes

- The app runs with Django's development server in this local Docker setup.
- For Azure App Service (gunicorn via `startup.sh`, `DEBUG` off, data in `/home/data`) see [DEPLOY_AZURE.md](DEPLOY_AZURE.md).
- The settings are environment-driven so you can switch hosts, debug mode, and secret keys without editing code.
