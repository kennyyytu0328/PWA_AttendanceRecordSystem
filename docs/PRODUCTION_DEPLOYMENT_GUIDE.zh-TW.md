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
│ 我方伺服器（go2fresh-1，Ubuntu 18.04）                             │
│   ├─ host nginx :80                                                │
│   │     ├─ /gogoffcc-arms/api/  → 127.0.0.1:8120/api/  （剝離） │
│   │     └─ /gogoffcc-arms/      → 127.0.0.1:3000/      （剝離） │
│   └─ docker compose -f docker-compose.prod.yml                    │
│         ├─ frontend  (Next.js，127.0.0.1:3000，basePath=...)      │
│         ├─ backend   (FastAPI，127.0.0.1:8120 → uvicorn :8000)    │
│         └─ db        (Postgres 16 容器，僅 compose 內網可達 —     │
│                       port 5432 不對主機發布)                     │
└────────────────────────────────────────────────────────────────────┘
```

**本部署的關鍵事實：**

1. **TLS 由上游終結**，不在我方伺服器。容器內部僅使用純 HTTP。瀏覽器只看得到 `https://www.gogoffcc.com`，看不到我方 IP。
2. **我方不擁有公開網域。** WebAuthn `RP_ID` 為上游主機名稱 `www.gogoffcc.com`，並被釘入每個註冊過的指紋憑證。
3. **子路徑部署。** 應用程式網址為 `https://www.gogoffcc.com/gogoffcc-arms`。Next.js (`basePath`) 與 FastAPI (`root_path`) 皆以此前綴設定。
4. **上游 proxy 由同事管理。** 您需與 `www.gogoffcc.com` 的維運者協調，§6 附有對方需貼入的 Nginx 設定。我方 host nginx 的兩個 location block **都剝離** `/gogoffcc-arms` 前綴（見 §6.1 的 Next.js 16 說明）。
5. **3000 / 8120 連接埠僅綁定 `127.0.0.1`**，此主機不對公網開放任何連接埠。`db` 容器完全不發布 port。
6. **PostgreSQL 跑在容器內**（`docker-compose.prod.yml` 的 `db` 服務），不裝在主機上。正式伺服器為 Ubuntu 18.04，apt 只提供 PostgreSQL 10（低於需求的 14+）且該 OS 已 EOL，無法在主機安裝新版 — 改用 `postgres:16-alpine` 容器完全繞過主機 OS 限制；資料持久化於 `pgdata` Docker volume。

---

## 0. 前置需求

- 一台伺服器 / VM，已安裝 Docker ≥ 24 與 Docker Compose v2
- **不需要主機 PostgreSQL** — 資料庫由 `docker-compose.prod.yml` 的 `db` 服務（Postgres 16 容器）提供。這是刻意的設計：正式伺服器為 Ubuntu 18.04，apt 只有 PostgreSQL 10（低於需求的 14+）。若您想改用主機上既有的 Postgres 14+（與其他應用程式共用），請參閱 `docker-compose.prod.yml` 底部的「host Postgres alternative」註解區塊與 §2.5 末尾說明。
- 一個上游 reverse proxy 可連通的**內部 IP / 主機名稱**（例如私有 LAN 位址、VPC peer，或若上游與本機同一台則為 `127.0.0.1`）
- 與上游 proxy（`www.gogoffcc.com`）維運者協調 — 您會把一段 Nginx 設定交給對方（見 §6）
- 可執行 `openssl rand -hex 32`（用於產生密鑰）

> **您不需要：** 自己的公開網域、TLS 憑證、Caddy/certbot、對網際網路開放 80/443、DNS 記錄 — 這些全部由上游負責。

---

## 1. 將 repo clone 至伺服器

```bash
# clone 至部署使用者的家目錄（go2fresh-1 實際就放在這裡）。
# 家目錄本來就是你擁有的，不需要 sudo / chown。
git clone <your-repo-url> ~/gogofresh-attendance
cd ~/gogofresh-attendance
ls   # 應看到：backend/  docs/  docker-compose.prod.yml  frontend/  ...
```

> **路徑說明：** 本指南統一使用 `~/gogofresh-attendance`（在 `go2fresh-1` 上即 `/home/gogoffccict/gogofresh-attendance`）。若你的環境改 clone 到 `/opt/gogofresh-attendance` 之類的系統路徑，請將下文所有 `cd` 指令改成該路徑。

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

# 容器內 Postgres 的資料庫密碼
# （使用 -hex 而非 -base64：base64 含 '+' '/'，落到 DATABASE_URL 時需 URL encode。
#   hex 只有 [0-9a-f]，在 URL、shell、JSON 中都安全。）
openssl rand -hex 24
```

兩個數值都需妥善保存 — 第一個於 §3 貼入 `backend/.env` 的 `SECRET_KEY`；第二個要貼入**兩個地方**（根目錄 `.env` 的 `POSTGRES_PASSWORD`，以及 `backend/.env` 的 `DATABASE_URL` 內）。

## 2.5 資料庫佈建（自動 — 由 `db` 容器完成）

Postgres 以 `docker-compose.prod.yml` 的 `db` 服務（`postgres:16-alpine`）運行。**主機上不需安裝任何東西，也不需手動執行 SQL**：容器首次啟動時會讀取根目錄 `.env`（§3.3）的 `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`，自動建立 role 與 database。資料存於 `pgdata` named volume，容器重建與主機重開機後均保留。

兩件需要理解的事：

> **密碼只在首次啟動時設定。** `POSTGRES_*` 變數僅於 `pgdata` volume 為空時生效。之後修改 `.env` 的 `POSTGRES_PASSWORD` **不會**改變實際的資料庫密碼 — 需進容器執行 `ALTER USER`（`docker compose -f docker-compose.prod.yml exec db psql -U attendance_user -d attendance`）。

> **資料庫對外完全不可達。** `db` 服務不發布任何 port；只有 backend 容器能透過 compose 內網以主機名 `db` 連線。請保持如此。

> **替代方案 — 重用主機上的 Postgres 14+**（原 alg-compute-0 部署的作法，多應用共用一個 Postgres）：依 `docker-compose.prod.yml` 底部的「host Postgres alternative」註解區塊操作。簡述：移除 `db` 服務、backend 加回 `extra_hosts: host.docker.internal:host-gateway`、`DATABASE_URL` 指向 `host.docker.internal:5432`、手動建立 role + database（`CREATE USER attendance_user ...; CREATE DATABASE attendance OWNER attendance_user;`），並於 `pg_hba.conf` 開放 Docker bridge 網段（`host attendance attendance_user 172.16.0.0/12 scram-sha-256`）、`postgresql.conf` 設 `listen_addresses = 'localhost,172.17.0.1'`。絕不重用其他應用程式的 DB role。

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
| `DATABASE_URL` | `postgresql+asyncpg://attendance_user:<§2 產生的密碼>@db:5432/attendance` — `db` 為容器內 Postgres 的 compose 服務名稱。密碼**必須與**根目錄 `.env` 的 `POSTGRES_PASSWORD`（§3.3）完全一致。若改用主機 Postgres，主機名改為 `host.docker.internal`。 |
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

此為 repo 根目錄下的 `.env`，Docker Compose 會自動讀取以供 `docker-compose.prod.yml` 內的變數插值使用。內容包含 frontend build args **與**容器內 Postgres 的憑證：

```bash
cat > .env <<'EOF'
NEXT_PUBLIC_API_URL=/gogoffcc-arms
NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms
POSTGRES_USER=attendance_user
POSTGRES_PASSWORD=<§2 中 openssl rand -hex 24 的結果>
POSTGRES_DB=attendance
EOF

chmod 600 .env
```

> 此處的 `POSTGRES_PASSWORD` 與 `backend/.env` → `DATABASE_URL` 內的密碼是**同一個密鑰存在兩個檔案** — 必須完全一致，否則 backend 無法通過 `db` 容器的驗證。並請記得它只在 volume 首次啟動時生效（§2.5）。

---

## 4. 建置並啟動服務

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

首次建置約需 3–5 分鐘。確認所有服務均已啟動：

```bash
docker compose -f docker-compose.prod.yml ps
```

三個服務（`db`、`backend`、`frontend`）皆應顯示 `Up`，其中 `db` 應為 `Up (healthy)`。backend 會等待 db 的 healthcheck 通過後才啟動（`depends_on: condition: service_healthy`）。

確認 backend 能實際連到資料庫：

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -c "import asyncio, asyncpg, os; \
print(asyncio.run(asyncpg.connect(os.environ['DATABASE_URL'].replace('+asyncpg','')).fetch('select 1')))"
```

若出現 "password authentication failed"，表示 `backend/.env` → `DATABASE_URL` 的密碼與根目錄 `.env` 的 `POSTGRES_PASSWORD` 不一致（或 volume 首次初始化時用的是另一組密碼 — 見 §2.5）。

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

Compose 檔將後端與前端 port 僅綁定於 `127.0.0.1`。正式環境採**雙層 nginx**：上游 `www.gogoffcc.com`（TLS，由同事維運），以及我方正式伺服器 port 80 上的**主機 nginx**。主機 nginx 負責 `/gogoffcc-arms` 的路徑改寫並 proxy 至我方容器。若伺服器尚未安裝 nginx：`sudo apt install -y nginx`。

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

# 前端 — 同樣剝離 /gogoffcc-arms 前綴（見下方 Next.js 16 說明）
location /gogoffcc-arms/ {
    proxy_pass         http://127.0.0.1:3000/;        # 結尾斜線 → 剝離前綴
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

> **Next.js 16 basePath 注意 — 為何前端 block 也要剝離。** Next.js ≤15 中，`basePath` 會讓 server *要求*進來的請求帶前綴，所以 proxy 必須保留前綴。**Next.js 16 改變了這個行為**：`basePath` 只影響 bundle 內 URL / 資源的*產生*；server 仍以無前綴路徑提供路由（`/login`、`/dashboard`、`/_next/...`）。已實測驗證：`curl 127.0.0.1:3000/login` → 200，`curl 127.0.0.1:3000/gogoffcc-arms/login` → 404。因此主機 nginx 對前端也必須剝離前綴 — 兩個 location block 都使用結尾斜線的 `proxy_pass` 寫法。瀏覽器端的 URL 仍全部帶 `/gogoffcc-arms`，因為 `NEXT_PUBLIC_BASE_PATH` 已將前綴烘進產生的 HTML/JS。

> 後端為何使用主機 port **8120** 而非 8000：8000 是熱門預設值，原正式 VM 上已被其他應用佔用。`docker-compose.prod.yml` 將 uvicorn（容器內 port 8000）發布於主機 port **8120** 以避開此類衝突。容器內 port 不變。

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
| `https://www.gogoffcc.com/gogoffcc-arms/login` | 上游 → 主機 nginx `/gogoffcc-arms/`（剝離）→ `127.0.0.1:3000/login` → Next.js 回應 login 頁（HTML 內的 URL 經 `basePath` 帶前綴）✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/api/auth/login` | 上游 → 主機 nginx `/gogoffcc-arms/api/`（剝離）→ `127.0.0.1:8120/api/auth/login` → FastAPI（`prefix=/api/auth`）處理 ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/_next/static/...` | 上游 → 主機 nginx（剝離）→ `127.0.0.1:3000/_next/static/...` → Next.js 提供資源 ✓ |
| `https://www.gogoffcc.com/gogoffcc-arms/manifest.webmanifest` | 由 `app/manifest.ts` 動態產生，`start_url` 與 `scope` 已包含前綴 ✓ |

#### 6.6 主機端 smoke test（不需等上游）

主機 nginx reload 成功後，先在本機驗證 host nginx → 容器路徑正常，無須等上游維運：

```bash
# 後端路徑 — 預期 401（auth middleware 有作動 = 已連到 FastAPI；404 才代表接線有問題）
# 注意：沒有 /api/health 這條路由 — health handler 位於 bare app 的 /health
#（不在 /api prefix 下），因此無法透過 /api 剝離規則打到。
curl -i -H 'Host: www.gogoffcc.com' -H 'X-Forwarded-Proto: https' \
     http://127.0.0.1/gogoffcc-arms/api/auth/webauthn/status
# → HTTP/1.1 401 Unauthorized

curl -I -H 'Host: www.gogoffcc.com' -H 'X-Forwarded-Proto: https' \
     http://127.0.0.1/gogoffcc-arms/login
# → HTTP/1.1 200 OK  (Next.js 登入頁)
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

首先，於 Docker 主機本身（連接埠僅發布於 `127.0.0.1`，必須在伺服器上執行）確認容器可直接回應：

```bash
# 後端健康檢查（直連 docker 發布的連接埠：主機 8120 → 容器 8000）
curl http://127.0.0.1:8120/health
# → {"status":"ok"}

# 前端可正常渲染。Next.js 16 以「無前綴」路徑提供路由（basePath 只影響產生的
# URL）— 直連容器時測 /login，而非 /gogoffcc-arms/login。
curl -I http://127.0.0.1:3000/login
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
| 8 | 直接打 `https://<HOST><PREFIX>/api/auth/webauthn/status` | 回應 **401**（JSON 錯誤）。401 代表請求已抵達 FastAPI 的 auth middleware — `/api/` 剝離規則已生效；404 才代表路徑改寫有問題。（沒有 `/api/health` 路由 — health handler 位於 `/health`，不在 `/api` prefix 下。） |
| 9 | （行動裝置，選用）由該 URL 安裝 PWA | 「加入主畫面」成功；啟動後開啟於 `<PREFIX>/`，而非主機根目錄 |

**若步驟 5 或 6 出現 origin mismatch 錯誤**：上游未轉發 `X-Forwarded-Proto: https`，uvicorn 將請求視為 HTTP 而拒絕 WebAuthn。確認 uvicorn 已使用 `--proxy-headers --forwarded-allow-ips=*`（`docker-compose.prod.yml` 已預設），並請上游加上 `proxy_set_header X-Forwarded-Proto $scheme;`。

**若步驟 2 出現 `_next/static` 404**：主機 nginx 的 frontend `location` 區塊**沒有**剝離前綴 — Next.js 16 以無前綴路徑提供資源，該區塊必須加結尾斜線：`proxy_pass http://127.0.0.1:3000/;`。請參閱 §6.1 的 Next.js 16 說明。

**若步驟 8 回 404 但步驟 1 正常**：主機 nginx 的 `/gogoffcc-arms/api/` location 缺少結尾斜線的剝離 — 應為 `proxy_pass http://127.0.0.1:8120/api/;`（結尾斜線即剝離行為）。

---

## 8. 備份

`db` 容器內的 `attendance` database（`pgdata` Docker volume）是此應用程式唯一有狀態的部分。以**容器內**執行的 `pg_dump` 備份：

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
# 保留 30 天
find "$BACKUP_DIR" -name '*.sql.gz' -mtime +30 -delete
```

> `-T` 旗標很重要 — `exec` 預設會配置 TTY，從 cron 透過 pipe 輸出時會破壞二進位串流。不需密碼：`pg_dump` 在容器內以 postgres image 的本機信任環境執行。

```bash
sudo chmod +x /etc/cron.daily/attendance-backup
# 立即測試一次：
sudo /etc/cron.daily/attendance-backup && ls -la /var/backups/attendance/
```

還原到全新 volume：`gunzip -c attendance-<日期>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U attendance_user attendance`。

請定期測試還原 — 未經測試的備份不算是備份。另外請注意：備份的正確單位是 SQL dump，不是直接複製 `pgdata` volume 目錄（對運行中的 Postgres data dir 做檔案層級複製不具 crash-consistency）。

---

## 9. 升級

於 production 主機上執行：

```bash
cd ~/gogofresh-attendance
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

四步驟意義：

1. **`git pull`** — 拉取最新 code（你 push 到 GitHub / Bitbucket 之後）。
2. **`up -d --build`** — 重新 build frontend / backend image 並滾動重啟。
   - ⚠️ `NEXT_PUBLIC_API_URL` 與 `NEXT_PUBLIC_BASE_PATH` 是 **build time** 烘進前端 bundle，所以前端 env 一旦變更，務必加 `--build`。
3. **`alembic upgrade head`** — 套用新的 DB migration（若該版本無 schema 變更則為 no-op，但仍建議執行）。
4. （隱含步驟 0）**先備份 DB**：若該版本含 schema migration，先執行 `docker compose -f docker-compose.prod.yml exec -T db pg_dump -U attendance_user attendance > backup.sql` 再升級。（`up -d --build` 不會動到 `pgdata` volume，但 migration 會。）

### 加速小技巧

- 若只改 backend：`docker compose -f docker-compose.prod.yml up -d --build backend`
- 若只改 frontend：`docker compose -f docker-compose.prod.yml up -d --build frontend`
- 看 log 確認啟動成功：`docker compose -f docker-compose.prod.yml logs -f --tail 50`

### 回退

```bash
git checkout <previous-commit>
docker compose -f docker-compose.prod.yml up -d --build
```

Migration 是 forward-only — 若該版本含 schema 變更，回退前必須從備份還原 DB。

### 工作流提醒：雙 remote push

開發機上請同時 push 到 `origin`（GitHub）與 `bitbucket` 兩個 remote。Server 上 `git pull` 只會從預設 remote 拉取，所以只要兩邊 push 的是同一個 commit，就不會有不一致問題。

---

## 10. 上線前檢查清單

- [ ] `SECRET_KEY` 為 32+ bytes 隨機值，非預設的 `change-me-in-production`
- [ ] DB 密碼夠強，根目錄 `.env`（`POSTGRES_PASSWORD`）與 `backend/.env`（`DATABASE_URL`）完全一致，且未保存於其他任何地方（未進入 git）
- [ ] `backend/.env`、`frontend/.env.production`、根目錄 `.env` 均為 `chmod 600` 且**未被 commit**
- [ ] `backend/.env` 中的 `CORS_ORIGIN_REGEX` 已取消設定
- [ ] `DATABASE_URL` 使用 `db:5432`，且 backend 容器可實際連線（見 §4 健康檢查）
- [ ] `db` 服務**未發布任何 port**（`docker compose ps` 看不到 `5432` 對映）
- [ ] 後端 `ROOT_PATH=/gogoffcc-arms` 與前端 `NEXT_PUBLIC_BASE_PATH=/gogoffcc-arms` 與上游子路徑相符
- [ ] `CORS_ORIGINS`、`WEBAUTHN_RP_ID`、`WEBAUTHN_ORIGIN` 全部指向上游主機（`www.gogoffcc.com`），不含路徑
- [ ] 主機 nginx 已有**兩條剝離規則**（`/gogoffcc-arms/api/` → `:8120/api/` 與 `/gogoffcc-arms/` → `:3000/`，均帶結尾斜線），且上游維運者已加入 `/gogoffcc-arms/` 轉發規則（見 §6）
- [ ] 容器連接埠發布於上游可達的內部介面，**不是** `0.0.0.0`
- [ ] `https://www.gogoffcc.com/gogoffcc-arms/api/auth/webauthn/status` 透過上游端對端回應 401（404 = 路徑改寫有問題）
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
| backend 連不上 DB："password authentication failed" | `DATABASE_URL` 密碼 ≠ 根目錄 `.env` 的 `POSTGRES_PASSWORD`，或 `pgdata` volume 首次初始化時用的是舊密碼 | 讓兩個檔案一致；若 volume 已用其他密碼初始化，進容器 `docker compose exec db psql -U attendance_user attendance` 執行 `ALTER USER attendance_user WITH PASSWORD '...'`（或若 DB 尚為空，`docker compose down && docker volume rm <project>_pgdata` 重來） |
| backend 連不上 DB：對 `db:5432` "Connection refused" | `db` 容器尚未 healthy，或已被從 compose 檔移除 | `docker compose -f docker-compose.prod.yml ps` — `db` 須為 `Up (healthy)`；查 `docker compose logs db` |
| 台灣行事曆顯示「未載入」 | CDN 請求被防火牆阻擋 | 於後端容器內測試 curl：`docker compose exec backend curl -I https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/2026.json` |
