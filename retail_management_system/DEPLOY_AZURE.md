# Deploying to Azure App Service

The system runs as a **Python web app on Azure App Service (Linux)**. Azure gives it an address like
`https://<app-name>.azurewebsites.net`, and the app uses that automatically: no domain needs to be set up front.

| What                          | Where on App Service                                                     |
|-------------------------------|---------------------------------------------------------------------------|
| The app (gunicorn)            | Started by `startup.sh`                                                  |
| WhatsApp retry loop           | Also started by `startup.sh`, in the background (when `WAHA_URL` is set) |
| Database                      | `/home/data/db.sqlite3` (copied from the deployed `db.sqlite3` on first start) |
| Uploaded photos               | `/home/data/media` (photos in the deployed `media/` are copied in once)  |
| Daily sales files             | `/home/data/exports/orders`                                              |
| Secrets and settings          | App Service → **Environment variables** (not `.env`)                     |

`/home` is App Service's persistent storage, so redeploying the code never replaces the live database or uploads.

## 1. Create the Web App

Azure portal → **App Services → Create → Web App**:

- Publish: **Code**. Runtime stack: **Python 3.12**. Operating system: **Linux**.
- Pricing plan: **Basic B1** or higher (Free/Shared can't keep the app running, which the WhatsApp retry loop needs).
- Keep it to **one instance**: the database is a single SQLite file. Don't turn on scale-out.

After it's created:

1. **Configuration → General settings** (or **Settings → Configuration**):
   - Startup Command: `sh startup.sh`
   - Always On: **On**
   - Save.
2. **Environment variables → App settings**: add the settings in step 2 below, then **Apply**.

## 2. Settings (the email key and the rest)

Add each one as an App setting (Name = left side, Value = right side). Make random values with
`python -c "import secrets; print(secrets.token_urlsafe(50))"`.

| Name                              | Value                                                                    |
|-----------------------------------|---------------------------------------------------------------------------|
| `SCM_DO_BUILD_DURING_DEPLOYMENT`  | `true` (installs `requirements.txt` on deploy)                           |
| `SECRET_KEY`                      | a long random value (required; the app won't start without it)          |
| `OFFICE365_TENANT_ID`             | Entra ID → App registrations → your app → Overview → Directory (tenant) ID |
| `OFFICE365_CLIENT_ID`             | same page → Application (client) ID                                      |
| `OFFICE365_CLIENT_SECRET`         | Certificates & secrets → New client secret → copy the **Value**          |
| `OFFICE365_SENDER`                | the mailbox emails come from, e.g. `orders@ahliki.ws`                     |
| `DEFAULT_FROM_EMAIL`              | same as the sender                                                       |
| `OFFICE365_ORDER_EMAILS`          | who gets new FE orders, comma-separated                                  |
| `OFFICE365_ISSUE_EMAILS`          | who gets new FE issues                                                   |
| `OFFICE365_WHATSAPP_ALERT_EMAILS` | who hears when a WhatsApp message fails                                  |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ORDERS_CHAT_ID` | if you use Telegram                                        |
| `WAHA_URL`, `WAHA_API_KEY`, `WAHA_SESSION`, `WHATSAPP_ORDERS_CHAT_ID` | see "WhatsApp" below                  |

The Office 365 app registration needs **API permissions → Microsoft Graph → Application permissions → Mail.Send**,
with **Grant admin consent** clicked. If the office server already sends emails, copy its values from its `.env`.

You don't need `DEBUG`, `SITE_URL` or `ALLOWED_HOSTS`: on App Service, debug is off and the address is the app's own
`azurewebsites.net` name.

## 3. Deploy the code (from VS Code)

1. Install the **Azure App Service** extension and sign in to Azure.
2. In the Explorer, right-click the **`retail_management_system`** folder (the one with `manage.py`) →
   **Deploy to Web App…** → pick the app.

`.vscode/settings.json` keeps `.env`, `venv`, `sessions`, `exports` and other local files out of the upload. The
current `db.sqlite3` and `media/` do go up: they seed the live database and photos the first time only.

The first start takes a few minutes (packages install, the database is copied in, migrations run).
Watch it under **Monitoring → Log stream**. Then open `https://<app-name>.azurewebsites.net`.

To redeploy after code changes, run **Deploy to Web App…** again.

## WhatsApp (WAHA)

WAHA can't run inside the Python app, so it gets its own small Web App:

1. **Create → Web App**, Publish: **Container**, Linux, on the **same App Service plan**.
   Image source: Docker Hub (public), image `devlikeapro/waha`.
2. Its **Environment variables**:
   - `WEBSITES_PORT=3000`
   - `WAHA_API_KEY`, `WAHA_DASHBOARD_USERNAME`, `WAHA_DASHBOARD_PASSWORD` (long random values)
   - `WHATSAPP_SWAGGER_USERNAME` and `WHATSAPP_SWAGGER_PASSWORD` (same as the dashboard ones)
   - `WHATSAPP_DEFAULT_ENGINE=WEBJS`, `WHATSAPP_RESTART_ALL_SESSIONS=True`
3. Keep the WhatsApp login across restarts: create a Storage account with a file share (e.g. `waha-sessions`),
   then in the WAHA app: **Configuration → Path mappings → New Azure Storage Mount**, mount path `/app/.sessions`.
4. Turn on **Always On** for it as well.
5. Open `https://<waha-app>.azurewebsites.net/dashboard`, log in, start the `default` session and scan the QR code.
6. In the **main** app's settings: `WAHA_URL=https://<waha-app>.azurewebsites.net`, the same `WAHA_API_KEY`,
   `WAHA_SESSION=default` and `WHATSAPP_ORDERS_CHAT_ID`.

One WhatsApp login can't run in two places, so stop WAHA on the office server when you switch.

## Adding your own domain later

1. App → **Custom domains → Add custom domain**. Follow the DNS records it shows (a CNAME and a TXT record),
   then add the free **App Service Managed Certificate** for HTTPS.
2. App setting `SITE_URL=https://rms.ahliki.ws` (your domain), then Apply.

Email links (e.g. *Open Car Allocations*) follow `SITE_URL`. The `azurewebsites.net` address keeps working too.

## Everyday tasks

- **Logs**: Monitoring → Log stream.
- **Management commands** (create an admin, send a test email): Development Tools → **SSH**. It opens in the app
  folder, and the commands use the live database in `/home/data` by themselves:
  ```bash
  python manage.py createsuperuser
  python manage.py office365 test --to you@ahliki.ws
  ```
  If `manage.py` isn't found, run `cd $APP_PATH` first.
- **Changing a setting**: edit it under Environment variables → Apply (the app restarts by itself).

## Backups and limits

- Turn on **Backups** for the app (Basic plan or higher). It includes `/home`, so the database and photos.
- For a quick database copy, in SSH:
  `python -c "import sqlite3; sqlite3.connect('/home/data/db.sqlite3').backup(sqlite3.connect('/home/data/backup.sqlite3'))"`
- App Service ends any request after **230 seconds**. A very large CSV import that takes longer will fail; split it
  into smaller files.
