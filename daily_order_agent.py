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
import logging

from playwright.sync_api import sync_playwright

import calendar_check
import order_agent

log = order_agent._setup_logging()


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

    log.info("=== daily_order_agent 啟動，關鍵字：「%s」===", keyword)

    try:
        found = calendar_check.has_keyword_event_today(keyword, calendar_id)
    except Exception as exc:  # noqa: BLE001
        log.error("Google 日曆查詢失敗（可能是 token 過期，請重新執行授權）: %s", exc)
        order_agent.send_failure_email(
            "Google 日曆查詢失敗",
            f"今天 11:45 的自動訂餐檢查因 Google 日曆 API 錯誤而中止：\n\n{exc}\n\n"
            "請執行 python daily_order_agent.py --check-only 重新觸發 OAuth 授權流程。",
        )
        return

    if not found:
        log.info("今天的 Google 日曆沒有包含「%s」的活動，不執行訂餐。", keyword)
        return

    log.info("偵測到今天的日曆活動包含「%s」。", keyword)
    if args.check_only:
        log.info("（--check-only 模式，不執行訂餐）")
        return

    log.info("開始執行自動訂餐流程...")
    with sync_playwright() as playwright:
        order_agent.run_order(playwright)


if __name__ == "__main__":
    main()
