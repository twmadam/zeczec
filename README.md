# 自動訂餐 Agent

依排程自動把固定菜單加入 Uber Eats 購物車並導到結帳頁面；**最後付款一律
由人工在瀏覽器中親自點擊確認**，腳本不會自動送出付款。

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

## 設定菜單

複製範例設定檔並填入你的餐廳網址與想吃的餐點：

```bash
cp config/menu.example.json config/menu.json
```

`config/menu.json`：

```json
{
  "restaurant_url": "https://www.ubereats.com/tw/store/你的餐廳ID",
  "items": [
    { "name": "招牌雞腿便當", "quantity": 1 },
    { "name": "可口可樂", "quantity": 1 }
  ]
}
```

`name` 用來在菜單頁面搜尋對應的餐點文字，建議填餐點名稱中容易匹配到的
關鍵字。

## 首次登入

第一次使用前，需要手動登入一次 Uber Eats 帳號，登入狀態會儲存供之後排
程執行重複使用：

```bash
python order_agent.py --login
```

瀏覽器開啟後請手動完成登入，回到終端機按 Enter 即會儲存登入狀態到
`config/storage_state.json`（此檔案含敏感資訊，已加入 `.gitignore`，
不會進版控）。登入狀態過期後，重新執行此指令即可。

## 手動執行一次

```bash
python order_agent.py
```

腳本會開啟瀏覽器、把設定好的餐點加入購物車、導到購物車頁面，然後停
下來等你確認。**請親自檢查購物車內容並點擊付款**，付款完成後回到終端
機按 Enter，腳本才會關閉瀏覽器。

## 排程設定

### Linux（桌面環境 + cron）

cron 預設沒有 GUI 顯示環境，需要指定 `DISPLAY`：

```cron
# 每個工作日上午 11:00 自動準備購物車
0 11 * * 1-5 DISPLAY=:0 /usr/bin/python3 /path/to/order_agent.py >> /path/to/order_agent.log 2>&1
```

### macOS（launchd）

建議用 `launchd` 取代 cron，在 `~/Library/LaunchAgents/` 建立
plist，設定 `StartCalendarInterval` 對應時間，並確保使用者已登入桌面。

### Windows（工作排程器）

在「工作排程器」建立工作，觸發程序設定每日特定時間執行
`python.exe order_agent.py`，並在「條件」分頁勾選「只有使用者登入時才
執行工作」，確保有桌面畫面可顯示瀏覽器。

## 安全提醒

- 請勿把 `config/menu.json`、`config/storage_state.json` 提交到版本控
  制（已預設加入 `.gitignore`）。
- 此自動化方式並非 Uber Eats 官方支援的整合方式，使用時請自行評估帳
  號被平台偵測、限制的風險。
