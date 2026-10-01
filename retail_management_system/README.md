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

## Notes

- The app runs with Django's development server in this local Docker setup.
- The settings are environment-driven so you can switch hosts, debug mode, and secret keys without editing code.
