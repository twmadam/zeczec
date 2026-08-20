"""在 LINE 裡走完「作燴 ZoheyEats」的午餐訂購流程。

安全界線：本模組只會走到「選好 LINE Pay 付款方式」為止。
最後的確認付款與指紋驗證一律留給使用者本人，程式不代按。
"""

from __future__ import annotations

import time
from typing import Callable

from .config import Config
from .device import Screen


class OrderAborted(RuntimeError):
    """流程因為店家未開放訂餐等原因主動中止。"""


class LineOrderFlow:
    def __init__(
        self,
        screen: Screen,
        cfg: Config,
        log: Callable[[str], None] = print,
        ignore_availability: bool = False,
    ):
        self.s = screen
        self.cfg = cfg
        self.log = log
        self.ignore_availability = ignore_availability

    # ---------- 各階段 ----------

    def open_line(self) -> None:
        package = self.cfg.get("line.package")
        self.log(f"啟動 LINE（{package}）")
        self.s.d.app_start(package, stop=True)
        time.sleep(self.cfg.get("timing.app_launch", 6))
        self.s.shot("line_launched")

    def open_chat(self) -> None:
        """優先用深層連結直接開聊天室；沒設定就走搜尋。"""
        deeplink = self.cfg.get("line.chat_deeplink")
        if deeplink:
            self.log(f"以深層連結開啟聊天室：{deeplink}")
            self.s.d.open_url(deeplink)
            time.sleep(self.cfg.get("timing.page_load", 4))
        else:
            keyword = self.cfg.get("line.chat_search_keyword")
            self.log(f"在 LINE 內搜尋「{keyword}」")
            self.s.click(
                self.cfg.list_of_str("line.search_entry"),
                timeout=15,
                scroll=False,
                label="LINE 搜尋入口",
            )
            time.sleep(1.5)
            self.s.type_text(keyword)
            time.sleep(self.cfg.get("timing.search", 3))
            self.s.shot("search_results")
            self.s.click(
                self.cfg.list_of_str("line.chat_title_match"),
                timeout=10,
                label="作燴聊天室",
            )
            time.sleep(self.cfg.get("timing.page_load", 4))
        self.s.shot("chat_opened")

    def tap_order_lunch_tile(self) -> None:
        """點圖文選單左上角的「訂購午餐」。

        圖文選單是一張圖，沒有可讀的文字節點，只能用相對座標點。
        若選單是收合狀態，第一次點會落空，因此點完會確認 LIFF 有沒有打開，
        沒有的話先展開選單再試一次。
        """
        for attempt in (1, 2):
            x, y = self._tile_center("rich_menu.order_lunch")
            self.log(f"點擊圖文選單「訂購午餐」(相對座標 {x:.3f}, {y:.3f})，第 {attempt} 次")
            self.s.tap_relative(x, y)
            time.sleep(self.cfg.get("timing.page_load", 5))
            if self.s.page_contains(self.cfg.list_of_str("order.store_page_markers")):
                self.s.shot("store_list")
                return
            if attempt == 1:
                self.log("沒偵測到店家列表，先展開圖文選單再試一次")
                self.s.click(
                    self.cfg.list_of_str("line.rich_menu_toggle"),
                    timeout=5,
                    scroll=False,
                    required=False,
                    label="圖文選單開關",
                )
                time.sleep(2)
        self.s.shot("rich_menu_failed")
        raise LookupError(
            "點了「訂購午餐」但沒有開啟店家列表。"
            "請跑 tools/calibrate.py 重新校正 rich_menu 的 top/bottom 比例。"
        )

    def pick_store(self) -> None:
        store = self.cfg.list_of_str("order.store")
        self.log(f"選擇取餐地點：{store[0]}")
        self.s.click(store, timeout=20, label="取餐地點")
        time.sleep(self.cfg.get("timing.page_load", 4))
        self.s.shot("store_info")
        self._assert_available("店家資訊頁")

    def start_ordering(self) -> None:
        self.log("點擊「我要點餐」")
        self.s.click(
            self.cfg.list_of_str("order.start_button"), timeout=15, label="我要點餐"
        )
        time.sleep(self.cfg.get("timing.page_load", 5))
        self.s.shot("menu_page")
        self._assert_available("點餐頁")

    def pick_category(self) -> None:
        category = self.cfg.list_of_str("order.category")
        self.log(f"切換分類：{category[0]}")
        # 分類是水平捲動的頁籤列，先直接找，找不到再左右滑
        if not self.s.click(
            category, timeout=8, scroll=False, required=False, label="餐點分類"
        ):
            node = self.s.scroll_to(category, direction="left", max_swipes=4)
            if node is None:
                raise LookupError(f"找不到分類頁籤：{category}")
            node.click()
        time.sleep(self.cfg.get("timing.page_load", 3))
        self.s.shot("category")

    def pick_item(self) -> None:
        item_full = self.cfg.get("order.item_full")
        matches = self.cfg.list_of_str("order.item_match")
        self.log(f"選擇餐點：{item_full}")

        if self.s.click(matches, timeout=10, required=False, label="餐點"):
            time.sleep(self.cfg.get("timing.page_load", 3))
            self.s.shot("item_detail")
            return

        # 捲不到就改用頁面上的「搜尋全部商品」
        self.log("列表中找不到，改用商品搜尋")
        self.s.click(
            self.cfg.list_of_str("order.search_box"),
            timeout=10,
            scroll=False,
            label="商品搜尋框",
        )
        time.sleep(1.5)
        self.s.type_text(self.cfg.get("order.search_term", matches[-1]))
        time.sleep(self.cfg.get("timing.search", 3))
        self.s.shot("item_search")
        self.s.click(matches, timeout=10, label="餐點（搜尋結果）")
        time.sleep(self.cfg.get("timing.page_load", 3))
        self.s.shot("item_detail")

    def run_checkout_steps(self) -> None:
        """加入購物車 → 前往結帳 這段的畫面依店家設定而異，走設定檔驅動。"""
        for step in self.cfg.get("order.checkout_steps", []) or []:
            name = step.get("name", "未命名步驟")
            matches = step.get("match", [])
            optional = bool(step.get("optional", False))
            self.log(f"結帳步驟：{name}")
            clicked = self.s.click(
                matches,
                timeout=step.get("timeout", 12),
                required=not optional,
                label=name,
            )
            if not clicked:
                self.log(f"  （略過選用步驟：{name}）")
                continue
            time.sleep(step.get("wait", self.cfg.get("timing.page_load", 3)))
            self.s.shot(f"step_{name}")

    def pick_linepay(self) -> None:
        payment = self.cfg.list_of_str("order.payment")
        self.log(f"選擇付款方式：{payment[0]}")
        self.s.click(payment, timeout=15, label="LINE Pay 付款方式")
        time.sleep(self.cfg.get("timing.page_load", 4))
        self.s.shot("linepay_selected")

    def remind_fingerprint(self) -> None:
        title = "午餐訂購已備妥"
        text = (
            f"{self.cfg.get('order.item_full')} 已選好 LINE Pay，"
            "請你本人確認金額後用指紋完成付款。"
        )
        self.log("=" * 56)
        self.log("  " + title)
        self.log("  " + text)
        self.log("  程式到此停止，不會代按確認付款。")
        self.log("=" * 56)
        self.s.remind(title, text)

    # ---------- 內部工具 ----------

    def _tile_center(self, dotted: str) -> tuple[float, float]:
        rm = self.cfg.get("rich_menu")
        pos = self.cfg.get(dotted)
        top, bottom = float(rm["top"]), float(rm["bottom"])
        rows, cols = int(rm["rows"]), int(rm["cols"])
        x = (int(pos["col"]) - 0.5) / cols
        y = top + (bottom - top) * (int(pos["row"]) - 0.5) / rows
        return x, y

    def _assert_available(self, stage: str) -> None:
        markers = self.cfg.list_of_str("guards.unavailable_markers")
        hits = self.s.page_contains(markers)
        if not hits:
            return
        message = f"{stage}偵測到「{'、'.join(hits)}」，目前無法訂餐。"
        if self.ignore_availability:
            self.log(f"警告：{message}（--ignore-availability 已指定，繼續執行）")
            return
        raise OrderAborted(message + " 已停止，沒有送出任何訂單。")

    # ---------- 主流程 ----------

    def run(self) -> None:
        self.open_line()
        self.open_chat()
        self.tap_order_lunch_tile()
        self.pick_store()
        self.start_ordering()
        self.pick_category()
        self.pick_item()
        self.run_checkout_steps()
        self.pick_linepay()
        self.remind_fingerprint()
