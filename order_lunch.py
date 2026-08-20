#!/usr/bin/env python3
"""作燴 ZoheyEats 午餐自動訂購。

流程：查 Google 行事曆 → 沒有「居家」才繼續 → 開 LINE → 圖文選單「訂購午餐」
→ 臺北文創大樓 → 我要點餐 → 健康特餐 → 12FIT 七味蒜香雞胸(B) → 選 LINE Pay
→ 停下來提醒你用指紋付款。

程式不會替你按下最後的「確認付款」。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from lunch_bot.calendar_check import check_today
from lunch_bot.config import Config, ConfigError

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_ABORTED = 2
EXIT_UI_FAILED = 3
EXIT_HOME_DAY = 0  # 居家日不訂餐屬於正常結果


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", default="config.yaml", help="設定檔路徑")
    parser.add_argument("--serial", default=None, help="指定 adb 裝置序號")
    parser.add_argument("--artifacts", default="artifacts", help="截圖輸出資料夾")
    parser.add_argument("--check-only", action="store_true", help="只查行事曆，不碰手機")
    parser.add_argument(
        "--force",
        action="store_true",
        help="行事曆讀不到時仍然繼續（預設是讀不到就不訂，避免居家日還訂餐）",
    )
    parser.add_argument(
        "--ignore-availability",
        action="store_true",
        help="即使畫面顯示暫不供應也繼續往下點（不建議）",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="跳過開始前的確認提問")
    return parser


def confirm(cfg: Config) -> bool:
    print()
    print("即將在你的手機上自動操作並選擇付款方式，內容如下：")
    print(f"  取餐地點：{cfg.list_of_str('order.store')[0]}")
    print(f"  餐點分類：{cfg.list_of_str('order.category')[0]}")
    print(f"  餐點：    {cfg.get('order.item_full')}")
    print(f"  付款：    {cfg.list_of_str('order.payment')[0]}（最後仍需你本人指紋確認）")
    print()
    answer = input("確定要開始嗎？輸入 y 繼續：").strip().lower()
    return answer == "y"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        cfg = Config.load(args.config)
    except ConfigError as exc:
        log(f"設定錯誤：{exc}")
        return EXIT_CONFIG

    # ---- 1. 行事曆 ----
    log("查詢今日 Google 行事曆…")
    verdict = check_today(
        ics_url=cfg.get("calendar.ics_url", ""),
        home_keywords=cfg.list_of_str("calendar.home_keywords"),
        timezone=cfg.get("calendar.timezone", "Asia/Taipei"),
    )
    log(verdict.describe())

    if verdict.is_home:
        log("今天居家，不訂午餐。結束。")
        return EXIT_HOME_DAY

    if not verdict.checked:
        if not args.force:
            log("讀不到行事曆，為避免居家日誤訂，已停止。確定要訂請加 --force。")
            return EXIT_CONFIG
        log("讀不到行事曆，但已指定 --force，繼續執行。")

    if args.check_only:
        log("--check-only：到此為止，未操作手機。")
        return EXIT_OK

    # ---- 2. 確認 ----
    if not args.yes and not confirm(cfg):
        log("已取消。")
        return EXIT_OK

    # ---- 3. 操作手機 ----
    # 延後 import，讓 --check-only 在沒有裝置/沒裝 uiautomator2 時也能跑
    from lunch_bot.device import Screen
    from lunch_bot.line_flow import LineOrderFlow, OrderAborted

    try:
        screen = Screen(serial=args.serial, artifacts_dir=args.artifacts)
    except Exception as exc:
        log(f"連線手機失敗：{exc}")
        log("請確認手機已開啟 USB 偵錯、adb devices 看得到，且已跑過 python -m uiautomator2 init")
        return EXIT_CONFIG

    width, height = screen.window_size()
    log(f"已連線裝置，螢幕解析度 {width}x{height}")

    flow = LineOrderFlow(
        screen, cfg, log=log, ignore_availability=args.ignore_availability
    )
    try:
        flow.run()
    except OrderAborted as exc:
        log(f"流程中止：{exc}")
        screen.shot("aborted")
        screen.remind("午餐未訂成", str(exc))
        return EXIT_ABORTED
    except LookupError as exc:
        log(f"找不到畫面元素：{exc}")
        path = screen.shot("ui_failed")
        log(f"已存下當時畫面：{path}，請據此調整 config.yaml 的比對字串。")
        return EXIT_UI_FAILED

    log(f"完成。截圖在 {args.artifacts}/ 。")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
