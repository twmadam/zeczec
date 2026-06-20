"""每日排程入口。

由 cron / 排程工具在固定時間（例如 11:45）執行此腳本：
1. 檢查今天的 Google 日曆是否有標題包含指定關鍵字（預設「居家」）的活動。
2. 如果有，才啟動 Uber Eats 自動訂餐流程（加入購物車，最後付款交給人工確認）。
3. 如果沒有，什麼都不做，直接結束。

使用方式：
    python daily_order_agent.py                # 正式執行：檢查日曆，符合才訂餐
    python daily_order_agent.py --check-only    # 只檢查日曆並印出結果，不開瀏覽器訂餐
"""

import argparse

from playwright.sync_api import sync_playwright

import calendar_check
import order_agent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="每日排程入口：偵測到日曆中的關鍵字活動才自動準備 Uber Eats 購物車。"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只檢查日曆並印出結果，不開瀏覽器、不執行訂餐（方便測試日曆設定）",
    )
    args = parser.parse_args()

    config = order_agent.load_config()
    calendar_config = config.get("calendar", {})
    keyword = calendar_config.get("keyword", "居家")
    calendar_id = calendar_config.get("calendar_id", "primary")

    found = calendar_check.has_keyword_event_today(keyword, calendar_id)

    if not found:
        print(f"今天的 Google 日曆沒有包含「{keyword}」的活動，不執行訂餐。")
        return

    print(f"偵測到今天的日曆活動包含「{keyword}」。")
    if args.check_only:
        print("（--check-only 模式，不執行訂餐）")
        return

    print("開始執行自動訂餐流程...")
    with sync_playwright() as playwright:
        order_agent.run_order(playwright)


if __name__ == "__main__":
    main()
