# Production Environment Setting Guide

GoGoFresh Attendance — step-by-step guide for deploying to a production environment.

> This guide assumes you already got the app running locally (`docker compose up -d` against `docker-compose.yml`). If not, start there first.

## Topology (as actually deployed)

```
┌─ Browser ─────────────────────────────────────────────────────────┐
│ HTTPS                                                              │
│   ↓                                                                │
│ www.gogoffcc.com  (upstream nginx — owned by colleague, TLS here) │
│   ↓ HTTP, /gogoffcc-arms/*  →  <our-server-internal-ip>:80         │
│   ↓                                                                │
│ Our server (alg-compute-0, 10.140.0.4)                            │
│   ├─ host nginx :80  (already serves /gogoffcc-pms/ and others)   │
│   │     ├─ /gogoffcc-arms/api/  → 127.0.0.1:8120/api/  (strip)    │
│   │     └─ /gogoffcc-arms/      → 127.0.0.1:3000       (preserve) │
│   ├─ docker compose -f docker-compose.prod.yml                    │
│   │     ├─ frontend  (Next.js, 127.0.0.1:3000, basePath=...)      │
│   │     └─ backend   (FastAPI, 127.0.0.1:8120 → uvicorn :8000)    │
│   └─ Postgres 14+    (host service, port 5432, shared with        │
│                       other apps on this VM — NOT in Docker)      │
└────────────────────────────────────────────────────────────────────┘
```

**Key facts about this setup:**

1. **TLS terminates upstream**, not on our server. Our containers speak plain HTTP on the internal network. The browser only ever sees `https://www.gogoffcc.com`, never our IP.
2. **We do not own the public domain.** WebAuthn `RP_ID` is `www.gogoffcc.com` (the upstream's host), pinned to every registered fingerprint.
3. **Sub-path deployment.** The app lives at `https://www.gogoffcc.com/gogoffcc-arms`. Both Next.js (`basePath`) and FastAPI (`root_path`) are configured for this prefix.
4. **Two nginx layers.** Upstream nginx (colleague) terminates TLS and forwards `/gogoffcc-arms/*` to our server's port 80. Our **host nginx** (already running, also serves `/gogoffcc-pms/` and other apps) holds the location blocks that do the strip/preserve split and proxies into the Docker containers on `127.0.0.1:8120` / `127.0.0.1:3000`.
5. **Coordination is minimal.** Upstream colleague just adds `/gogoffcc-arms/*` → `<our-server>:80`, mirroring the existing `/gogoffcc-pms/` rule. All the path-rewriting logic lives in our host nginx, where we own it.
6. **Container ports bind to `127.0.0.1` only**, never `0.0.0.0` — host nginx is the only thing that can reach them.

---

## 0. Prerequisites

- A server / VM with Docker ≥ 24 and Docker Compose v2
- **An existing PostgreSQL 14+ server running on the host** (the production GoGoFresh box reuses the same Postgres instance shared with other apps on the VM — see §2.5). If you'd rather run Postgres in a container, see the "bundled Postgres" note in `docker-compose.prod.yml`.
- An **internal IP / hostname** reachable from the upstream reverse proxy (e.g., a private LAN address, a VPC peer, or `127.0.0.1` if upstream runs on the same box)
- Coordination with whoever runs the upstream proxy (`www.gogoffcc.com`) — you'll hand them an Nginx snippet (see §6)
- Ability to run: `openssl rand -hex 32` (for generating secrets)

> **What you do NOT need:** your own public domain, a TLS certificate, Caddy/certbot, ports 80/443 open to the internet, or DNS records. The upstream owns all of that.

---

## 1. Clone the repo onto the server

```bash
sudo git clone <your-repo-url> /opt/gogofresh-attendance
sudo chown -R $USER:$USER /opt/gogofresh-attendance   # so later `git pull` / edits don't need sudo
cd /opt/gogofresh-attendance
ls   # expect: backend/  docs/  docker-compose.prod.yml  frontend/  ...
```

### 1.1 Authentication for Bitbucket / GitHub clones

Both Bitbucket and GitHub stopped accepting account passwords for git over HTTPS. Use one of the following:

**Bitbucket — API token** (the replacement for App Passwords, which Atlassian deprecated on 2025-09-09):
- Generate the token in Atlassian account settings → Security → **API tokens** → scope it to `Bitbucket: repositories: read` for the target repo
- At the `git clone` prompt:
  - **Username**: your Atlassian account email (e.g. `kennyyytu0328@gmail.com`)
  - **Password**: paste the API token

**GitHub — Personal Access Token (fine-grained)**:
- GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → grant `Contents: Read-only` on the target repo
- At the `git clone` prompt:
  - **Username**: your GitHub username
  - **Password**: paste the PAT

**Either platform — SSH deploy key** (cleanest long-term, no expiry, no token rotation):
- `ssh-keygen -t ed25519 -C "<server-name> deploy" -f ~/.ssh/<remote>_deploy` (no passphrase for unattended pulls)
- Paste `~/.ssh/<remote>_deploy.pub` into the repo's **Access keys** settings (Bitbucket) or **Deploy keys** (GitHub), read-only
- Add to `~/.ssh/config`:
  ```
  Host bitbucket.org    # or github.com
      User git
      IdentityFile ~/.ssh/<remote>_deploy
      IdentitiesOnly yes
  ```
- Clone via SSH URL: `git clone git@bitbucket.org:<workspace>/<repo>.git ...`

**Optional**: to avoid re-pasting the HTTPS token on every `git pull`:
```bash
git config --global credential.helper store
git pull   # paste token once; stored cleartext in ~/.git-credentials thereafter
```
Only use `store` on a server you alone have shell access to.

---

## 2. Generate secrets

Run this on the server (or securely copy the result):

```bash
# JWT signing key (keep secret — leak = auth bypass)
openssl rand -hex 32
```

Save the value somewhere secure — you'll paste it into `backend/.env` (as `SECRET_KEY`) in §3.

## 2.5 Create the application's database role and database

We are **not** running Postgres in Docker; we reuse the host's existing Postgres. So we need to provision a dedicated role + database **outside** Docker, just once.

Connect as the `postgres` superuser (peer auth — no password needed for the local Unix socket):

```bash
sudo -u postgres psql
```

Then, at the `postgres=#` prompt, generate and apply a new password:

```sql
-- Pick a strong password. Generate one in another shell with: openssl rand -hex 24
-- (Use -hex rather than -base64: base64 contains '+' and '/' which must be
--  URL-encoded when they land in DATABASE_URL. Hex is [0-9a-f] only — safe
--  in URLs, shell, JSON, everything.)
CREATE USER attendance_user WITH PASSWORD '<paste-strong-password-here>';
CREATE DATABASE attendance OWNER attendance_user;
GRANT ALL PRIVILEGES ON DATABASE attendance TO attendance_user;
\q
```

Save the password — you'll paste it into `backend/.env` → `DATABASE_URL` in the next step.

> **Why a new role**: never reuse another app's DB user. Each app gets its own role + own database — that way a credential leak or a bad migration in one app can't corrupt another.

> **If the host Postgres only allows TCP from `127.0.0.1`** (default on Ubuntu), the backend container needs to reach it via `host.docker.internal`, which `docker-compose.prod.yml` already wires up via `extra_hosts: host-gateway`. Also make sure `pg_hba.conf` allows `host all attendance_user 172.17.0.0/16 scram-sha-256` (or `md5`) — the Docker bridge network. After editing `pg_hba.conf`, `sudo systemctl reload postgresql`.

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
| `DATABASE_URL` | `postgresql+asyncpg://attendance_user:<password from §2.5>@host.docker.internal:5432/attendance` — `host.docker.internal` lets the container reach Postgres running on the Docker host. If you're bundling Postgres in a container instead, use `db` (the compose service name). |
| `SECRET_KEY` | Paste the `openssl rand -hex 32` value from §2 |
| `ALGORITHM` | `HS256` (don't change unless you know why) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` default; raise for longer sessions, lower for stricter security |
| `CORS_ORIGINS` | `["https://www.gogoffcc.com"]` — exact upstream origin, no trailing slash, no path |
| `CORS_ORIGIN_REGEX` | Leave **unset/commented out**. The regex is for LAN dev only |
| `WEBAUTHN_RP_ID` | `www.gogoffcc.com` — **bare host** of the upstream, no scheme, no port, no path |
| `WEBAUTHN_RP_NAME` | Any display name shown in the biometric prompt (e.g., `GoGoFresh Attendance`) |
| `WEBAUTHN_ORIGIN` | `https://www.gogoffcc.com` — full upstream origin, must be HTTPS, no path |
| `ROOT_PATH` | `/gogoffcc-arms` — the sub-path the upstream forwards to us. Must match `NEXT_PUBLIC_BASE_PATH` |

> **WebAuthn gotcha**: `WEBAUTHN_RP_ID` and `WEBAUTHN_ORIGIN` are pinned into each registered authenticator. If you change either after users have registered fingerprints, all of those credentials become invalid and must be re-registered.

### 3.2 Frontend env

```bash
cp frontend/.env.production.example frontend/.env.production
```

Edit `frontend/.env.production`:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `/gogoffcc-arms` — the API client appends `/api/...` to this, so set only the upstream prefix. (For alternative same-origin or separate-API-host deploys see §6.) |
| `NEXT_PUBLIC_BASE_PATH` | `/gogoffcc-arms` — must match backend `ROOT_PATH`. |

> **Important**: `NEXT_PUBLIC_*` is **compiled into the JS bundle at build time**, not read at runtime. If you change either value, you must rebuild the frontend container.

### 3.3 Compose-level env

This is the `.env` **at the repo root** that Docker Compose reads automatically for variable interpolation in `docker-compose.prod.yml`. With the host-Postgres setup, only the frontend build args need to be exposed here:

```bash
cat > .env <<'EOF'
NEXT_PUBLIC_API_URL=/gogoffcc-arms
NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms
EOF

chmod 600 .env
```

> `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` are **not** needed here — there's no `db` service in the compose file. The DB password lives only in `backend/.env` → `DATABASE_URL`. If you switch to the bundled-Postgres variant (commented in `docker-compose.prod.yml`), add them back.

---

## 4. Build and start the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes ~3–5 minutes. Verify everything is up:

```bash
docker compose -f docker-compose.prod.yml ps
```

Both services (`backend`, `frontend`) should show `Up`. (No `db` container — the host Postgres runs outside Compose.)

Sanity-check that the backend can actually reach the host Postgres:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -c "import asyncio, asyncpg, os; \
print(asyncio.run(asyncpg.connect(os.environ['DATABASE_URL'].replace('+asyncpg','')).fetch('select 1')))"
```

If this errors with "connection refused" or "no pg_hba.conf entry", revisit §2.5 — the host Postgres isn't accepting connections from the Docker bridge.

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

The compose file binds the backend and frontend ports to `127.0.0.1` only. In production we sit behind **two nginx layers**: the upstream `www.gogoffcc.com` (TLS, owned by a colleague), and our **host nginx** on `alg-compute-0:80` (which already serves several other apps including `/gogoffcc-pms/`). The host nginx is the layer that does the `/gogoffcc-arms` path-rewriting and proxies into our containers.

If you're reading this and you actually do control the public domain (rare for this project), the legacy "stand-alone TLS" options are documented at the bottom as Option A / Option B.

### Option C — Behind an upstream reverse proxy at a sub-path (production default)

#### 6.1 Host nginx (our server) — add a new location block

Append the following inside the existing `server { ... }` block in `/etc/nginx/sites-enabled/default` (right next to the existing `/gogoffcc-pms/` block):

```nginx
# === GGFF Attendance — served at /gogoffcc-arms/ ===

# Backend API — strip the /gogoffcc-arms prefix so FastAPI sees /api/...
location /gogoffcc-arms/api/ {
    proxy_pass         http://127.0.0.1:8120/api/;    # trailing slash strips the prefix
    proxy_http_version 1.1;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto https;       # upstream already terminated TLS
    proxy_set_header   X-Forwarded-Host  $host;
    proxy_read_timeout 60s;
}

# Frontend — preserve the /gogoffcc-arms prefix so Next.js basePath matches
location /gogoffcc-arms/ {
    proxy_pass         http://127.0.0.1:3000;         # NO trailing slash → prefix preserved
    proxy_http_version 1.1;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto https;
    proxy_set_header   X-Forwarded-Host  $host;
    proxy_set_header   Upgrade           $http_upgrade;
    proxy_set_header   Connection        "upgrade";
    proxy_read_timeout 60s;
}
```

Validate and reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

> Why host port **8120** for backend, not 8000: 8000 is already taken on `alg-compute-0` by the `barcode_identify` app. `docker-compose.prod.yml` publishes uvicorn (container port 8000) on host port **8120** to avoid the collision. The container-side port is unchanged.

#### 6.2 Upstream proxy (colleague's) — one new forward rule

Hand the upstream operator this one-line ask:

> Please add a location block for `/gogoffcc-arms/` that mirrors the existing `/gogoffcc-pms/` one — same target (`<our-server-ip>:80`), same TLS / `X-Forwarded-*` headers. All path rewriting is handled internally on our side.

No strip/preserve split is needed at the upstream layer because our host nginx does it.

#### 6.3 Container ports

`docker-compose.prod.yml` is already configured for this topology:

```yaml
  backend:
    ports:
      - "127.0.0.1:8120:8000"   # host:8120 → container:8000 (uvicorn)
  frontend:
    ports:
      - "127.0.0.1:3000:3000"
```

`127.0.0.1` binding means only processes on the host (i.e., host nginx) can reach these ports — nothing public, nothing on the LAN.

The `docker-compose.prod.yml` runs uvicorn with `--proxy-headers --forwarded-allow-ips=*`, which is required so FastAPI trusts `X-Forwarded-Proto: https` from host nginx. Without it, WebAuthn origin checks see `http://` and reject all biometric logins.

#### 6.4 Env values

These are also covered in §3 but repeated here for quick reference:

`backend/.env`:
```
ROOT_PATH=/gogoffcc-arms
WEBAUTHN_RP_ID=www.gogoffcc.com              # bare host — never includes the path
WEBAUTHN_ORIGIN=https://www.gogoffcc.com     # origin only — never includes the path
CORS_ORIGINS=["https://www.gogoffcc.com"]
```

`frontend/.env.production` and root `.env`:
```
NEXT_PUBLIC_API_URL=/gogoffcc-arms
NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms
```

#### 6.5 Sanity-check matrix

After host nginx is reloaded and the upstream operator has added the new forward rule:

| URL the browser hits | What each hop sees |
|---|---|
| `https://www.gogoffcc.com/gogoffcc-arms/login` | Upstream → host nginx `/gogoffcc-arms/` → `127.0.0.1:3000/gogoffcc-arms/login` → Next.js (`basePath=/gogoffcc-arms`) serves login page ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/api/auth/login` | Upstream → host nginx `/gogoffcc-arms/api/` (strip) → `127.0.0.1:8120/api/auth/login` → FastAPI (`prefix=/api/auth`) handles it ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/_next/static/...` | Upstream → host nginx (preserve) → Next.js serves asset ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/manifest.webmanifest` | Generated by `app/manifest.ts`, `start_url` and `scope` already include the prefix ✓ |

#### 6.6 Local smoke test before involving upstream

Once the host nginx reload succeeds, prove the host-nginx → container path works without waiting on the upstream:

```bash
curl -H 'Host: www.gogoffcc.com' -H 'X-Forwarded-Proto: https' \
     http://127.0.0.1/gogoffcc-arms/api/health
# → {"status":"ok"}

curl -I -H 'Host: www.gogoffcc.com' -H 'X-Forwarded-Proto: https' \
     http://127.0.0.1/gogoffcc-arms/
# → HTTP/1.1 200 OK  (Next.js login or root page)
```

If both succeed, host nginx + containers are wired correctly. Only the upstream-colleague step (§6.2) remains before the public URL works.

> **WebAuthn note**: Because the upstream — not your server — owns the TLS termination for `www.gogoffcc.com`, you do not need your own cert. But the browser still records origin = `https://www.gogoffcc.com` for every registered credential. If the upstream's domain ever changes, all existing fingerprints become invalid and must be re-registered.

---

### Alternative self-hosted setups (Option A / Option B)

Skip this subsection unless you are deploying somewhere where you actually do own the domain and need to terminate TLS yourself. The production GoGoFresh deployment uses Option C above.

#### Option A — Caddy (zero-config TLS via Let's Encrypt)

Point `attendance.yourdomain.com` and `api.yourdomain.com` at your server, then create `/etc/caddy/Caddyfile`:

```caddy
attendance.yourdomain.com {
    reverse_proxy localhost:3000
}

api.yourdomain.com {
    reverse_proxy localhost:8000
}
```

Install Caddy (`sudo apt install caddy && sudo systemctl reload caddy`) — it auto-issues and renews TLS. Then publish container ports on localhost only by replacing the `expose:` blocks in `docker-compose.prod.yml` with `ports: ["127.0.0.1:8000:8000"]` and `ports: ["127.0.0.1:3000:3000"]`.

With Option A, you must also blank out `ROOT_PATH` / `NEXT_PUBLIC_BASE_PATH` (no sub-path) and set `WEBAUTHN_RP_ID=attendance.yourdomain.com`, `WEBAUTHN_ORIGIN=https://attendance.yourdomain.com`, `NEXT_PUBLIC_API_URL=https://api.yourdomain.com`.

#### Option B — Same-origin with nginx (single domain, API proxied through `/api`)

Serve everything from `attendance.yourdomain.com` and proxy `/api/` to the backend:

```nginx
server {
    listen 443 ssl http2;
    server_name attendance.yourdomain.com;
    ssl_certificate     /etc/letsencrypt/live/attendance.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/attendance.yourdomain.com/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

With Option B, set `NEXT_PUBLIC_API_URL=""` (empty string) so frontend fetches go to the same origin. Leave `ROOT_PATH` / `NEXT_PUBLIC_BASE_PATH` empty.

---

## 7. Smoke test

First, from the host running Docker (or any machine on the upstream's internal network), confirm the containers are answering directly:

```bash
# Backend health, hit through the docker-published port
curl http://<internal-ip>:8000/health
# → {"status":"ok"}

# Frontend renders (note the basePath in the URL)
curl -I http://<internal-ip>:3000/gogoffcc-arms
# → HTTP/1.1 200
```

If both succeed, the stack is healthy and any remaining issue is in the upstream proxy. Continue with the public-URL checks in §7.1 below.

### 7.1 Sub-path deployment smoke test (through the upstream)

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

The `attendance` database on the host Postgres is the only stateful piece for this app. Back it up directly from the host with `pg_dump` (no Docker involvement):

```bash
# /etc/cron.daily/attendance-backup
#!/bin/bash
set -e
BACKUP_DIR=/var/backups/attendance
mkdir -p "$BACKUP_DIR"
sudo -u postgres pg_dump attendance \
    | gzip > "$BACKUP_DIR/attendance-$(date +%F).sql.gz"
# retain 30 days
find "$BACKUP_DIR" -name '*.sql.gz' -mtime +30 -delete
```

> If you already have a cron job dumping the other apps' databases on this host (e.g. `pms_db`), just add `attendance` to its list instead of running a separate cron.

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
- [ ] The `attendance_user` DB password is strong and is the only place it's written down (not in git)
- [ ] `backend/.env`, `frontend/.env.production`, and root `.env` are all `chmod 600` and **not committed**
- [ ] `CORS_ORIGIN_REGEX` is unset in `backend/.env`
- [ ] `DATABASE_URL` uses `host.docker.internal:5432` and the backend container can actually connect (see the sanity-check in §4)
- [ ] Host Postgres `pg_hba.conf` grants `attendance_user` access from the Docker bridge (`172.17.0.0/16`)
- [ ] `ROOT_PATH=/gogoffcc-arms` (backend) and `NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms` (frontend) match the upstream sub-path
- [ ] `CORS_ORIGINS`, `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGIN` all point at the upstream host (`www.gogoffcc.com`), no path
- [ ] Upstream proxy operator has reloaded their Nginx with the `/gogoffcc-arms/api/` strip rule AND the `/gogoffcc-arms/` preserve rule (see §6)
- [ ] Container ports are published on the internal interface the upstream can reach — **not** `0.0.0.0`
- [ ] `https://www.gogoffcc.com/gogoffcc-arms/api/health` returns 200 (end-to-end through the upstream)
- [ ] Fingerprint register + login works end-to-end in a browser at the public URL
- [ ] Initial ADMIN password changed away from the bootstrap value
- [ ] Nightly `pg_dump` of `attendance` is installed and at least one backup has run successfully
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
| Postgres connection refused / "no pg_hba.conf entry" | Host Postgres doesn't accept the Docker bridge subnet, or only listens on `127.0.0.1` | Add `host all attendance_user 172.17.0.0/16 scram-sha-256` to `pg_hba.conf`, ensure `listen_addresses` in `postgresql.conf` includes `*` (or at least the docker bridge IP), then `sudo systemctl reload postgresql` |
| Taiwan calendar shows "not loaded" | CDN fetch blocked by firewall | Curl test from inside the backend container: `docker compose exec backend curl -I https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/2026.json` |
