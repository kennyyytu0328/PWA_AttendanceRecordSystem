# NFC 門禁打卡回補程式

把 SOYAL 701 匯出的 `YYYYMM.txt` 打卡檔傳送到考勤系統後端，用來補上員工漏打的手機打卡（單邊回補）。詳細設計請見 `docs/superpowers/specs/2026-07-01-nfc-punch-backup-design.md`。

## 目前部署狀態（實際環境，2026-07-03 驗證通過）

| 項目 | 值 |
|---|---|
| 主機 | `DESKTOP-MMGK6PJ`（門禁主機，辦公室內網，DHCP —— 2026-07-03 時為 `192.168.2.165`） |
| 安裝資料夾 | `C:\Users\ltre5\nfc-agent\` |
| 檔案 | `push-nfc.ps1`、`curl.exe`、`curl-ca-bundle.crt`（+ `push-nfc.log`） |
| curl | 8.21.0 win64（curl.se）—— LibreSSL 4.3.2 後端，支援 TLS 1.3 |
| API 金鑰 | `NFC_IMPORT_API_KEY` 已設為**機器層級**環境變數（HKLM）—— 已完成 |
| 排程工作 | `GoGoFresh NFC Push` —— 每天 **00:20**、`/RU SYSTEM` —— 已註冊 |
| SOYAL 匯出 | `C:\Users\ltre5\OneDrive\桌面\門禁\YYYYMM.txt`，每天約 00:10 產生 |

2026-07-03 端對端驗證結果：

- 手動執行：`OK 202607.txt: in=0 out=1 skipped=7 unknown=[] terminated=[]`
- 隨後由工作排程觸發執行：`OK 202607.txt: in=0 out=0 skipped=8 …`
  （第一次回補的那一側，第二次已被視為「已打卡」——證明冪等性正常），
  排程「上次結果」代碼為 `0`。

## 遠端管理（SSH）

門禁主機跑著 **OpenSSH Server**（OpenSSH for Windows 9.5）。主機名稱在內網
解析不到——請用 IP 連線（DHCP 配發；連不上時先到路由器查現在的租約）。

- 互動式：`ssh gogoffcc_doorcontrol`（`~/.ssh/config` 別名 →
  `gateadmin@192.168.2.165`，僅密碼驗證——密碼**刻意不寫在**本 repo，請向資訊人員索取）。
- 腳本自動化（OpenSSH 無法用腳本餵密碼）：改用 PuTTY 的 `plink` / `pscp`，
  並**固定主機金鑰指紋**。不加 `-hostkey` 時 plink 會卡在首次連線的
  金鑰確認提示永遠不動——就算用 `echo y |` 灌進去也一樣。

  ```cmd
  plink -batch -ssh -hostkey "SHA256:5do06ov4BYF3zmNRXD0rdbLTJZORSDSwlDD7ZPy8ZZs" ^
    -pw <密碼> gateadmin@192.168.2.165 "schtasks /Query /TN ""GoGoFresh NFC Push"""

  pscp -batch -hostkey "SHA256:5do06ov4BYF3zmNRXD0rdbLTJZORSDSwlDD7ZPy8ZZs" ^
    -pw <密碼> push-nfc.ps1 gateadmin@192.168.2.165:C:/Users/ltre5/nfc-agent/
  ```

  遠端 shell 是 `cmd.exe`；要跑 PowerShell 請包成
  `powershell -NoProfile -Command "..."`。`gateadmin` 帳號可以讀寫
  `C:\Users\ltre5\` 也能管理排程工作。

## 安裝／重新安裝步驟

1. 把 `push-nfc.ps1` 複製到 `C:\Users\ltre5\nfc-agent\push-nfc.ps1`（目前部署
   的實際路徑——若要改放別處，記得同步修改排程工作的 `/TR` 路徑）。
2. 從 <https://curl.se/windows/> 下載 **curl for Windows**（64 位元），把壓縮檔內
   `bin\curl.exe` **和** `bin\curl-ca-bundle.crt` 兩個檔案複製到腳本同一個資料夾。

   > 原因：正式環境只接受 **TLS 1.3**，而 Windows 10 內建的 TLS
   > （`Invoke-RestMethod` 和 `System32\curl.exe` 使用的）最高只到 TLS 1.2。
   > curl.se 的版本自帶 TLS 函式庫（8.21.0 版為 LibreSSL），支援 TLS 1.3。
   > 如果找不到 `curl.exe`，腳本會在記錄檔留下明確錯誤並結束。

3. 設定 API 金鑰為機器環境變數（必須跟後端的 `NFC_IMPORT_API_KEY` 一致）——
   要在**系統管理員**權限的視窗執行，設定後重開機（或重啟工作排程器服務），
   排程工作才看得到新變數。*（目前的安裝已設定完成。）*

   ```powershell
   [Environment]::SetEnvironmentVariable("NFC_IMPORT_API_KEY", "<你的密鑰>", "Machine")
   ```

4. 註冊每日排程工作（每天 00:20 執行，晚於門禁系統 00:10 的匯出時間）：

   ```cmd
   schtasks /Create /SC DAILY /ST 00:20 /RU SYSTEM /TN "GoGoFresh NFC Push" ^
     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\ltre5\nfc-agent\push-nfc.ps1"
   ```

   `/RU SYSTEM` 讓排程不管有沒有人登入都會執行。*（目前的安裝已註冊完成。）*

## 驗證方式

- 手動執行一次（或 `schtasks /Run /TN "GoGoFresh NFC Push"`），並檢查記錄檔：

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\ltre5\nfc-agent\push-nfc.ps1
  Get-Content C:\Users\ltre5\nfc-agent\push-nfc.log -Tail 5
  ```

- 預期會看到類似這樣的紀錄：`OK 202607.txt: in=0 out=1 skipped=7 unknown=[] terminated=[]`。
- 端對端驗證：用測試卡 `02400:09483` 刷卡，等下一次匯出後執行本腳本，再到系統上確認該員工當天出現對應的打卡紀錄。

## 補充說明

- 參數皆可覆寫，例如：`push-nfc.ps1 -Folder "D:\door" -ApiUrl "https://…/api/nfc/import" -CurlExe "D:\tools\curl.exe"`。
- 門禁主機的 DHCP IP 跟推送功能無關——本程式只會對外發送請求（outbound），不需要對內開放任何連接埠。（IP 只有 SSH 連進去管理時才重要，見上方。）
- 透過 `curl --data-binary` 傳送原始 CP950 編碼的檔案內容（bytes），解碼工作由後端負責。
- 腳本以 **UTF-8 with BOM** 編碼儲存——中文資料夾路徑在 Windows PowerShell 5.1
  下必須有 BOM 才能正確解析。編輯時請保留 BOM。
- 若修改了 `push-nfc.ps1`，請用 `pscp` 重新部署（見「遠端管理」），並比對雜湊值：
  門禁主機上跑 `certutil -hashfile C:\Users\ltre5\nfc-agent\push-nfc.ps1 SHA256`，
  本機用 `Get-FileHash` 對照。
