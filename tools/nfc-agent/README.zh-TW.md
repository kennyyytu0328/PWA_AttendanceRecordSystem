# NFC 門禁打卡回補程式

把 SOYAL 701 匯出的 `YYYYMM.txt` 打卡檔傳送到考勤系統後端，用來補上員工漏打的手機打卡（單邊回補）。詳細設計請見 `docs/superpowers/specs/2026-07-01-nfc-punch-backup-design.md`。

## 安裝在門禁主機上（`DESKTOP-MMGK6PJ`）

1. 把 `push-nfc.ps1` 複製到門禁主機，例如 `C:\nfc-agent\push-nfc.ps1`。
2. 從 <https://curl.se/windows/> 下載 **curl for Windows**（64 位元），把壓縮檔內
   `bin\curl.exe` **和** `bin\curl-ca-bundle.crt` 兩個檔案複製到腳本同一個資料夾。

   > 原因：正式環境只接受 **TLS 1.3**，而 Windows 10 內建的 TLS
   > （`Invoke-RestMethod` 和 `System32\curl.exe` 使用的）最高只到 TLS 1.2。
   > OpenSSL 版的 curl 才支援 TLS 1.3。如果找不到 `curl.exe`，
   > 腳本會在記錄檔留下明確錯誤並結束。

3. 設定 API 金鑰為機器環境變數（必須跟後端的 `NFC_IMPORT_API_KEY` 一致）——
   要在**系統管理員**權限的視窗執行，設定後重開機（或重啟工作排程器服務），
   排程工作才看得到新變數：

   ```powershell
   [Environment]::SetEnvironmentVariable("NFC_IMPORT_API_KEY", "<你的密鑰>", "Machine")
   ```

4. 註冊每日排程工作（每天 00:20 執行，晚於門禁系統 00:10 的匯出時間）：

   ```cmd
   schtasks /Create /SC DAILY /ST 00:20 /RU SYSTEM /TN "GoGoFresh NFC Push" ^
     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\nfc-agent\push-nfc.ps1"
   ```

   `/RU SYSTEM` 讓排程不管有沒有人登入都會執行。

## 驗證方式

- 手動執行一次，並檢查記錄檔：

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File C:\nfc-agent\push-nfc.ps1
  Get-Content C:\nfc-agent\push-nfc.log -Tail 5
  ```

- 預期會看到類似這樣的紀錄：`OK 202607.txt: in=3 out=1 skipped=10 unknown=[] terminated=[]`。
- 端對端驗證：用測試卡 `02400:09483` 刷卡，等下一次匯出後執行本腳本，再到系統上確認該員工當天出現對應的打卡紀錄。

## 補充說明

- 參數皆可覆寫，例如：`push-nfc.ps1 -Folder "D:\door" -ApiUrl "https://…/api/nfc/import" -CurlExe "D:\tools\curl.exe"`。
- 門禁主機的 DHCP IP 無關緊要——本程式只會對外發送請求（outbound），不需要對內開放任何連接埠。
- 透過 `curl --data-binary` 傳送原始 CP950 編碼的檔案內容（bytes），解碼工作由後端負責。
- 腳本以 **UTF-8 with BOM** 編碼儲存——中文資料夾路徑在 Windows PowerShell 5.1
  下必須有 BOM 才能正確解析。編輯時請保留 BOM。
