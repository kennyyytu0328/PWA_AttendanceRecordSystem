# Production Environment Setting Guide

GoGoFresh Attendance — step-by-step guide for deploying to a production environment.

> This guide assumes you already got the app running locally (`docker compose up -d` against `docker-compose.yml`). If not, start there first.

---

## 0. Prerequisites

- A server / VM with Docker ≥ 24 and Docker Compose v2
- A registered **public domain** you control (e.g., `attendance.yourdomain.com`)
  - WebAuthn/fingerprint login requires a real registrable domain — IP addresses and `.local` names will not work for biometrics
- **Two DNS records** pointing to your server's public IP:
  - `attendance.yourdomain.com` → frontend
  - `api.yourdomain.com` → backend (optional if you proxy `/api` through the same host — see §6)
- Ports **80** and **443** reachable from the internet
- Ability to run: `openssl rand -hex 32` (for generating secrets)

---

## 1. Clone the repo onto the server

```bash
git clone <your-repo-url> /opt/gogofresh-attendance
cd /opt/gogofresh-attendance
```

---

## 2. Generate secrets

Run these on the server (or securely copy the results):

```bash
# JWT signing key (keep secret — leak = auth bypass)
openssl rand -hex 32

# PostgreSQL password
openssl rand -base64 24
```

Save both values somewhere secure — you'll paste them into the `.env` files in the next step.

---

## 3. Fill in environment templates

The repo ships **three** template files. Copy each, then edit the copy with real values.

### 3.1 Backend env

```bash
cp backend/.env.production.example backend/.env
```

Then edit `backend/.env`:

| Variable | Value to set |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://attendance_user:<POSTGRES_PASSWORD>@db:5432/attendance` — the hostname `db` resolves to the postgres container in the compose network. Use a managed-DB connection string instead if applicable. |
| `SECRET_KEY` | Paste the `openssl rand -hex 32` value from §2 |
| `ALGORITHM` | `HS256` (don't change unless you know why) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` default; raise for longer sessions, lower for stricter security |
| `CORS_ORIGINS` | `["https://attendance.yourdomain.com"]` — exact origin, no trailing slash |
| `CORS_ORIGIN_REGEX` | Leave **unset/commented out**. The regex is for LAN dev only |
| `WEBAUTHN_RP_ID` | `attendance.yourdomain.com` — **bare host**, no scheme, no port, no path |
| `WEBAUTHN_RP_NAME` | Any display name shown in the biometric prompt (e.g., `GoGoFresh Attendance`) |
| `WEBAUTHN_ORIGIN` | `https://attendance.yourdomain.com` — full origin, must be HTTPS |
| `ROOT_PATH` | Leave empty for domain-root deploys. Set to e.g. `/gogoffcc-arms` when an upstream reverse proxy serves the app under a sub-path (see §6 Option C) |

> **WebAuthn gotcha**: `WEBAUTHN_RP_ID` and `WEBAUTHN_ORIGIN` are pinned into each registered authenticator. If you change either after users have registered fingerprints, all of those credentials become invalid and must be re-registered.

### 3.2 Frontend env

```bash
cp frontend/.env.production.example frontend/.env.production
```

Edit `frontend/.env.production`:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.yourdomain.com` (or `""` if you proxy `/api` through the frontend domain — see §6 option B; or `/<prefix>` for sub-path deploys — see §6 option C) |
| `NEXT_PUBLIC_BASE_PATH` | Leave empty for domain-root deploys. Set to e.g. `/gogoffcc-arms` when an upstream reverse proxy serves the app under a sub-path (see §6 Option C). Must match backend `ROOT_PATH`. |

> **Important**: `NEXT_PUBLIC_*` is **compiled into the JS bundle at build time**, not read at runtime. If you change either value, you must rebuild the frontend container.

### 3.3 Compose-level env

This is the `.env` **at the repo root** that Docker Compose reads automatically for variable interpolation in `docker-compose.prod.yml`:

```bash
cat > .env <<'EOF'
POSTGRES_USER=attendance_user
POSTGRES_PASSWORD=<paste openssl rand -base64 24 output here>
POSTGRES_DB=attendance
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
EOF

chmod 600 .env
```

The `POSTGRES_PASSWORD` here **must match** what you used in `backend/.env` → `DATABASE_URL`.

---

## 4. Build and start the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes ~3–5 minutes. Verify everything is up:

```bash
docker compose -f docker-compose.prod.yml ps
```

All three services (`db`, `backend`, `frontend`) should show `Up (healthy)` / `Up`.

---

## 5. Run database migrations

The compose file does **not** auto-migrate on startup (to avoid surprises on rollback). Run migrations manually after the first deploy and after every code update:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

Expected output ends with `INFO  [alembic.runtime.migration] Running upgrade ... -> c3d4e5f6a7b8, add_absent_status`.

### 5.1 Create the initial ADMIN user

The dev `seed.py` script creates five test users with weak passwords — **do not run it in production**. Instead, create one real ADMIN user directly:

```bash
docker compose -f docker-compose.prod.yml exec backend python - <<'PYEOF'
import asyncio, datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings
from app.models.employee import Employee, Role
from app.utils.password import hash_password

async def main():
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        admin = Employee(
            emp_id="ADMIN",
            name="System Administrator",
            department="IT",
            role=Role.ADMIN,
            hashed_password=hash_password("CHANGE_THIS_STRONG_PASSWORD"),
            shift_start_time=datetime.time(9, 0),
            shift_end_time=datetime.time(18, 0),
        )
        s.add(admin)
        await s.commit()
    await engine.dispose()
    print("Admin created. Log in and immediately change the password.")

asyncio.run(main())
PYEOF
```

After logging in as this ADMIN, use the admin panel to create HR and other users — don't create non-ADMIN users via SQL.

### 5.2 Seed initial system config

Log in as ADMIN, then via the admin panel set:

- **Office location** (latitude/longitude — used for the 2 km WFH/OFFICE geofence)
- **Departments** (pre-set list for employee creation dropdowns)
- **Grace period** (minutes; default 5)
- **Workday calendar** — click "更新全年行事曆" to fetch the Taiwan calendar from the CDN

---

## 6. Reverse proxy + TLS

The compose file exposes the backend and frontend **only inside the Docker network** (`expose:` not `ports:`). You need a reverse proxy in front to terminate TLS and route public traffic.

Two common options:

### Option A — Caddy (zero-config TLS via Let's Encrypt)

Create `/etc/caddy/Caddyfile`:

```caddy
attendance.yourdomain.com {
    reverse_proxy localhost:3000
}

api.yourdomain.com {
    reverse_proxy localhost:8000
}
```

Install and start Caddy on the host:

```bash
sudo apt install caddy
sudo systemctl reload caddy
```

Caddy will automatically obtain and renew TLS certificates.

Then publish the container ports on localhost only — in `docker-compose.prod.yml`, replace `expose:` with:

```yaml
  backend:
    ports:
      - "127.0.0.1:8000:8000"
  frontend:
    ports:
      - "127.0.0.1:3000:3000"
```

### Option B — Same-origin with nginx (single domain, API proxied through `/api`)

If you'd rather not publish `api.yourdomain.com`, serve everything from `attendance.yourdomain.com`:

```nginx
server {
    listen 443 ssl http2;
    server_name attendance.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/attendance.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/attendance.yourdomain.com/privkey.pem;

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

If you use Option B, set `NEXT_PUBLIC_API_URL=""` (empty string) in `frontend/.env.production` so fetches go to the same origin.

### Option C — Behind an upstream reverse proxy at a sub-path

Use this when you do **not** control the public domain — a separate upstream proxy (run by a hosting team or shared platform) terminates TLS and forwards a sub-path to your server. Example: `https://www.gogoffcc.com/gogoffcc-arms` is served by an upstream that proxies `/gogoffcc-arms/*` to your stack.

#### Upstream proxy configuration (path-based stripping)

Coordinate with whoever runs the upstream so it strips the prefix for API calls but **preserves** it for frontend requests. Without this split, Next.js will either 404 (strip everywhere) or generate broken link URLs (preserve everywhere).

Reference Nginx config the upstream operator needs:

```nginx
# Strip the prefix for backend API calls
location /gogoffcc-arms/api/ {
    proxy_pass http://your-server-ip:8000/api/;   # trailing slash strips the prefix
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
}

# Preserve the prefix for the frontend
location /gogoffcc-arms/ {
    proxy_pass http://your-server-ip:3000;        # NO trailing slash → prefix preserved
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

#### Your-server-side configuration

Set both env files to the matching prefix:

`backend/.env`:

```
ROOT_PATH=/gogoffcc-arms
WEBAUTHN_RP_ID=www.gogoffcc.com              # bare host — never includes the path
WEBAUTHN_ORIGIN=https://www.gogoffcc.com     # origin only — never includes the path
CORS_ORIGINS=["https://www.gogoffcc.com"]
```

`frontend/.env.production` and root `.env`:

```
NEXT_PUBLIC_API_URL=/gogoffcc-arms             # api client appends /api/... so this is the prefix only
NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms
```

Publish container ports on your server's interface that the upstream can reach (e.g. a private network IP or `127.0.0.1` if upstream is on the same box) — replace the `expose:` blocks in `docker-compose.prod.yml`:

```yaml
  backend:
    ports:
      - "<internal-ip>:8000:8000"
  frontend:
    ports:
      - "<internal-ip>:3000:3000"
```

The `docker-compose.prod.yml` already runs uvicorn with `--proxy-headers --forwarded-allow-ips=*`, which is required so FastAPI trusts `X-Forwarded-Proto: https` from the upstream. Without it, WebAuthn origin checks see `http://` and reject all biometric logins.

#### Sanity-check matrix

After the stack is up and the upstream operator has reloaded their proxy:

| URL the browser hits | What each hop sees |
|---|---|
| `https://www.gogoffcc.com/gogoffcc-arms/login` | Upstream → `your-server:3000/gogoffcc-arms/login` → Next.js (`basePath=/gogoffcc-arms`) serves login page ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/api/auth/login` | Upstream → `your-server:8000/api/auth/login` → FastAPI router (`prefix=/api/auth`) handles it ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/_next/static/...` | Upstream preserves prefix → Next.js serves asset ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/manifest.webmanifest` | Generated by `app/manifest.ts`, `start_url` and `scope` already include the prefix ✓ |

> **WebAuthn note**: Because the upstream — not your server — owns the TLS termination for `www.gogoffcc.com`, you do not need your own cert. But the browser still records origin = `https://www.gogoffcc.com` for every registered credential. If the upstream's domain ever changes, all existing fingerprints become invalid and must be re-registered.

---

## 7. Smoke test

```bash
# Backend health
curl https://api.yourdomain.com/health
# → {"status":"ok"}

# Frontend renders
curl -I https://attendance.yourdomain.com
# → HTTP/2 200

# CORS preflight from the frontend origin
curl -I -X OPTIONS https://api.yourdomain.com/api/auth/login \
  -H "Origin: https://attendance.yourdomain.com" \
  -H "Access-Control-Request-Method: POST"
# → HTTP/2 200 and Access-Control-Allow-Origin header present
```

Open `https://attendance.yourdomain.com` in a browser:

1. Log in with `ADMIN` / your initial password
2. Change the password immediately (admin panel → edit self)
3. Register a fingerprint — should succeed on HTTPS
4. Log out, log back in via fingerprint

### 7.1 Sub-path deployment smoke test (Option C only)

Run this once after the upstream operator has reloaded their proxy, before announcing the URL to users. Substitute your real values for `<HOST>` (`www.gogoffcc.com`) and `<PREFIX>` (`/gogoffcc-arms`).

| # | Step | Pass criterion |
|---|------|----------------|
| 1 | Browse to `https://<HOST><PREFIX>/login` | Login page renders. No 404. URL bar still shows the prefix. |
| 2 | DevTools → Network → reload the page | All `_next/static/*` requests are under `<PREFIX>/_next/...` and return 200. Zero requests hit the root `/_next/...`. |
| 3 | Submit the login form with `ADMIN` credentials | Single POST to `<PREFIX>/api/auth/login` returns 200 with a JWT. No 404, no CORS error in console. |
| 4 | DevTools → Application → Manifest | `start_url` and `scope` both equal `<PREFIX>/`. Icons resolve under `<PREFIX>/icons/...`. |
| 5 | Register a fingerprint (admin panel → enable WebAuthn) | Biometric prompt shows RP name. No console error mentioning origin or RP ID mismatch. |
| 6 | Log out, then log back in via fingerprint | Authentication succeeds. JWT issued. Lands on the dashboard at `<PREFIX>/dashboard`. |
| 7 | Browse to `https://<HOST><PREFIX>/docs` | FastAPI Swagger UI loads. All endpoint paths in the spec are shown under `<PREFIX>` (because `ROOT_PATH` is set). "Try it out" requests succeed. |
| 8 | Hit `https://<HOST><PREFIX>/api/health` directly | Returns `{"status":"ok"}`. Confirms the upstream `/api/` strip rule is wired up. |
| 9 | (Mobile, optional) Install the PWA from the URL | "Add to Home Screen" succeeds; launching the installed app opens at `<PREFIX>/`, not the host root. |

**If step 5 or 6 fails with an origin-mismatch error**, the upstream is not forwarding `X-Forwarded-Proto: https` — uvicorn is seeing the request as HTTP and rejecting WebAuthn. Confirm `--proxy-headers --forwarded-allow-ips=*` is on the uvicorn command (already set in `docker-compose.prod.yml`) and that the upstream's `proxy_set_header X-Forwarded-Proto $scheme;` line is present.

**If step 2 shows `_next/static` 404s**, the upstream is stripping `<PREFIX>` on the frontend `location` block — it should preserve it (no trailing slash on `proxy_pass`). See §6 Option C.

**If step 8 returns 404 but step 1 works**, the upstream's `/api/` location block is missing the trailing-slash strip — fix the upstream's `proxy_pass http://your-server:8000/api/;` (the trailing slash is what does the strip).

---

## 8. Backups

The postgres volume is the only stateful piece. Set up a nightly backup:

```bash
# /etc/cron.daily/attendance-backup
#!/bin/bash
set -e
BACKUP_DIR=/var/backups/attendance
mkdir -p "$BACKUP_DIR"
cd /opt/gogofresh-attendance
docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U attendance_user attendance \
    | gzip > "$BACKUP_DIR/attendance-$(date +%F).sql.gz"
# retain 30 days
find "$BACKUP_DIR" -name '*.sql.gz' -mtime +30 -delete
```

```bash
sudo chmod +x /etc/cron.daily/attendance-backup
```

Test restore periodically — a backup you haven't tested is not a backup.

---

## 9. Upgrades

```bash
cd /opt/gogofresh-attendance
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

Rollback: `git checkout <previous-commit>` then repeat. Migrations are generally forward-only — have a database backup before any release that includes schema changes.

---

## 10. Checklist before going live

- [ ] `SECRET_KEY` is 32+ random bytes, not the `change-me-in-production` default
- [ ] `POSTGRES_PASSWORD` is strong and is the only place it's written down (not in git)
- [ ] `backend/.env`, `frontend/.env.production`, and root `.env` are all `chmod 600` and **not committed**
- [ ] `CORS_ORIGIN_REGEX` is unset in `backend/.env`
- [ ] DNS A/AAAA records resolve to the server
- [ ] TLS certificate issued and auto-renewing (Caddy handles this; certbot if using nginx)
- [ ] `https://api.yourdomain.com/health` returns 200
- [ ] Fingerprint register + login works end-to-end in a browser
- [ ] Initial ADMIN password changed away from the bootstrap value
- [ ] Nightly postgres backup cron is installed and at least one backup has run successfully
- [ ] `docker compose ps` shows all services healthy after a reboot (set `restart: unless-stopped` is already in the template)

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Login fails with `ERR_FAILED` in browser console | `NEXT_PUBLIC_API_URL` wrong | Check the value, rebuild frontend (`docker compose -f docker-compose.prod.yml up -d --build frontend`) |
| Login preflight returns 400 | Origin not in `CORS_ORIGINS` | Add the exact origin to `backend/.env`, restart backend |
| Fingerprint prompt never appears | HTTP (not HTTPS), or `WEBAUTHN_RP_ID` mismatch | Confirm HTTPS is working; `RP_ID` must be the bare host of the origin |
| "Invalid credentials" on correct password | DB not migrated (hashed_password column missing) or wrong SECRET_KEY across restarts | `alembic upgrade head`; ensure `SECRET_KEY` is stable across deploys |
| CORS error only on one endpoint | That endpoint returns 500 before CORS headers are added | Check backend logs: `docker compose -f docker-compose.prod.yml logs backend --tail 100` |
| Postgres connection refused | Backend started before DB was ready | Already handled by `depends_on.condition: service_healthy`; if it persists, check the DB container logs |
| Taiwan calendar shows "not loaded" | CDN fetch blocked by firewall | Curl test from inside the backend container: `docker compose exec backend curl -I https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/2026.json` |
