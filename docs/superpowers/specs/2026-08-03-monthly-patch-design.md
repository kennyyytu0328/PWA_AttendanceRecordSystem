# 2026-08 系統修補設計規格（Monthly Patch）

**日期**：2026-08-03
**來源**：會議記錄（system patch meeting minutes）
**Branch**：`feature/monthly-patch-202608`
**範圍**：4 個功能 — 延後下班原因、HRM 匯出 + 測試帳號排除、月結鎖定、月度打卡修改提醒文字

---

## 功能 1：延後下班原因（late_leave_reason）

### 1.1 資料模型

- `daily_attendance_summaries` 新增 nullable 欄位 `late_leave_reason VARCHAR(30)`（Alembic migration，接在 `c9d0e1f2a3b4` 之後）。
- 允許值（存代碼，顯示文字走 i18n）：
  - `ASSIGNED_OVERTIME` = 「A:主管指派加班·另外依程序填寫加班單」
  - `PERSONAL` = 「B:因個人原因留在辦公室」
- Pydantic 層驗證只接受這兩個值（或 null）。
- `generate_daily_summary` 比照 `leave_type`/`remark`/`overtime_hours` round-trip 既有值（重算 summary 不得弄丟已存的原因）。
- `upsert_summary` 沿用 `_UNSET` sentinel 模式：未傳入的呼叫端不動既有值。

### 1.2 打卡頁確認畫面（frontend/src/app/punch/page.tsx）

- **觸發條件**（送出打卡前判斷）：打卡當下時間 > 使用者 `shift_end_time`（嚴格晚於；17:30 整不觸發），**且**當天 `day_kind` 為 `WORKDAY` 或 `MAKEUP_WORKDAY`（休息日/例假日/國定假日沒有排定下班時間，不觸發）。
- **Modal 內容**：
  - 標題文字：「您填寫的時間已超過您的班別 {HH:mm} 應下班時間，請勾選以下原因：」（{HH:mm} 帶入該員工 `shift_end_time`）
  - 單選項目列表：A / B 兩項，**預設勾選 B**。
  - **只有「確認」按鈕，沒有取消**。確認後才送出打卡。打卡時間有誤差時，同仁可再次打卡覆蓋，或到月度打卡修改調整。
- 兩條送出路徑（直接送出 + geolocation effect）都要經過此攔截；與既有 `submitLockRef` 防重複機制相容。
- **後端**：`POST /api/attendance/punch` request schema 新增 optional `late_leave_reason`；打卡成功並重算 summary 後，將該值寫入當日 summary。同一天多次超時打卡：每次都跳 modal，最後一次確認的值覆蓋前值。
- 後端不強制驗證「時間超過班別才可帶 reason」（信任前端觸發條件；值本身仍要通過白名單驗證）。

### 1.3 月度打卡修改頁（frontend/src/app/dashboard/monthly-override/page.tsx)

- 欄位順序：「上班(24h)｜下班(24h)｜**延後下班原因**｜…」— 新欄位緊接在下班欄之後。
- 欄位型態：下拉選單（空白 / A / B），可編輯規則與該列其他欄位相同（Sunday 鎖定、Saturday HR+ 等既有 editability matrix 照舊）。HR/ADMIN 代改他人時同樣可編輯。
- `GET /api/attendance/summaries` 回傳 `late_leave_reason` 供頁面預填。
- `PUT /api/attendance/override-bulk`：`BulkOverrideEntry` 新增 optional `late_leave_reason`，沿用 #38 的 key-presence 語意（explicit null 清除、省略保留）。

### 1.4 必填判定與送單閘門

- **必填條件**（per row）：`day_kind ∈ {WORKDAY, MAKEUP_WORKDAY}` 且當日最後下班時間（不論來源：APP 實際打卡、NFC 補卡、月度補填）**嚴格晚於** `shift_end_time`，而 `late_leave_reason` 為空 → 該列必填。
  - 17:30 整 = 準時，免填。
  - 忘打下班卡且尚未補填下班時間的日子：下班欄為空 → 不構成「晚於」→ 暫不必填；一旦補填了超過班別的時間，即轉為必填。
  - **請假/休假日免填**：`leave_type` 有值的列一律免填——**除非**該 `leave_type` 屬於「仍需填寫下班時間」的類型（如出差）。此類型清單存 `system_config` key `late_reason_required_leave_types`，value `{"leave_types": ["出差"]}`（預設值，可設定；比照 `export_excluded_emp_ids` 模式，不做管理 UI）。出差日補填的下班時間若晚於班別下班時間 → 照樣必填。
  - 免填規則前後端一體適用（月度頁的列掃描與 `POST /api/monthly-submissions` 的 server-side 驗證用同一判定）。
- **前端**：未填的必填列顯示醒目提示（比照 `rowNeedsPunchForOvertime` 的紅色列 highlight + 欄位紅框 + ⚠）。按「本月送單」時掃描**全月所有列**，凡必填未填 → 跳 modal 列出日期並**硬擋**（比照 `OvertimePunchModal`，無「繼續送出」選項）。
- **後端**（防繞過，已與使用者確認要做）：`POST /api/monthly-submissions` 建立前用同一規則掃描該月 summaries，發現必填未填 → `400`，`detail` 帶缺漏日期清單。日別分類用 `classify_day_kind`（與 #31 一致），時間比較用 naive `time()` 比對（與既有 tardiness 邏輯一致）。

### 1.5 不做的事（YAGNI）

- 匯出報表**不**新增延後下班原因欄位（會議未要求）。
- `/api/reports/daily`（team page）不回傳此欄位。
- 不新增獨立資料表——A/B 是固定二選項，直接存 summary 欄位。

---

## 功能 2：HRM 匯出 + 測試帳號排除

### 2.1 「HRM系統使用」匯出格式

- `GET /api/reports/export` 新增 `format=hrm`，輸出 **.xlsx**（openpyxl，與既有 Excel 匯出同套件）。
- 欄位（單一 sheet，首列標題）：

  | 序號 | 工號 | 姓名 | 考勤機ID | 刷卡日期 | 刷卡時間 | 補刷卡假勤類型原因 |
  |---|---|---|---|---|---|---|
  | 1 | R1000421 | 李孟芳 | *(空白)* | 2026/7/24 | 08:30 | APP打卡 |
  | 2 | R1000421 | 李孟芳 | *(空白)* | 2026/7/24 | 17:30 | APP打卡 |

- **列規則**：每人每天最多 2 列 — 首次上班一列、最後下班一列；單次打卡日（first == last）只出上班 1 列；無打卡日（ABSENT、請假無打卡、假日 filler）不出列。
- **格式細節**：序號從 1 起連續編號；考勤機ID 一律空白；刷卡日期 `YYYY/M/D` 不補零（如 `2026/7/24`）；刷卡時間 `HH:mm`；最後一欄**一律**「APP打卡」（不分 APP／NFC／補登來源，已與使用者確認）。
- 沿用報表頁既有篩選條件（日期區間、部門、emp_id、submission_filter、include_terminated）。
- **前端**：報表頁匯出區新增按鈕「HRM系統使用」，下載檔名 `hrm_export_{start}_{end}.xlsx`。

### 2.2 測試帳號排除（全部匯出格式）

- `system_config` 新 key `export_excluded_emp_ids`，value `{"emp_ids": ["HR01", "ADMIN"]}`（預設值；已與使用者確認做成可設定清單，帳號名不同時可直接改 DB config，不做管理 UI）。
- `export_attendance` 對**全部四種格式**（CSV/JSON/Excel/HRM）套用排除：清單內的 emp_id 一律不出現在匯出檔，**即使查詢明確指定該 emp_id** 也排除。
- 畫面上的報表顯示（`/api/reports/daily`）**不受影響**——只有匯出排除。

---

## 功能 3：月結鎖定（monthly override lock）

- `system_config` 新 key `monthly_override_lock`，value `{"locked": bool}`，預設 `false`。**全域單一開關，不分月份**。
- **API**（比照 `/api/admin/leave-types` 模式）：
  - `GET /api/admin/override-lock` — 任何登入者可讀（頁面需要知道要不要 render 唯讀）。
  - `PUT /api/admin/override-lock` — **HR+**（HR、ADMIN）可切換。
- **鎖定時的強制行為**（requester 角色為 EMPLOYEE 或 MANAGER）：
  - `PUT /api/attendance/override-bulk` → `403`
  - `POST /api/monthly-submissions` → `403`
  - **HR/ADMIN 完全不受限**（結算期間人資可繼續修正資料，已與使用者確認）。
- **前端**：
  - 月度打卡修改頁：載入時讀取鎖定狀態；鎖定且非 HR/ADMIN → 顯示鎖定橫幅（「月結作業中，暫停修改」類文案）、所有輸入欄位唯讀、儲存與本月送單按鈕停用。
  - 管理頁（admin）：新增區塊（HR+ 可見）顯示目前狀態 + 「鎖定」/「釋放」切換按鈕。
- 打卡頁**不受**鎖定影響（每日打卡照常）。

---

## 功能 4：月度打卡修改頁提醒文字

- 頁面頂部（篩選列之下、表格之上）加醒目橫幅：amber 底色 + 圖示，文字：

  > 備註：本月份排班表已依個人意願與公司工作需求排定，若對班表有疑慮或錯誤者，請與單位主管和人資進行修改確認，若逾期未提出，則視為同意本月排班，謝謝。

- 文案進 i18n（zh.json / en.json），所有人可見、不分角色。

---

## i18n 新增 key（zh / en 都要）

- 延後下班原因欄位標題、A/B 選項文字、打卡 modal 標題與確認鈕、送單缺漏 modal 文案
- 月結鎖定橫幅、admin 鎖定/釋放按鈕與狀態
- 排班確認提醒文字
- HRM 匯出按鈕「HRM系統使用」

## 測試策略（TDD，RED → GREEN）

**Backend（pytest）**
- schema：`late_leave_reason` 白名單驗證（punch request、BulkOverrideEntry）
- punch 帶 reason → summary 寫入；同日再打卡覆蓋
- `generate_daily_summary` round-trip `late_leave_reason`（重算不丟值）
- bulk override：設值 / explicit null 清除 / 省略保留（比照 `test_bulk_override_clear.py`）
- monthly-submissions 閘門：缺必填 → 400 + 日期清單；補齊後 → 201；非工作日超時列不擋；請假日（leave_type 有值）不擋；出差日（在 `late_reason_required_leave_types` 清單內）超時仍擋；清單未設定時用預設值 `["出差"]`
- override lock：locked 時 EMPLOYEE/MANAGER 403、HR/ADMIN 通過；GET/PUT 權限
- HRM export：欄位、序號、日期不補零、單次打卡日僅 1 列、無打卡日 0 列
- 排除清單：四種格式都排除、指定 emp_id 也排除、config 未設時用預設值

**Frontend（vitest）**
- 打卡頁：超時觸發 modal、預設 B、無取消鈕、確認後 payload 帶 reason、假日/準時不觸發
- 月度打卡修改頁：新欄位 render 與預填、必填紅色提示、送單硬擋 modal 列日期、鎖定時唯讀 + 橫幅、提醒文字 render
- 報表頁：HRM 按鈕觸發 `format=hrm` 下載

## 交付

- 完成後更新 CLAUDE.md（新增 design decision 條目）
- 雙 remote push（origin + bitbucket），由使用者指示後 commit/push
