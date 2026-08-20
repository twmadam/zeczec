# 作燴 ZoheyEats 午餐自動訂購

在自己的電腦上執行，透過 adb 驅動你的 Android 手機，自動走完 LINE 裡「作燴 ZoheyEats」的午餐訂購流程：

```
查 Google 行事曆 → 今天沒有「居家」才繼續
  → 開啟 LINE → 圖文選單「訂購午餐」
  → 作燴 - 臺北文創大樓 → 我要點餐
  → 健康特餐 → 12FIT - 特餐_七味蒜香雞胸(B)
  → 選擇 LINE Pay
  → 停下來，提醒你用指紋完成付款
```

## 安全界線

**程式不會替你按下最後的「確認付款」，也不會碰指紋驗證。** 它只做到把付款方式選成 LINE Pay，
然後用 toast、系統通知與震動提醒你，剩下的金額確認與生物辨識由你本人完成。

另外有兩道保護：

- **行事曆讀不到就不訂餐**（fail closed）。與其在居家日誤訂一個便當，不如什麼都不做。
  真的要在讀不到行事曆時硬跑，得自己加 `--force`。
- **畫面出現「暫不供應」「暫不開放點餐」等字樣就中止**，不會繼續亂點。
  這些字串列在 `config.yaml` 的 `guards.unavailable_markers`。

## 需要什麼

- 一台電腦（Windows / macOS / Linux 都可）安裝 Python 3.10+ 與 [adb](https://developer.android.com/tools/adb)
- 你的 Android 手機，開啟「開發人員選項 → USB 偵錯」，並用 USB 或 `adb connect` 連上電腦
- 手機上已登入 LINE，且已加入「作燴 ZoheyEats」官方帳號

## 安裝

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows：.venv\Scripts\activate
pip install -r requirements.txt

python -m uiautomator2 init        # 在手機上安裝 uiautomator2 需要的服務
adb devices                        # 確認看得到你的手機

cp config.example.yaml config.yaml
```

## 設定

編輯 `config.yaml`：

### 1. Google 行事曆

Google 行事曆網頁版 → 左側選單找到該行事曆 → **設定** → 捲到「整合行事曆」→
複製 **私密網址（iCal 格式）**，貼到 `calendar.ics_url`。

```yaml
calendar:
  ics_url: "https://calendar.google.com/calendar/ical/.../basic.ics"
  home_keywords: ["居家", "WFH", "在家上班"]
```

會展開重複性活動，所以「每週三居家」這種設定也讀得到。
先單獨驗證這一段，不會碰到手機：

```bash
python order_lunch.py --check-only
```

### 2. 圖文選單座標

LINE 的圖文選單是一整張圖片，UI 樹裡沒有文字節點可以抓，只能用螢幕相對座標點。
`rich_menu.top` / `bottom` 是選單區塊上下緣佔螢幕高度的比例，預設值依 Samsung 直式螢幕估算，
換手機或選單改版就要重新校正：

```bash
# 先在手機上開好作燴的聊天室、展開圖文選單，再執行
python tools/calibrate.py            # 倒出截圖與所有元素座標
python tools/calibrate.py --tap-tile # 依目前設定實際點一下「訂購午餐」試試
```

把截圖裡量到的選單上下緣像素值除以螢幕高度，填回 `config.yaml`。

若你知道作燴官方帳號的深層連結（`line://ti/p/@xxxx`），填進 `line.chat_deeplink`
可以直接跳到聊天室，比用搜尋穩定得多。

### 3. 結帳步驟

「加入購物車 → 結帳」這幾頁的按鈕文字依店家設定而異，設定檔中列為 `optional`，
找不到就自動略過。第一次跑完請翻 `artifacts/` 裡的截圖，把實際按鈕文字補進
`order.checkout_steps`。

## 執行

```bash
python order_lunch.py                      # 完整流程（開始前會問你一次）
python order_lunch.py --check-only         # 只查行事曆
python order_lunch.py -y                   # 跳過確認提問，適合排程
python order_lunch.py --force              # 行事曆讀不到也照跑
python order_lunch.py --ignore-availability  # 顯示暫不供應仍繼續（不建議）
```

離開碼：`0` 正常（含居家日不訂餐）、`1` 設定或行事曆問題、`2` 因店家未開放而中止、
`3` 找不到畫面元素（`artifacts/` 會留下當時截圖）。

每一步都會截圖到 `artifacts/`，流程走歪時照著截圖調 `config.yaml` 的比對字串即可，
通常不需要改程式。

### 每天自動跑

macOS / Linux，平日 11:30：

```cron
30 11 * * 1-5 cd /path/to/zeczec && .venv/bin/python order_lunch.py -y >> lunch.log 2>&1
```

Windows 用工作排程器叫同一行指令。手機要保持連著電腦、螢幕解鎖。

## 已知限制

- **訂餐時段**：作燴過了訂餐時間就會顯示「暫不供應 / 暫不開放點餐」，這時腳本會中止。
  請把排程設在你們公司的訂餐時段內。
- 手機必須解鎖且螢幕亮著，uiautomator 才點得到東西。
- LINE 或作燴改版就可能要重新校正；改 `config.yaml` 的比對字串通常就夠。
- 最後的付款確認與指紋，永遠是你自己按。

## 測試

```bash
python -m unittest discover -s tests -v
```

不需要實體手機，涵蓋行事曆判斷（含重複活動與失敗情境）、設定驗證、
圖文選單座標換算與未開放訂餐的守門邏輯。
