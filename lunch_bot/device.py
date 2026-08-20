"""uiautomator2 的薄封裝：找元素、點擊、捲動、截圖、發提醒。"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from pathlib import Path

import uiautomator2 as u2


def xpath_literal(value: str) -> str:
    """把字串安全地包成 XPath 字面值（處理內含引號的情況）。"""
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    joined = ", \"'\", ".join(f"'{p}'" for p in parts)
    return f"concat({joined})"


class Screen:
    """一台已連線的 Android 裝置。"""

    def __init__(
        self,
        serial: str | None = None,
        artifacts_dir: str | Path = "artifacts",
        xpath_wait: float = 5.0,
    ):
        self.d = u2.connect(serial) if serial else u2.connect()
        # 預設 20 秒太久，等待邏輯由本模組的 find() 自己控制
        self.d.xpath.implicitly_wait(xpath_wait)
        self.artifacts = Path(artifacts_dir)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self._shot_seq = 0

    # ---------- 基本資訊 ----------

    def window_size(self) -> tuple[int, int]:
        return self.d.window_size()

    def texts(self) -> list[str]:
        """目前畫面上所有可見的文字（含 content-desc），用來做守門檢查與除錯。"""
        found: list[str] = []
        try:
            root = ET.fromstring(self.d.dump_hierarchy())
        except Exception:
            return found
        for node in root.iter():
            for attr in ("text", "content-desc"):
                value = (node.get(attr) or "").strip()
                if value and value not in found:
                    found.append(value)
        return found

    def page_contains(self, needles: list[str]) -> list[str]:
        """回傳畫面上命中的關鍵字。"""
        blob = "\n".join(self.texts())
        return [n for n in needles if n in blob]

    # ---------- 找與點 ----------

    def find(self, matches: list[str], timeout: float = 10.0):
        """依序用完全相符 / 部分相符 / content-desc 找元素，回傳第一個找到的。

        每一輪只抓一次畫面版面再拿去比對所有候選字串；若每個字串都各自
        重抓一次 UI 樹，光是找一個按鈕就要來回十幾趟，會慢到不堪用。
        """
        deadline = time.time() + timeout
        while True:
            source = self.d.xpath.get_page_source()
            for text in matches:
                lit = xpath_literal(text)
                for expr in (
                    f"//*[@text={lit}]",
                    f"//*[contains(@text, {lit})]",
                    f"//*[@content-desc={lit}]",
                    f"//*[contains(@content-desc, {lit})]",
                ):
                    selector = self.d.xpath(expr)
                    if selector.all(source):
                        # 回傳 selector 而非當下的節點，點擊時會重新定位，
                        # 避免頁面還在動畫時用到過期座標。
                        return selector
            if time.time() >= deadline:
                return None
            time.sleep(0.5)

    def click(
        self,
        matches: list[str],
        timeout: float = 10.0,
        scroll: bool = True,
        direction: str = "up",
        required: bool = True,
        label: str = "",
    ) -> bool:
        """找到並點擊；找不到時視 required 決定拋錯或回 False。"""
        node = self.find(matches, timeout=timeout)
        if node is None and scroll:
            node = self.scroll_to(matches, direction=direction)
        if node is None:
            if required:
                raise LookupError(
                    f"找不到{label or '目標元素'}：{matches}。"
                    f"目前畫面文字：{self.texts()[:40]}"
                )
            return False
        node.click()
        return True

    def scroll_to(self, matches: list[str], direction: str = "up", max_swipes: int = 8):
        """在可捲動頁面上邊滑邊找。"""
        for _ in range(max_swipes):
            self.d.swipe_ext(direction, scale=0.7)
            time.sleep(0.8)
            node = self.find(matches, timeout=1.5)
            if node is not None:
                return node
        return None

    def tap_relative(self, x: float, y: float) -> None:
        """以螢幕比例 (0~1) 點擊，避免綁死在特定解析度。"""
        self.d.click(x, y)

    def type_text(self, text: str) -> None:
        self.d.send_keys(text, clear=True)

    # ---------- 記錄與提醒 ----------

    def shot(self, name: str) -> Path:
        self._shot_seq += 1
        path = self.artifacts / f"{self._shot_seq:02d}_{name}.png"
        self.d.screenshot(str(path))
        return path

    def remind(self, title: str, text: str) -> None:
        """在手機上盡量大聲地提醒使用者（toast + 通知 + 震動）。"""
        try:
            self.d.toast.show(f"{title}｜{text}", 6.0)
        except Exception:
            pass
        try:
            self.d.shell(
                f'cmd notification post -S bigtext -t "{title}" lunch_bot "{text}"'
            )
        except Exception:
            pass
        try:
            self.d.shell("cmd vibrator vibrate 800")
        except Exception:
            pass
