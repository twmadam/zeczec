# 自動訂餐 Agent

每天檢查 Google 日曆，只要當天有標題包含「居家」的活動，就在指定時間
（預設 11:45）自動開啟瀏覽器，把固定的 Uber Eats 餐點加入購物車並導到
結帳頁面；**最後付款一律由人工在瀏覽器中親自點擊確認**，腳本不會自動
送出付款。

這是因為：

- Uber Eats 的使用條款禁止自動下單機器人，全自動付款風險較高。
- 付款是難以復原的動作，自動化到「填好購物車」就停下來、交給人工做
  最後確認，可以兼顧便利與安全。

## 限制

此腳本會開啟一個「有畫面」的瀏覽器視窗讓你親自確認並付款，因此：

- **必須在你自己有桌面畫面的電腦上執行**（用 cron / 排程工具），
  **不能跑在 GitHub Actions 這類無頭雲端環境**。
- Uber Eats 網頁的按鈕文字、版面隨時可能改版，導致自動加入購物車失敗；
  失敗時腳本會印出錯誤訊息，請手動把該項餐點加入購物車即可。

## 安裝

```bash
pip install -r requirements.txt
playwright install chromium
```

## 設定檔

`config/menu.json`（此檔不含敏感資訊，已直接放在 repo 裡，可依需要修
改）：

```json
{
  "calendar": {
    "keyword": "居家",
    "calendar_id": "primary"
  },
  "order_time": "11:45",
  "items": [
    {
      "url": "https://www.ubereats.com/store-browse-uuid/.../6efe0244-3448-50bc-8283-fd686ac0df21?storeInfoHeader=true",
      "quantity": 1
    }
  ]
}
```

說明：

- `calendar.keyword`：日曆活動標題要包含的關鍵字，預設「居家」。
- `calendar.calendar_id`：要檢查的日曆，預設 `primary`（你的主要日曆）。
- `order_time`：純粹紀錄用，提醒你 cron 要排在這個時間（腳本本身不會
  自己等到這個時間，實際觸發時間由 cron 設定決定）。
- `items`：要加入購物車的餐點，每一項可以用兩種方式指定：
  - `{"url": "<餐點的直接連結>", "quantity": n}`：直接導到該餐點/組合
    頁面加入購物車（例如從 App 分享出來的餐點連結）。
  - `{"name": "<餐點名稱關鍵字>", "quantity": n}`：在 `restaurant_url`
    指定的餐廳頁面用文字搜尋並加入購物車。若使用此寫法，設定檔需另外
    加上 `"restaurant_url": "https://www.ubereats.com/tw/store/..."`。

兩種寫法可以混用，可參考 `config/menu.example.json`。

## Google 日曆設定

1. 到 [Google Cloud Console](https://console.cloud.google.com/) 建立
   專案，啟用「Google Calendar API」。
2. 在「憑證」頁面建立 OAuth 用戶端 ID，應用程式類型選「桌面應用程式」。
3. 下載憑證 JSON，存成 `config/google_credentials.json`（已加入
   `.gitignore`，不會進版控）。
4. 第一次執行 `daily_order_agent.py`（或 `--check-only`）時，會自動開
   啟瀏覽器要求你用 Google 帳號登入並授權唯讀存取日曆的權限，授權結果
   會存成 `config/google_token.json`（同樣已加入 `.gitignore`），之後
   排程執行就不需要再次登入。

可以先用以下指令測試日曆偵測是否正常（不會開 Uber Eats、不會訂餐）：

```bash
python daily_order_agent.py --check-only
```

## Uber Eats 首次登入

第一次使用前，需要手動登入一次 Uber Eats 帳號，登入狀態會儲存供之後
排程執行重複使用：

```bash
python order_agent.py --login
```

瀏覽器開啟後請手動完成登入，回到終端機按 Enter 即會儲存登入狀態到
`config/storage_state.json`（此檔案含敏感資訊，已加入 `.gitignore`，
不會進版控）。登入狀態過期後，重新執行此指令即可。

## 手動執行一次

```bash
# 完整流程：檢查日曆，符合才訂餐
python daily_order_agent.py

# 略過日曆檢查，直接把設定檔裡的餐點加入購物車
python order_agent.py
```

符合條件時，腳本會開啟瀏覽器、把設定好的餐點加入購物車、導到購物車
頁面，然後停下來等你確認。**請親自檢查購物車內容並點擊付款**，付款完
成後回到終端機按 Enter，腳本才會關閉瀏覽器。

## 排程設定

排程請統一執行 `daily_order_agent.py`（會先檢查日曆，沒有「居家」活
動就直接結束、不會開瀏覽器），時間設定在 `config/menu.json` 的
`order_time`（預設 11:45）。

### Linux（桌面環境 + cron）

cron 預設沒有 GUI 顯示環境，需要指定 `DISPLAY`：

```cron
# 每天上午 11:45 檢查日曆，若有「居家」活動才自動準備購物車
45 11 * * * DISPLAY=:0 /usr/bin/python3 /path/to/daily_order_agent.py >> /path/to/order_agent.log 2>&1
```

### macOS（launchd）

建議用 `launchd` 取代 cron，在 `~/Library/LaunchAgents/` 建立
plist，設定 `StartCalendarInterval` 為 11:45，並確保使用者已登入桌面。

### Windows（工作排程器）

在「工作排程器」建立工作，觸發程序設定每天 11:45 執行
`python.exe daily_order_agent.py`，並在「條件」分頁勾選「只有使用者登
入時才執行工作」，確保有桌面畫面可顯示瀏覽器。

## 安全提醒

- 請勿把 `config/storage_state.json`、`config/google_credentials.json`、
  `config/google_token.json` 提交到版本控制（已預設加入 `.gitignore`）。
- 此自動化方式並非 Uber Eats 官方支援的整合方式，使用時請自行評估帳
  號被平台偵測、限制的風險。
