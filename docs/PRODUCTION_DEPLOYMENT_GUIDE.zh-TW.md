# 正式環境部署指南

GoGoFresh 差勤系統 — 部署至正式環境的逐步指南。

> 本指南假設您已能在本機成功執行應用程式（使用 `docker-compose.yml` 執行 `docker compose up -d`）。若尚未完成，請先從本機環境開始。

## 部署拓樸（實際部署架構）

```
┌─ 瀏覽器 ──────────────────────────────────────────────────────────┐
│ HTTPS                                                              │
│   ↓                                                                │
│ www.gogoffcc.com  （上游 nginx，由同事維運，TLS 在此終結）        │
│   ↓ HTTP，/gogoffcc-arms/*  →  <我方伺服器內部 IP>:80              │
│   ↓                                                                │
│ 我方伺服器（alg-compute-0，10.140.0.4）                            │
│   ├─ host nginx :80  （已為 /gogoffcc-pms/ 等多個應用程式服務）   │
│   │     ├─ /gogoffcc-arms/api/  → 127.0.0.1:8120/api/  （剝離） │
│   │     └─ /gogoffcc-arms/      → 127.0.0.1:3000       （保留） │
│   ├─ docker compose -f docker-compose.prod.yml                    │
│   │     ├─ frontend  (Next.js，127.0.0.1:3000，basePath=...)      │
│   │     └─ backend   (FastAPI，127.0.0.1:8120 → uvicorn :8000)    │
│   └─ Postgres 14+    (主機服務，port 5432，與本機其他應用程式共用 │
│                       — 不在 Docker 內)                           │
└────────────────────────────────────────────────────────────────────┘
```

**本部署的關鍵事實：**

1. **TLS 由上游終結**，不在我方伺服器。容器內部僅使用純 HTTP。瀏覽器只看得到 `https://www.gogoffcc.com`，看不到我方 IP。
2. **我方不擁有公開網域。** WebAuthn `RP_ID` 為上游主機名稱 `www.gogoffcc.com`，並被釘入每個註冊過的指紋憑證。
3. **子路徑部署。** 應用程式網址為 `https://www.gogoffcc.com/gogoffcc-arms`。Next.js (`basePath`) 與 FastAPI (`root_path`) 皆以此前綴設定。
4. **上游 proxy 由同事管理。** 您需與 `www.gogoffcc.com` 的維運者協調，§6 附有對方需貼入的 Nginx 設定。
5. **3000 / 8000 連接埠僅暴露於上游可達的內部介面**，此主機不對公網開放任何連接埠。

---

## 0. 前置需求

- 一台伺服器 / VM，已安裝 Docker ≥ 24 與 Docker Compose v2
- **主機上已運行 PostgreSQL 14+**（正式環境的 GoGoFresh 主機與其他應用程式共用同一個 Postgres 實例 — 詳見 §2.5）。若您寧可在容器內跑 Postgres，請參閱 `docker-compose.prod.yml` 中的「bundled Postgres」註解區塊。
- 一個上游 reverse proxy 可連通的**內部 IP / 主機名稱**（例如私有 LAN 位址、VPC peer，或若上游與本機同一台則為 `127.0.0.1`）
- 與上游 proxy（`www.gogoffcc.com`）維運者協調 — 您會把一段 Nginx 設定交給對方（見 §6）
- 可執行 `openssl rand -hex 32`（用於產生密鑰）

> **您不需要：** 自己的公開網域、TLS 憑證、Caddy/certbot、對網際網路開放 80/443、DNS 記錄 — 這些全部由上游負責。

---

## 1. 將 repo clone 至伺服器

```bash
sudo git clone <your-repo-url> /opt/gogofresh-attendance
sudo chown -R $USER:$USER /opt/gogofresh-attendance   # 後續 git pull / 編輯不需 sudo
cd /opt/gogofresh-attendance
ls   # 應看到：backend/  docs/  docker-compose.prod.yml  frontend/  ...
```

### 1.1 Bitbucket / GitHub clone 驗證方式

Bitbucket 與 GitHub 皆已停止支援 git over HTTPS 的帳號密碼登入。請擇一使用：

**Bitbucket — API token**（Atlassian 已於 2025-09-09 棄用 App Passwords，改用 API token）：
- 於 Atlassian 帳號設定 → Security → **API tokens** 產生 token，scope 設為 `Bitbucket: repositories: read`
- `git clone` 提示時：
  - **Username**：Atlassian 帳號的 email（例如 `kennyyytu0328@gmail.com`）
  - **Password**：貼上 API token

**GitHub — Personal Access Token (fine-grained)**：
- GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens**，授予該 repo `Contents: Read-only`
- `git clone` 提示時：
  - **Username**：GitHub 使用者名稱
  - **Password**：貼上 PAT

**兩種平台皆適用 — SSH deploy key**（長期最乾淨，無到期、無 token 輪替）：
- `ssh-keygen -t ed25519 -C "<server-name> deploy" -f ~/.ssh/<remote>_deploy`（不設密碼，方便無人值守 pull）
- 將 `~/.ssh/<remote>_deploy.pub` 貼到該 repo 的 **Access keys**（Bitbucket）或 **Deploy keys**（GitHub），唯讀
- 加入 `~/.ssh/config`：
  ```
  Host bitbucket.org    # 或 github.com
      User git
      IdentityFile ~/.ssh/<remote>_deploy
      IdentitiesOnly yes
  ```
- 改用 SSH URL clone：`git clone git@bitbucket.org:<workspace>/<repo>.git ...`

**可選**：若希望日後 `git pull` 不再重複貼 token：
```bash
git config --global credential.helper store
git pull   # 貼一次，之後存於 ~/.git-credentials（明文）
```
僅在僅您能 shell 進入的伺服器上使用 `store`。

---

## 2. 產生密鑰

於伺服器上執行下列指令（或將結果安全地複製過去）：

```bash
# JWT 簽章金鑰（務必保密 — 外洩等同於驗證被繞過）
openssl rand -hex 32
```

將該數值妥善保存 — §3 會貼入 `backend/.env` 的 `SECRET_KEY` 欄位。

## 2.5 建立應用程式的資料庫角色與 database

我們**不在** Docker 內跑 Postgres，而是重用主機上既有的 Postgres。因此需在 Docker **外**，僅一次性地建立專屬 role 與 database。

以 `postgres` 超級使用者連線（透過本機 Unix socket 的 peer 驗證，不需密碼）：

```bash
sudo -u postgres psql
```

於 `postgres=#` 提示字元輸入（先在另一個 shell 跑 `openssl rand -hex 24` 取得強密碼 — 使用 `-hex` 而非 `-base64`，可避免 `+` `/` 等字元落到 `DATABASE_URL` 時需 URL encode 的麻煩）：

```sql
CREATE USER attendance_user WITH PASSWORD '<貼上強密碼>';
CREATE DATABASE attendance OWNER attendance_user;
GRANT ALL PRIVILEGES ON DATABASE attendance TO attendance_user;
\q
```

保存該密碼 — §3 會貼入 `backend/.env` 的 `DATABASE_URL`。

> **為何要建立新 role**：絕不重用其他應用程式的 DB user。每個應用程式擁有專屬 role + 專屬 database — 如此某一個應用的憑證外洩或錯誤 migration 不會影響到其他應用。

> **若主機 Postgres 僅允許從 `127.0.0.1` 連線**（Ubuntu 預設）：backend 容器需透過 `host.docker.internal` 連線，`docker-compose.prod.yml` 已透過 `extra_hosts: host-gateway` 設定好。另外請確認 `pg_hba.conf` 允許 `host all attendance_user 172.17.0.0/16 scram-sha-256`（或 `md5`，docker bridge 網段）。修改 `pg_hba.conf` 後執行 `sudo systemctl reload postgresql`。

---

## 3. 填入環境變數範本

repo 中附有**三個**範本檔。請先複製，再於複本中填入實際值。

### 3.1 後端 env

```bash
cp backend/.env.production.example backend/.env
```

接著編輯 `backend/.env`：

| 變數 | 設定值 |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://attendance_user:<§2.5 設的密碼>@host.docker.internal:5432/attendance` — `host.docker.internal` 讓容器連到 Docker 主機上的 Postgres。若您改用容器內 Postgres，請改為 `db`（compose 服務名稱）。 |
| `SECRET_KEY` | 貼上 §2 中 `openssl rand -hex 32` 的結果 |
| `ALGORITHM` | `HS256`（除非您明確知道原因，否則不要更動） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 預設 `30`；可調高以延長登入時效，調低以提升安全性 |
| `CORS_ORIGINS` | `["https://www.gogoffcc.com"]` — 精確上游來源，結尾不可加斜線或路徑 |
| `CORS_ORIGIN_REGEX` | 保持**未設定 / 註解狀態**。此正規式僅用於 LAN 開發 |
| `WEBAUTHN_RP_ID` | `www.gogoffcc.com` — 上游的**純主機名稱**，不含協定、連接埠或路徑 |
| `WEBAUTHN_RP_NAME` | 生物辨識提示顯示的任意名稱（例如 `GoGoFresh Attendance`） |
| `WEBAUTHN_ORIGIN` | `https://www.gogoffcc.com` — 完整上游來源，必須為 HTTPS，不含路徑 |
| `ROOT_PATH` | `/gogoffcc-arms` — 上游轉發至我方的子路徑，必須與 `NEXT_PUBLIC_BASE_PATH` 相同 |

> **WebAuthn 注意事項**：`WEBAUTHN_RP_ID` 與 `WEBAUTHN_ORIGIN` 會被釘入每個已註冊的驗證器。若使用者註冊指紋後才變更任一項，則所有已註冊的憑證皆會失效，必須重新註冊。

### 3.2 前端 env

```bash
cp frontend/.env.production.example frontend/.env.production
```

編輯 `frontend/.env.production`：

| 變數 | 值 |
|---|---|
| `NEXT_PUBLIC_API_URL` | `/gogoffcc-arms` — API client 會在後面附加 `/api/...`，因此這裡只填上游前綴。（其他同源或獨立 API 主機部署請參閱 §6） |
| `NEXT_PUBLIC_BASE_PATH` | `/gogoffcc-arms` — 必須與後端 `ROOT_PATH` 一致 |

> **重要**：`NEXT_PUBLIC_*` 於**建置時被編譯進 JS bundle**，而非執行時讀取。若要變更此值，必須重新建置前端容器。

### 3.3 Compose 層級 env

此為 repo 根目錄下的 `.env`，Docker Compose 會自動讀取以供 `docker-compose.prod.yml` 內的變數插值使用：

採用主機 Postgres 後，此處僅需 frontend build args：

```bash
cat > .env <<'EOF'
NEXT_PUBLIC_API_URL=/gogoffcc-arms
NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms
EOF

chmod 600 .env
```

> 不再需要 `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` — compose 檔內已無 `db` 服務。DB 密碼僅保存於 `backend/.env` 的 `DATABASE_URL` 中。若您改用容器內 Postgres（compose 檔內已註解的選項），再加回此處。

---

## 4. 建置並啟動服務

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

首次建置約需 3–5 分鐘。確認所有服務均已啟動：

```bash
docker compose -f docker-compose.prod.yml ps
```

兩個服務（`backend`、`frontend`）皆應顯示 `Up`。（沒有 `db` 容器 — 主機 Postgres 在 Compose 之外運行。）

確認 backend 能實際連到主機 Postgres：

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -c "import asyncio, asyncpg, os; \
print(asyncio.run(asyncpg.connect(os.environ['DATABASE_URL'].replace('+asyncpg','')).fetch('select 1')))"
```

若出現 "connection refused" 或 "no pg_hba.conf entry" 錯誤，請回到 §2.5 — 主機 Postgres 未接受 Docker bridge 的連線。

---

## 5. 執行資料庫 migration

Compose 檔**不會**在啟動時自動 migrate（以避免 rollback 時發生意外）。首次部署後及每次程式碼更新後都需手動執行：

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

預期輸出結尾為 `INFO  [alembic.runtime.migration] Running upgrade ... -> c3d4e5f6a7b8, add_absent_status`。

### 5.1 建立初始 ADMIN 使用者

開發用的 `seed.py` 會建立五位測試帳號並使用弱密碼 — **切勿於正式環境執行**。請改為直接建立一位真實的 ADMIN 使用者：

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

以此 ADMIN 登入後，請透過管理員面板建立 HR 與其他使用者 — 切勿透過 SQL 直接建立非 ADMIN 使用者。

### 5.2 設定初始系統配置

以 ADMIN 登入後，透過管理員面板設定：

- **辦公室位置**（經緯度 — 用於 2 公里 WFH / OFFICE 地理圍欄）
- **部門清單**（建立員工時的下拉選單預設值）
- **彈性打卡分鐘數**（預設 5 分鐘）
- **工作日行事曆** — 點擊「更新全年行事曆」以從 CDN 取得台灣行事曆

---

## 6. 反向代理與 TLS

Compose 檔將後端與前端 port 僅綁定於 `127.0.0.1`。正式環境採**雙層 nginx**：上游 `www.gogoffcc.com`（TLS，由同事維運），以及我方位於 `alg-compute-0:80` 的**主機 nginx**（已為 `/gogoffcc-pms/` 等多個應用程式服務）。主機 nginx 負責 `/gogoffcc-arms` 的路徑改寫並 proxy 至我方容器。

若您讀到這裡而**實際上擁有公開網域**（本專案少見），可參考本節最後的「自架 TLS 替代方案」（選項 A / 選項 B）。

### 選項 C — 位於上游 reverse proxy 的子路徑後（正式環境預設）

#### 6.1 主機 nginx（我方伺服器）— 新增 location block

於 `/etc/nginx/sites-enabled/default` 既有 `server { ... }` 區塊內（與既有 `/gogoffcc-pms/` 區塊並列）新增：

```nginx
# === GGFF Attendance — 於 /gogoffcc-arms/ 服務 ===

# 後端 API — 剝離 /gogoffcc-arms 前綴，使 FastAPI 看到 /api/...
location /gogoffcc-arms/api/ {
    proxy_pass         http://127.0.0.1:8120/api/;    # 結尾斜線 → 剝離前綴
    proxy_http_version 1.1;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto https;       # 上游已終結 TLS
    proxy_set_header   X-Forwarded-Host  $host;
    proxy_read_timeout 60s;
}

# 前端 — 保留 /gogoffcc-arms 前綴，使 Next.js basePath 匹配
location /gogoffcc-arms/ {
    proxy_pass         http://127.0.0.1:3000;         # 無結尾斜線 → 保留前綴
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

驗證並重載：
```bash
sudo nginx -t
sudo systemctl reload nginx
```

> 後端為何使用主機 port **8120** 而非 8000：`alg-compute-0` 上 port 8000 已被 `barcode_identify` 佔用。`docker-compose.prod.yml` 將 uvicorn（容器內 port 8000）發布於主機 port **8120** 以避開衝突。容器內 port 不變。

#### 6.2 上游 proxy（同事的）— 一條新轉發規則

請上游維運者新增與既有 `/gogoffcc-pms/` 並列的 `/gogoffcc-arms/` location block — 目標相同（`<我方伺服器 IP>:80`）、TLS 與 `X-Forwarded-*` 標頭相同。所有路徑改寫由我方主機 nginx 內部處理，上游無需再做剝離 / 保留分離。

#### 6.3 容器 port

`docker-compose.prod.yml` 已配置好此拓樸：

```yaml
  backend:
    ports:
      - "127.0.0.1:8120:8000"   # 主機:8120 → 容器:8000 (uvicorn)
  frontend:
    ports:
      - "127.0.0.1:3000:3000"
```

綁定 `127.0.0.1` 表示僅主機上的程序（即主機 nginx）可連線，公網或 LAN 均無法存取。

`docker-compose.prod.yml` 已在 uvicorn 啟動時加上 `--proxy-headers --forwarded-allow-ips=*`，這是讓 FastAPI 信任主機 nginx 送來的 `X-Forwarded-Proto: https` 的必要設定。若缺少此項，WebAuthn 會將 origin 視為 `http://` 並拒絕所有指紋登入。

#### 6.4 Env 值

§3 已涵蓋，此處供快速對照：

`backend/.env`：
```
ROOT_PATH=/gogoffcc-arms
WEBAUTHN_RP_ID=www.gogoffcc.com              # 純主機 — 不含路徑
WEBAUTHN_ORIGIN=https://www.gogoffcc.com     # 來源 — 不含路徑
CORS_ORIGINS=["https://www.gogoffcc.com"]
```

`frontend/.env.production` 與根目錄 `.env`：
```
NEXT_PUBLIC_API_URL=/gogoffcc-arms
NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms
```

#### 6.5 路徑檢查表

主機 nginx reload 完成、上游同事加上轉發規則之後：

| 瀏覽器請求 URL | 各 hop 看到的內容 |
|---|---|
| `https://www.gogoffcc.com/gogoffcc-arms/login` | 上游 → 主機 nginx `/gogoffcc-arms/` → `127.0.0.1:3000/gogoffcc-arms/login` → Next.js（`basePath=/gogoffcc-arms`）回應 login 頁 ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/api/auth/login` | 上游 → 主機 nginx `/gogoffcc-arms/api/`（剝離）→ `127.0.0.1:8120/api/auth/login` → FastAPI（`prefix=/api/auth`）處理 ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/_next/static/...` | 上游 → 主機 nginx（保留）→ Next.js 提供資源 ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/manifest.webmanifest` | 由 `app/manifest.ts` 動態產生，`start_url` 與 `scope` 已包含前綴 ✓ |

#### 6.6 主機端 smoke test（不需等上游）

主機 nginx reload 成功後，先在本機驗證 host nginx → 容器路徑正常，無須等上游維運：

```bash
curl -H 'Host: www.gogoffcc.com' -H 'X-Forwarded-Proto: https' \
     http://127.0.0.1/gogoffcc-arms/api/health
# → {"status":"ok"}

curl -I -H 'Host: www.gogoffcc.com' -H 'X-Forwarded-Proto: https' \
     http://127.0.0.1/gogoffcc-arms/
# → HTTP/1.1 200 OK  (Next.js 登入頁或首頁)
```

兩者皆成功表示主機 nginx + 容器接得起來，只剩 §6.2 的上游同事步驟。

> **WebAuthn 注意**：由於 TLS 是由上游（非我方）終結 `www.gogoffcc.com`，您無需自備憑證。但瀏覽器仍會將每個已註冊憑證的 origin 記為 `https://www.gogoffcc.com`。若上游網域日後變更，所有現有指紋皆會失效，必須重新註冊。

---

### 自架 TLS 替代方案（選項 A / 選項 B）

除非您部署於自己擁有網域且需自行終結 TLS 的環境，否則可略過本小節。本專案的正式環境採用上方選項 C。

#### 選項 A — Caddy（自動透過 Let's Encrypt 取得 TLS，零設定）

將 `attendance.yourdomain.com` 與 `api.yourdomain.com` 指向您的伺服器，建立 `/etc/caddy/Caddyfile`：

```caddy
attendance.yourdomain.com {
    reverse_proxy localhost:3000
}
api.yourdomain.com {
    reverse_proxy localhost:8000
}
```

安裝 Caddy（`sudo apt install caddy && sudo systemctl reload caddy`） — 會自動簽發並續發 TLS 憑證。於 `docker-compose.prod.yml` 將 `expose:` 改為 `ports: ["127.0.0.1:8000:8000"]` 與 `ports: ["127.0.0.1:3000:3000"]`。

選項 A 必須將 `ROOT_PATH` / `NEXT_PUBLIC_BASE_PATH` 留空（無子路徑），並改為 `WEBAUTHN_RP_ID=attendance.yourdomain.com`、`WEBAUTHN_ORIGIN=https://attendance.yourdomain.com`、`NEXT_PUBLIC_API_URL=https://api.yourdomain.com`。

#### 選項 B — 使用 nginx 達成同源（單一網域，透過 `/api` 代理 API）

由 `attendance.yourdomain.com` 統一服務，前端 / API 同源：

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

選項 B 須將 `NEXT_PUBLIC_API_URL=""`（空字串），並讓 `ROOT_PATH` / `NEXT_PUBLIC_BASE_PATH` 留空。

---

## 7. 煙霧測試（Smoke Test）

首先，於 Docker 主機本身（或上游內網中任一機器）確認容器可直接回應：

```bash
# 後端健康檢查（直連 docker 發布的連接埠）
curl http://<internal-ip>:8000/health
# → {"status":"ok"}

# 前端可正常渲染（注意 URL 包含 basePath）
curl -I http://<internal-ip>:3000/gogoffcc-arms
# → HTTP/1.1 200
```

若兩者皆成功，表示堆疊本身健康，任何剩下的問題都在上游 proxy。請繼續執行 §7.1 公開 URL 檢查。

### 7.1 子路徑部署煙霧測試（透過上游）

在上游維運者重載 proxy 後執行一次。將 `<HOST>`（`www.gogoffcc.com`）與 `<PREFIX>`（`/gogoffcc-arms`）替換為您的實際值。

| # | 步驟 | 通過標準 |
|---|------|----------|
| 1 | 瀏覽 `https://<HOST><PREFIX>/login` | 登入頁正常顯示，無 404，網址列仍包含前綴 |
| 2 | DevTools → Network 重新載入頁面 | 所有 `_next/static/*` 請求路徑均位於 `<PREFIX>/_next/...` 並回 200，無任何請求打到根目錄 `/_next/...` |
| 3 | 以 `ADMIN` 帳密送出登入表單 | 單次 POST 至 `<PREFIX>/api/auth/login` 回 200 並含 JWT，無 404、無 CORS 錯誤 |
| 4 | DevTools → Application → Manifest | `start_url` 與 `scope` 均等於 `<PREFIX>/`，icons 解析於 `<PREFIX>/icons/...` |
| 5 | 註冊指紋（管理員面板 → 啟用 WebAuthn） | 生物辨識提示顯示 RP 名稱，console 無 origin / RP ID 不符錯誤 |
| 6 | 登出後以指紋登入 | 驗證成功，發出 JWT，導向儀表板 `<PREFIX>/dashboard` |
| 7 | 瀏覽 `https://<HOST><PREFIX>/docs` | FastAPI Swagger UI 正常載入，所有端點顯示於 `<PREFIX>` 之下（`ROOT_PATH` 已設） |
| 8 | 直接打 `https://<HOST><PREFIX>/api/health` | 回應 `{"status":"ok"}` — 確認上游 `/api/` 剝離規則已生效 |
| 9 | （行動裝置，選用）由該 URL 安裝 PWA | 「加入主畫面」成功；啟動後開啟於 `<PREFIX>/`，而非主機根目錄 |

**若步驟 5 或 6 出現 origin mismatch 錯誤**：上游未轉發 `X-Forwarded-Proto: https`，uvicorn 將請求視為 HTTP 而拒絕 WebAuthn。確認 uvicorn 已使用 `--proxy-headers --forwarded-allow-ips=*`（`docker-compose.prod.yml` 已預設），並請上游加上 `proxy_set_header X-Forwarded-Proto $scheme;`。

**若步驟 2 出現 `_next/static` 404**：上游 frontend `location` 區塊將前綴剝離了 — 應保留（`proxy_pass` 結尾**不**加斜線）。請參閱 §6 選項 C。

**若步驟 8 回 404 但步驟 1 正常**：上游 `/api/` location 缺少結尾斜線的剝離 — 應為 `proxy_pass http://your-server:8000/api/;`（結尾斜線即剝離行為）。

---

## 8. 備份

主機 Postgres 中的 `attendance` database 是此應用程式唯一有狀態的部分。直接在主機上以 `pg_dump` 備份（不經 Docker）：

```bash
# /etc/cron.daily/attendance-backup
#!/bin/bash
set -e
BACKUP_DIR=/var/backups/attendance
mkdir -p "$BACKUP_DIR"
sudo -u postgres pg_dump attendance \
    | gzip > "$BACKUP_DIR/attendance-$(date +%F).sql.gz"
# 保留 30 天
find "$BACKUP_DIR" -name '*.sql.gz' -mtime +30 -delete
```

> 若主機上已有其他應用程式的備份 cron（例如 `pms_db`），直接在該腳本內加上 `attendance` 即可，無需另設 cron。

```bash
sudo chmod +x /etc/cron.daily/attendance-backup
```

請定期測試還原 — 未經測試的備份不算是備份。

---

## 9. 升級

```bash
cd /opt/gogofresh-attendance
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

回退：執行 `git checkout <previous-commit>` 後重複上述步驟。Migration 一般僅向前（forward-only） — 任何包含 schema 變更的版本發布前，務必先做好資料庫備份。

---

## 10. 上線前檢查清單

- [ ] `SECRET_KEY` 為 32+ bytes 隨機值，非預設的 `change-me-in-production`
- [ ] `attendance_user` 的 DB 密碼夠強，且僅保存於一處（未進入 git）
- [ ] `backend/.env`、`frontend/.env.production`、根目錄 `.env` 均為 `chmod 600` 且**未被 commit**
- [ ] `backend/.env` 中的 `CORS_ORIGIN_REGEX` 已取消設定
- [ ] `DATABASE_URL` 使用 `host.docker.internal:5432`，且 backend 容器可實際連線（見 §4 健康檢查）
- [ ] 主機 Postgres `pg_hba.conf` 已允許 `attendance_user` 從 Docker bridge（`172.17.0.0/16`）連線
- [ ] 後端 `ROOT_PATH=/gogoffcc-arms` 與前端 `NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms` 與上游子路徑相符
- [ ] `CORS_ORIGINS`、`WEBAUTHN_RP_ID`、`WEBAUTHN_ORIGIN` 全部指向上游主機（`www.gogoffcc.com`），不含路徑
- [ ] 上游 proxy 維運者已重載 Nginx，並已加入 `/gogoffcc-arms/api/` 剝離規則與 `/gogoffcc-arms/` 保留規則（見 §6）
- [ ] 容器連接埠發布於上游可達的內部介面，**不是** `0.0.0.0`
- [ ] `https://www.gogoffcc.com/gogoffcc-arms/api/health` 透過上游端對端回應 200
- [ ] 於瀏覽器中經由公開 URL 指紋註冊 + 登入可端對端成功
- [ ] 初始 ADMIN 密碼已更換，不再是 bootstrap 值
- [ ] 每日 `pg_dump attendance` cron 已安裝，且至少已有一次備份成功執行
- [ ] 重開機後 `docker compose ps` 顯示所有服務健康（範本已包含 `restart: unless-stopped`）

---

## 11. 疑難排解

| 現象 | 可能原因 | 修正方式 |
|---|---|---|
| 登入失敗且瀏覽器主控台出現 `ERR_FAILED` | `NEXT_PUBLIC_API_URL` 錯誤 | 檢查值並重建前端（`docker compose -f docker-compose.prod.yml up -d --build frontend`） |
| 登入 preflight 回傳 400 | 來源不在 `CORS_ORIGINS` 中 | 將精確來源加入 `backend/.env`，重啟後端 |
| 指紋提示從未出現 | 非 HTTPS，或 `WEBAUTHN_RP_ID` 不相符 | 確認 HTTPS 正常運作；`RP_ID` 必須是來源的純主機名稱 |
| 密碼正確仍顯示「Invalid credentials」 | DB 尚未 migrate（缺少 hashed_password 欄位），或重啟後 SECRET_KEY 不一致 | 執行 `alembic upgrade head`；確保 `SECRET_KEY` 在部署間維持穩定 |
| 僅某端點出現 CORS 錯誤 | 該端點在 CORS 標頭加入前已回 500 | 檢查後端 log：`docker compose -f docker-compose.prod.yml logs backend --tail 100` |
| Postgres 連線被拒 / "no pg_hba.conf entry" | 主機 Postgres 不接受 Docker bridge 網段，或僅監聽 `127.0.0.1` | 於 `pg_hba.conf` 加入 `host all attendance_user 172.17.0.0/16 scram-sha-256`，並確認 `postgresql.conf` 的 `listen_addresses` 包含 `*`（或至少 docker bridge IP），再執行 `sudo systemctl reload postgresql` |
| 台灣行事曆顯示「未載入」 | CDN 請求被防火牆阻擋 | 於後端容器內測試 curl：`docker compose exec backend curl -I https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/2026.json` |
