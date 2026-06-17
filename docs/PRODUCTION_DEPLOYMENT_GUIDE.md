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
│ Our server (go2fresh-1, Ubuntu 18.04)                             │
│   ├─ host nginx :80                                                │
│   │     ├─ /gogoffcc-arms/api/  → 127.0.0.1:8120/api/  (strip)    │
│   │     └─ /gogoffcc-arms/      → 127.0.0.1:3000/      (strip)    │
│   └─ docker compose -f docker-compose.prod.yml                    │
│         ├─ frontend  (Next.js, 127.0.0.1:3000, basePath=...)      │
│         ├─ backend   (FastAPI, 127.0.0.1:8120 → uvicorn :8000)    │
│         └─ db        (Postgres 16 container, compose-network      │
│                       only — port 5432 is NOT published)          │
└────────────────────────────────────────────────────────────────────┘
```

**Key facts about this setup:**

1. **TLS terminates upstream**, not on our server. Our containers speak plain HTTP on the internal network. The browser only ever sees `https://www.gogoffcc.com`, never our IP.
2. **We do not own the public domain.** WebAuthn `RP_ID` is `www.gogoffcc.com` (the upstream's host), pinned to every registered fingerprint.
3. **Sub-path deployment.** The app lives at `https://www.gogoffcc.com/gogoffcc-arms`. Both Next.js (`basePath`) and FastAPI (`root_path`) are configured for this prefix.
4. **Two nginx layers.** Upstream nginx (colleague) terminates TLS and forwards `/gogoffcc-arms/*` to our server's port 80. Our **host nginx** holds the location blocks that strip the `/gogoffcc-arms` prefix and proxy into the Docker containers on `127.0.0.1:8120` / `127.0.0.1:3000`. (Both blocks **strip** — see the Next.js 16 note in §6.1.)
5. **Coordination is minimal.** Upstream colleague just adds `/gogoffcc-arms/*` → `<our-server>:80`, mirroring the existing `/gogoffcc-pms/` rule. All the path-rewriting logic lives in our host nginx, where we own it.
6. **Container ports bind to `127.0.0.1` only**, never `0.0.0.0` — host nginx is the only thing that can reach them. The `db` container publishes no port at all.
7. **PostgreSQL runs in a container** (the `db` service in `docker-compose.prod.yml`), not on the host. The production server's Ubuntu 18.04 apt repos top out at PostgreSQL 10 — below the required 14+ — and the OS is EOL, so a host install is not an option. The bundled `postgres:16-alpine` container sidesteps the host OS entirely; data persists in the `pgdata` Docker volume.

---

## 0. Prerequisites

- A server / VM with Docker ≥ 24 and Docker Compose v2
- **No host PostgreSQL needed** — the database runs as the `db` container in `docker-compose.prod.yml` (Postgres 16). This is deliberate: the production server runs Ubuntu 18.04, whose apt repos only offer PostgreSQL 10 (< the required 14). If you instead want to reuse an existing host Postgres 14+ shared with other apps, see the "host Postgres alternative" comment block in `docker-compose.prod.yml` and the notes at the end of §2.5.
- An **internal IP / hostname** reachable from the upstream reverse proxy (e.g., a private LAN address, a VPC peer, or `127.0.0.1` if upstream runs on the same box)
- Coordination with whoever runs the upstream proxy (`www.gogoffcc.com`) — you'll hand them an Nginx snippet (see §6)
- Ability to run: `openssl rand -hex 32` (for generating secrets)

> **What you do NOT need:** your own public domain, a TLS certificate, Caddy/certbot, ports 80/443 open to the internet, or DNS records. The upstream owns all of that.

---

## 1. Clone the repo onto the server

```bash
# Cloned into the deploy user's home dir (this is where go2fresh-1 actually has it).
# No sudo/chown needed since you own your home directory.
git clone <your-repo-url> ~/gogofresh-attendance
cd ~/gogofresh-attendance
ls   # expect: backend/  docs/  docker-compose.prod.yml  frontend/  ...
```

> **Path note:** This guide uses `~/gogofresh-attendance` (e.g. `/home/gogoffccict/gogofresh-attendance` on `go2fresh-1`). If your site cloned into a system path like `/opt/gogofresh-attendance` instead, substitute that path in every `cd` below.

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

# Database password for the bundled Postgres container
# (-hex rather than -base64: base64 contains '+' and '/' which must be
#  URL-encoded when they land in DATABASE_URL. Hex is [0-9a-f] only — safe
#  in URLs, shell, JSON, everything.)
openssl rand -hex 24
```

Save both values somewhere secure — you'll paste the first into `backend/.env` (as `SECRET_KEY`) and the second into **two places** (root `.env` → `POSTGRES_PASSWORD` and `backend/.env` → inside `DATABASE_URL`) in §3.

## 2.5 Database provisioning (automatic — done by the `db` container)

Postgres runs as the `db` service in `docker-compose.prod.yml` (`postgres:16-alpine`). There is **nothing to install on the host and no SQL to run by hand**: on its very first start, the container reads `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` from the root `.env` (§3.3) and creates the role and database automatically. Data lives in the `pgdata` named Docker volume and survives container rebuilds and host reboots.

Two things to understand:

> **The password is set only on first start.** The `POSTGRES_*` variables are honored only while the `pgdata` volume is empty. Changing `POSTGRES_PASSWORD` in `.env` later does **not** change the actual database password — you'd have to `ALTER USER` inside the container (`docker compose -f docker-compose.prod.yml exec db psql -U attendance_user -d attendance`).

> **The database is not reachable from outside.** The `db` service publishes no ports; only the backend container can reach it over the compose network (as host `db`). Keep it that way.

> **Alternative — reuse a host Postgres 14+** (how the original alg-compute-0 deployment runs, sharing one Postgres across apps): follow the "host Postgres alternative" comment block in `docker-compose.prod.yml`. In short: drop the `db` service, give the backend `extra_hosts: host.docker.internal:host-gateway`, point `DATABASE_URL` at `host.docker.internal:5432`, create the role + database manually (`CREATE USER attendance_user ...; CREATE DATABASE attendance OWNER attendance_user;`), and open `pg_hba.conf` to the Docker bridge subnet (`host attendance attendance_user 172.16.0.0/12 scram-sha-256`) with `listen_addresses = 'localhost,172.17.0.1'`. Never reuse another app's DB role.

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
| `DATABASE_URL` | `postgresql+asyncpg://attendance_user:<password from §2>@db:5432/attendance` — `db` is the compose service name of the bundled Postgres container. The password **must be identical** to `POSTGRES_PASSWORD` in the root `.env` (§3.3). If you're reusing a host Postgres instead, use `host.docker.internal` as the host. |
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

This is the `.env` **at the repo root** that Docker Compose reads automatically for variable interpolation in `docker-compose.prod.yml`. It carries the frontend build args **and** the bundled-Postgres credentials:

```bash
cat > .env <<'EOF'
NEXT_PUBLIC_API_URL=/gogoffcc-arms
NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms
POSTGRES_USER=attendance_user
POSTGRES_PASSWORD=<the openssl rand -hex 24 value from §2>
POSTGRES_DB=attendance
EOF

chmod 600 .env
```

> `POSTGRES_PASSWORD` here and the password inside `backend/.env` → `DATABASE_URL` are the **same secret in two files** — they must match exactly, or the backend will fail to authenticate against the `db` container. Remember it's only applied on the volume's first start (§2.5).

---

## 4. Build and start the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes ~3–5 minutes. Verify everything is up:

```bash
docker compose -f docker-compose.prod.yml ps
```

All three services (`db`, `backend`, `frontend`) should show `Up` — `db` should show `Up (healthy)`. The backend deliberately waits for the db healthcheck before starting (`depends_on: condition: service_healthy`).

Sanity-check that the backend can actually reach the database:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -c "import asyncio, asyncpg, os; \
print(asyncio.run(asyncpg.connect(os.environ['DATABASE_URL'].replace('+asyncpg','')).fetch('select 1')))"
```

If this errors with "password authentication failed", the password in `backend/.env` → `DATABASE_URL` doesn't match `POSTGRES_PASSWORD` in the root `.env` (or the volume was first-initialized with a different password — see §2.5).

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

The compose file binds the backend and frontend ports to `127.0.0.1` only. In production we sit behind **two nginx layers**: the upstream `www.gogoffcc.com` (TLS, owned by a colleague), and our **host nginx** on the production server's port 80. The host nginx is the layer that does the `/gogoffcc-arms` path-rewriting and proxies into our containers. If nginx isn't installed on the server yet: `sudo apt install -y nginx`.

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

# Frontend — ALSO strip the /gogoffcc-arms prefix (see Next.js 16 note below)
location /gogoffcc-arms/ {
    proxy_pass         http://127.0.0.1:3000/;        # trailing slash strips the prefix
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

> **Next.js 16 basePath note — why the frontend block strips too.** In Next.js ≤15, `basePath` made the server *require* the prefix on incoming requests, so the proxy had to preserve it. **Next.js 16 changed this**: `basePath` only affects URL/asset *generation* in the bundle; the server still serves routes at unprefixed paths (`/login`, `/dashboard`, `/_next/...`). Verified empirically: `curl 127.0.0.1:3000/login` → 200, `curl 127.0.0.1:3000/gogoffcc-arms/login` → 404. So the host nginx must strip the prefix for the frontend as well — both location blocks use the trailing-slash `proxy_pass` form. The browser-side URLs still all carry `/gogoffcc-arms` because the prefix is baked into the generated HTML/JS by `NEXT_PUBLIC_BASE_PATH`.

> Why host port **8120** for backend, not 8000: 8000 is a popular default and was already taken on the original production VM by another app. `docker-compose.prod.yml` publishes uvicorn (container port 8000) on host port **8120** to avoid such collisions. The container-side port is unchanged.

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
| `https://www.gogoffcc.com/gogoffcc-arms/login` | Upstream → host nginx `/gogoffcc-arms/` (strip) → `127.0.0.1:3000/login` → Next.js serves login page (URLs in the HTML carry the prefix via `basePath`) ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/api/auth/login` | Upstream → host nginx `/gogoffcc-arms/api/` (strip) → `127.0.0.1:8120/api/auth/login` → FastAPI (`prefix=/api/auth`) handles it ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/_next/static/...` | Upstream → host nginx (strip) → `127.0.0.1:3000/_next/static/...` → Next.js serves asset ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/manifest.webmanifest` | Generated by `app/manifest.ts`, `start_url` and `scope` already include the prefix ✓ |

#### 6.6 Local smoke test before involving upstream

Once the host nginx reload succeeds, prove the host-nginx → container path works without waiting on the upstream:

```bash
# Backend path — expect 401 (auth middleware fired = FastAPI reached; 404 would mean broken wiring)
# Note: there is no /api/health route — the health handler lives at /health on the
# bare app (outside the /api prefix), so it is not reachable through the /api strip rule.
curl -i -H 'Host: www.gogoffcc.com' -H 'X-Forwarded-Proto: https' \
     http://127.0.0.1/gogoffcc-arms/api/auth/webauthn/status
# → HTTP/1.1 401 Unauthorized

curl -I -H 'Host: www.gogoffcc.com' -H 'X-Forwarded-Proto: https' \
     http://127.0.0.1/gogoffcc-arms/login
# → HTTP/1.1 200 OK  (Next.js login page)
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

First, from the host running Docker (the ports are published on `127.0.0.1` only, so these must run on the server itself), confirm the containers are answering directly:

```bash
# Backend health, hit through the docker-published port (host 8120 → container 8000)
curl http://127.0.0.1:8120/health
# → {"status":"ok"}

# Frontend renders. Next.js 16 serves routes UNPREFIXED (basePath only affects
# generated URLs) — so test /login, not /gogoffcc-arms/login, when hitting the
# container directly.
curl -I http://127.0.0.1:3000/login
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
| 8 | Hit `https://<HOST><PREFIX>/api/auth/webauthn/status` directly | Returns **401** (JSON error). 401 means the request reached FastAPI's auth middleware — the `/api/` strip rule is wired up. A 404 here means the path rewrite is broken. (There is no `/api/health` route — the health handler is at `/health`, outside the `/api` prefix.) |
| 9 | (Mobile, optional) Install the PWA from the URL | "Add to Home Screen" succeeds; launching the installed app opens at `<PREFIX>/`, not the host root. |

**If step 5 or 6 fails with an origin-mismatch error**, the upstream is not forwarding `X-Forwarded-Proto: https` — uvicorn is seeing the request as HTTP and rejecting WebAuthn. Confirm `--proxy-headers --forwarded-allow-ips=*` is on the uvicorn command (already set in `docker-compose.prod.yml`) and that the upstream's `proxy_set_header X-Forwarded-Proto $scheme;` line is present.

**If step 2 shows `_next/static` 404s**, the host nginx frontend `location` block is NOT stripping `<PREFIX>` — Next.js 16 serves assets at unprefixed paths, so the block needs the trailing slash: `proxy_pass http://127.0.0.1:3000/;`. See the Next.js 16 note in §6.1.

**If step 8 returns 404 but step 1 works**, the host nginx `/gogoffcc-arms/api/` location block is missing the trailing-slash strip — it must be `proxy_pass http://127.0.0.1:8120/api/;` (the trailing slash is what does the strip).

---

## 8. Backups

The `attendance` database inside the `db` container (the `pgdata` Docker volume) is the only stateful piece for this app. Back it up with `pg_dump` run **inside the container**:

```bash
# /etc/cron.daily/attendance-backup
#!/bin/bash
set -e
BACKUP_DIR=/var/backups/attendance
mkdir -p "$BACKUP_DIR"
cd ~/gogofresh-attendance
docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U attendance_user attendance \
    | gzip > "$BACKUP_DIR/attendance-$(date +%F).sql.gz"
# retain 30 days
find "$BACKUP_DIR" -name '*.sql.gz' -mtime +30 -delete
```

> The `-T` flag matters — `exec` allocates a TTY by default, which corrupts the binary stream when piped from cron. No password is needed: `pg_dump` runs inside the container as the `postgres` image's local trust context.

```bash
sudo chmod +x /etc/cron.daily/attendance-backup
# Test it once right away:
sudo /etc/cron.daily/attendance-backup && ls -la /var/backups/attendance/
```

To restore into a fresh volume: `gunzip -c attendance-<date>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U attendance_user attendance`.

Test restore periodically — a backup you haven't tested is not a backup. Note that backing up the SQL dump is the right unit, not the raw `pgdata` volume directory (a live file-level copy of a running Postgres data dir is not crash-consistent).

---

## 9. Upgrades

Run on the production host:

```bash
cd ~/gogofresh-attendance
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

What each step does:

1. **`git pull`** — fetch the latest code (after you've pushed to GitHub / Bitbucket).
2. **`up -d --build`** — rebuild the frontend / backend images and roll the containers.
   - ⚠️ `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_BASE_PATH` are baked into the frontend bundle at **build time**, so any frontend env change requires `--build`.
3. **`alembic upgrade head`** — apply new DB migrations (no-op when the release contains no schema changes, but always safe to run).
4. (Implicit step 0) **Back up the DB first** if the release contains a schema migration: `docker compose -f docker-compose.prod.yml exec -T db pg_dump -U attendance_user attendance > backup.sql` before upgrading. (`up -d --build` never touches the `pgdata` volume, but a migration can.)

### Speed tips

- Backend-only change: `docker compose -f docker-compose.prod.yml up -d --build backend`
- Frontend-only change: `docker compose -f docker-compose.prod.yml up -d --build frontend`
- Tail logs to confirm a clean start: `docker compose -f docker-compose.prod.yml logs -f --tail 50`

### Rollback

```bash
git checkout <previous-commit>
docker compose -f docker-compose.prod.yml up -d --build
```

Migrations are forward-only — if the release contains schema changes, restore the DB from backup before rolling back the code.

### Workflow reminder: dual-remote push

From your dev machine, push to **both** `origin` (GitHub) and `bitbucket`. The server's `git pull` only fetches from the default remote, so as long as both remotes receive the same commit you won't see drift between them.

---

## 10. Checklist before going live

- [ ] `SECRET_KEY` is 32+ random bytes, not the `change-me-in-production` default
- [ ] The DB password is strong, identical in root `.env` (`POSTGRES_PASSWORD`) and `backend/.env` (`DATABASE_URL`), and written down nowhere else (not in git)
- [ ] `backend/.env`, `frontend/.env.production`, and root `.env` are all `chmod 600` and **not committed**
- [ ] `CORS_ORIGIN_REGEX` is unset in `backend/.env`
- [ ] `DATABASE_URL` uses `db:5432` and the backend container can actually connect (see the sanity-check in §4)
- [ ] The `db` service publishes **no ports** (`docker compose ps` shows no `5432` mapping)
- [ ] `ROOT_PATH=/gogoffcc-arms` (backend) and `NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms` (frontend) match the upstream sub-path
- [ ] `CORS_ORIGINS`, `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGIN` all point at the upstream host (`www.gogoffcc.com`), no path
- [ ] Host nginx has BOTH strip rules (`/gogoffcc-arms/api/` → `:8120/api/` and `/gogoffcc-arms/` → `:3000/`, each with trailing slash) and the upstream operator has added the `/gogoffcc-arms/` forward rule (see §6)
- [ ] Container ports are published on the internal interface the upstream can reach — **not** `0.0.0.0`
- [ ] `https://www.gogoffcc.com/gogoffcc-arms/api/auth/webauthn/status` returns 401 (end-to-end through the upstream; 404 = broken path rewrite)
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
| Backend can't connect: "password authentication failed" | `DATABASE_URL` password ≠ `POSTGRES_PASSWORD` in root `.env`, or the `pgdata` volume was first-initialized with an older password | Make the two files match; if the volume already initialized with a different password, `ALTER USER attendance_user WITH PASSWORD '...'` inside `docker compose exec db psql -U attendance_user attendance` (or, if the DB is still empty, `docker compose down && docker volume rm <project>_pgdata` and start over) |
| Backend can't connect: "Connection refused" to `db:5432` | `db` container not healthy yet, or removed from the compose file | `docker compose -f docker-compose.prod.yml ps` — `db` must be `Up (healthy)`; check `docker compose logs db` |
| Taiwan calendar shows "not loaded" | CDN fetch blocked by firewall | Curl test from inside the backend container: `docker compose exec backend curl -I https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/2026.json` |
