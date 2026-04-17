# 正式環境部署指南

GoGoFresh 差勤系統 — 部署至正式環境的逐步指南。

> 本指南假設您已能在本機成功執行應用程式（使用 `docker-compose.yml` 執行 `docker compose up -d`）。若尚未完成，請先從本機環境開始。

---

## 0. 前置需求

- 一台伺服器 / VM，已安裝 Docker ≥ 24 與 Docker Compose v2
- 一個您擁有控制權的**公開網域**（例如 `attendance.yourdomain.com`）
  - WebAuthn / 指紋登入必須使用真實可註冊的網域 — IP 位址與 `.local` 名稱均無法用於生物辨識
- **兩筆 DNS 記錄**指向您伺服器的公開 IP：
  - `attendance.yourdomain.com` → 前端
  - `api.yourdomain.com` → 後端（若您透過同一主機代理 `/api`，此項為選用 — 請參閱 §6）
- **80** 與 **443** 連接埠可從網際網路連通
- 可執行 `openssl rand -hex 32`（用於產生密鑰）

---

## 1. 將 repo clone 至伺服器

```bash
git clone <your-repo-url> /opt/gogofresh-attendance
cd /opt/gogofresh-attendance
```

---

## 2. 產生密鑰

於伺服器上執行下列指令（或將結果安全地複製過去）：

```bash
# JWT 簽章金鑰（務必保密 — 外洩等同於驗證被繞過）
openssl rand -hex 32

# PostgreSQL 密碼
openssl rand -base64 24
```

將兩組數值妥善保存 — 下一步會貼入 `.env` 檔案中。

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
| `DATABASE_URL` | `postgresql+asyncpg://attendance_user:<POSTGRES_PASSWORD>@db:5432/attendance` — 主機名稱 `db` 會解析到 compose 網路中的 postgres 容器。若使用代管資料庫，請改為該連線字串。 |
| `SECRET_KEY` | 貼上 §2 中 `openssl rand -hex 32` 的結果 |
| `ALGORITHM` | `HS256`（除非您明確知道原因，否則不要更動） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 預設 `30`；可調高以延長登入時效，調低以提升安全性 |
| `CORS_ORIGINS` | `["https://attendance.yourdomain.com"]` — 精確來源，結尾不可加斜線 |
| `CORS_ORIGIN_REGEX` | 保持**未設定 / 註解狀態**。此正規式僅用於 LAN 開發 |
| `WEBAUTHN_RP_ID` | `attendance.yourdomain.com` — **純主機名稱**，不含協定、連接埠或路徑 |
| `WEBAUTHN_RP_NAME` | 生物辨識提示顯示的任意名稱（例如 `GoGoFresh Attendance`） |
| `WEBAUTHN_ORIGIN` | `https://attendance.yourdomain.com` — 完整來源，必須為 HTTPS |

> **WebAuthn 注意事項**：`WEBAUTHN_RP_ID` 與 `WEBAUTHN_ORIGIN` 會被釘入每個已註冊的驗證器。若使用者註冊指紋後才變更任一項，則所有已註冊的憑證皆會失效，必須重新註冊。

### 3.2 前端 env

```bash
cp frontend/.env.production.example frontend/.env.production
```

編輯 `frontend/.env.production`：

| 變數 | 值 |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.yourdomain.com`（若您透過前端網域代理 `/api`，請改為 `""` — 參閱 §6 選項 B） |

> **重要**：`NEXT_PUBLIC_*` 於**建置時被編譯進 JS bundle**，而非執行時讀取。若要變更此值，必須重新建置前端容器。

### 3.3 Compose 層級 env

此為 repo 根目錄下的 `.env`，Docker Compose 會自動讀取以供 `docker-compose.prod.yml` 內的變數插值使用：

```bash
cat > .env <<'EOF'
POSTGRES_USER=attendance_user
POSTGRES_PASSWORD=<此處貼上 openssl rand -base64 24 的輸出>
POSTGRES_DB=attendance
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
EOF

chmod 600 .env
```

此處的 `POSTGRES_PASSWORD` **必須**與您 `backend/.env` 內 `DATABASE_URL` 所使用者相符。

---

## 4. 建置並啟動服務

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

首次建置約需 3–5 分鐘。確認所有服務均已啟動：

```bash
docker compose -f docker-compose.prod.yml ps
```

三個服務（`db`、`backend`、`frontend`）皆應顯示 `Up (healthy)` / `Up`。

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

Compose 檔中，後端與前端**僅暴露於 Docker 網路內部**（使用 `expose:` 而非 `ports:`）。您需要在前面架設反向代理，以終結 TLS 並導向公開流量。

兩種常見選項：

### 選項 A — Caddy（自動透過 Let's Encrypt 取得 TLS，零設定）

建立 `/etc/caddy/Caddyfile`：

```caddy
attendance.yourdomain.com {
    reverse_proxy localhost:3000
}

api.yourdomain.com {
    reverse_proxy localhost:8000
}
```

於主機安裝並啟動 Caddy：

```bash
sudo apt install caddy
sudo systemctl reload caddy
```

Caddy 會自動取得並續發 TLS 憑證。

接著，將容器連接埠僅發布於 localhost — 於 `docker-compose.prod.yml` 中，將 `expose:` 改為：

```yaml
  backend:
    ports:
      - "127.0.0.1:8000:8000"
  frontend:
    ports:
      - "127.0.0.1:3000:3000"
```

### 選項 B — 使用 nginx 達成同源（單一網域，透過 `/api` 代理 API）

若您不想發布 `api.yourdomain.com`，可由 `attendance.yourdomain.com` 統一服務：

```nginx
server {
    listen 443 ssl http2;
    server_name attendance.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/attendance.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/attendance.yourdomain.com/privkey.pem;

    # 後端 API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 前端
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

若使用選項 B，請於 `frontend/.env.production` 將 `NEXT_PUBLIC_API_URL=""`（空字串）設定好，讓 fetch 請求走同源。

---

## 7. 煙霧測試（Smoke Test）

```bash
# 後端健康檢查
curl https://api.yourdomain.com/health
# → {"status":"ok"}

# 前端可正常渲染
curl -I https://attendance.yourdomain.com
# → HTTP/2 200

# 由前端來源發出 CORS preflight
curl -I -X OPTIONS https://api.yourdomain.com/api/auth/login \
  -H "Origin: https://attendance.yourdomain.com" \
  -H "Access-Control-Request-Method: POST"
# → HTTP/2 200 且回應中包含 Access-Control-Allow-Origin 標頭
```

於瀏覽器開啟 `https://attendance.yourdomain.com`：

1. 以 `ADMIN` / 初始密碼登入
2. 立即更改密碼（管理員面板 → 編輯自身）
3. 註冊指紋 — 於 HTTPS 環境下應可成功
4. 登出，再以指紋登入

---

## 8. 備份

postgres volume 是唯一有狀態的部分。請設定每日備份：

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
# 保留 30 天
find "$BACKUP_DIR" -name '*.sql.gz' -mtime +30 -delete
```

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
- [ ] `POSTGRES_PASSWORD` 夠強，且僅保存於一處（未進入 git）
- [ ] `backend/.env`、`frontend/.env.production`、根目錄 `.env` 均為 `chmod 600` 且**未被 commit**
- [ ] `backend/.env` 中的 `CORS_ORIGIN_REGEX` 已取消設定
- [ ] DNS A / AAAA 記錄已指向伺服器
- [ ] TLS 憑證已簽發且可自動續發（Caddy 已內建；若使用 nginx，請搭配 certbot）
- [ ] `https://api.yourdomain.com/health` 回應 200
- [ ] 於瀏覽器中指紋註冊 + 登入可端對端成功
- [ ] 初始 ADMIN 密碼已更換，不再是 bootstrap 值
- [ ] 每日 postgres 備份 cron 已安裝，且至少已有一次備份成功執行
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
| Postgres 連線被拒 | 後端早於 DB 就緒前啟動 | 已由 `depends_on.condition: service_healthy` 處理；若仍持續發生，請檢查 DB 容器 log |
| 台灣行事曆顯示「未載入」 | CDN 請求被防火牆阻擋 | 於後端容器內測試 curl：`docker compose exec backend curl -I https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/2026.json` |
