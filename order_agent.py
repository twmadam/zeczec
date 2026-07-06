"""自動訂餐 Agent。

依照 config/menu.json 設定的固定菜單，自動開啟瀏覽器並把餐點加入 Uber Eats
購物車，導到結帳頁面後停下來——最後的付款按鈕一律由人工點擊確認，
腳本本身不會送出付款，以降低誤下單與違反平台條款的風險。

使用方式：
    python order_agent.py --login   # 首次使用前，手動登入並儲存登入狀態
    python order_agent.py           # 依排程執行，自動加入購物車並等待人工付款

此腳本需要在有畫面的環境執行（本機 cron / 排程工具），不能在
GitHub Actions 之類的無頭雲端環境執行，因為人工付款這一步需要看到
並點擊瀏覽器視窗。
"""

import argparse
import json
import logging
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "menu.json"
STATE_PATH = BASE_DIR / "config" / "storage_state.json"
LOG_PATH = BASE_DIR / "logs" / "order_agent.log"

ADD_TO_CART_LABELS = ["加入購物車", "Add to cart", "加入訂單", "Add to order", "新增"]
CART_LABELS = ["查看購物車", "View cart", "購物車"]
QUANTITY_PLUS_LABELS = ["+", "增加數量"]


def _setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("order_agent")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


log = _setup_logging()


def send_failure_email(subject: str, body: str) -> None:
    """寄送失敗通知信。若環境變數未設定則只記 log，不拋出例外。"""
    sender = os.environ.get("SENDER_EMAIL")
    password = os.environ.get("SENDER_PASSWORD")
    receiver = os.environ.get("RECEIVER_EMAIL")
    if not all([sender, password, receiver]):
        log.warning("未設定 SENDER_EMAIL / SENDER_PASSWORD / RECEIVER_EMAIL，略過寄送失敗通知信。")
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[自動訂餐] {subject}"
        msg["From"] = sender
        msg["To"] = receiver
        msg.set_content(body)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)
        log.info("失敗通知信已寄出至 %s", receiver)
    except Exception as exc:  # noqa: BLE001
        log.warning("寄送失敗通知信時發生錯誤: %s", exc)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"找不到設定檔: {CONFIG_PATH}\n"
            "請複製 config/menu.example.json 為 config/menu.json，並填入你的訂餐內容。"
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def click_first_match(page: Page, labels: list[str], role: str = "button", timeout: int = 5000) -> None:
    last_error = None
    for label in labels:
        try:
            page.get_by_role(role, name=label).first.click(timeout=timeout)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"找不到符合的按鈕（嘗試過: {labels}）") from last_error


def add_item_to_cart(page: Page, item: dict) -> None:
    """加入一項餐點到購物車。

    item 可以是兩種形式之一：
    - {"url": "<餐點的直接連結>", "quantity": n}：直接導到該餐點頁面再加入購物車
    - {"name": "<餐點名稱關鍵字>", "quantity": n}：在目前頁面（餐廳頁）用文字搜尋該餐點
    """
    quantity = int(item.get("quantity", 1))
    url = item.get("url")
    name = item.get("name")

    if url:
        log.info("開啟餐點連結: %s x%d", url, quantity)
        page.goto(url)
        page.wait_for_load_state("networkidle")
    elif name:
        log.info("搜尋並加入餐點: %s x%d", name, quantity)
        page.get_by_text(name, exact=False).first.click(timeout=10000)
    else:
        raise ValueError("設定檔中的餐點項目需要至少包含 'url' 或 'name'")

    click_first_match(page, ADD_TO_CART_LABELS)

    for _ in range(quantity - 1):
        click_first_match(page, QUANTITY_PLUS_LABELS, timeout=3000)

    page.keyboard.press("Escape")
    log.info("加入購物車成功")


def login(playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.ubereats.com/")

    print("請在開啟的瀏覽器視窗中手動登入你的 Uber Eats 帳號。")
    input("登入完成後，回到這裡按 Enter 鍵以儲存登入狀態...")

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(STATE_PATH))
    browser.close()
    log.info("Uber Eats 登入狀態已儲存到 %s", STATE_PATH)


def run_order(playwright) -> None:
    if not STATE_PATH.exists():
        log.error("尚未儲存 Uber Eats 登入狀態，請先執行: python order_agent.py --login")
        sys.exit(1)

    config = load_config()
    log.info("=== 開始執行訂餐流程 ===")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(storage_state=str(STATE_PATH))
    page = context.new_page()

    failures: list[str] = []

    restaurant_url = config.get("restaurant_url")
    if restaurant_url:
        log.info("導向餐廳頁面: %s", restaurant_url)
        page.goto(restaurant_url)
        page.wait_for_load_state("networkidle")

    for item in config["items"]:
        try:
            add_item_to_cart(page, item)
        except Exception as exc:  # noqa: BLE001
            label = item.get("name") or item.get("url")
            log.error("加入「%s」失敗: %s", label, exc)
            failures.append(f"「{label}」: {exc}")

    if failures:
        detail = "\n".join(failures)
        send_failure_email(
            "部分餐點加入購物車失敗，請手動補訂",
            f"以下餐點自動加入購物車時失敗，請手動開啟 Uber Eats 補訂：\n\n{detail}\n\n"
            f"完整 log 請查看：{LOG_PATH}",
        )

    try:
        click_first_match(page, CART_LABELS, role="link")
        log.info("已導向購物車頁面")
    except RuntimeError:
        log.warning("找不到購物車按鈕，請手動點擊購物車確認內容")

    log.info("購物車準備完成，等待用戶手動付款並關閉瀏覽器")
    print("\n購物車已準備完成，請在瀏覽器中確認內容並手動完成付款。")
    print("（付款完成後直接關閉瀏覽器視窗，腳本會自動結束）")

    # 等待用戶關閉瀏覽器視窗（timeout=0 = 永久等待），不依賴 TTY，
    # 確保 cron 執行時瀏覽器不會因為 input() 的 EOFError 而立刻被關閉。
    page.wait_for_event("close", timeout=0)
    log.info("=== 訂餐流程結束 ===")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="自動訂餐 Agent：自動把固定菜單加入 Uber Eats 購物車，付款一律由人工確認。"
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="手動登入並儲存登入狀態（首次使用前需執行一次，登入狀態過期後也需重新執行）",
    )
    args = parser.parse_args()

    with sync_playwright() as playwright:
        if args.login:
            login(playwright)
        else:
            run_order(playwright)


if __name__ == "__main__":
    main()
