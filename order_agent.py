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
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "menu.json"
STATE_PATH = BASE_DIR / "config" / "storage_state.json"

ADD_TO_CART_LABELS = ["加入購物車", "Add to cart", "新增"]
CART_LABELS = ["查看購物車", "View cart", "購物車"]
QUANTITY_PLUS_LABELS = ["+", "增加數量"]


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
        except Exception as exc:  # noqa: BLE001 - 嘗試下一個候選文字
            last_error = exc
    raise RuntimeError(f"找不到符合的按鈕（嘗試過: {labels}）") from last_error


def add_item_to_cart(page: Page, item: dict) -> None:
    name = item["name"]
    quantity = int(item.get("quantity", 1))
    print(f"正在加入餐點: {name} x{quantity}")

    page.get_by_text(name, exact=False).first.click(timeout=10000)
    click_first_match(page, ADD_TO_CART_LABELS)

    for _ in range(quantity - 1):
        click_first_match(page, QUANTITY_PLUS_LABELS, timeout=3000)

    page.keyboard.press("Escape")


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
    print(f"登入狀態已儲存到 {STATE_PATH}")


def run_order(playwright) -> None:
    if not STATE_PATH.exists():
        sys.exit("尚未登入，請先執行: python order_agent.py --login")

    config = load_config()
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(storage_state=str(STATE_PATH))
    page = context.new_page()

    page.goto(config["restaurant_url"])
    page.wait_for_load_state("networkidle")

    for item in config["items"]:
        try:
            add_item_to_cart(page, item)
        except Exception as exc:  # noqa: BLE001 - 單項失敗不應中斷整個流程
            print(f"加入「{item['name']}」失敗，請手動加入。錯誤: {exc}")

    try:
        click_first_match(page, CART_LABELS, role="link")
    except RuntimeError:
        print("找不到購物車按鈕，請手動點擊購物車確認內容。")

    print("\n購物車已準備完成，請在瀏覽器中確認內容並手動完成付款。")
    print("（此腳本不會自動送出付款，付款請務必由你親自點擊確認）")
    input("完成付款後按 Enter 鍵結束程式（瀏覽器將會關閉）...")
    browser.close()


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
