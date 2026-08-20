#!/usr/bin/env python3
"""校正工具：把目前手機畫面的截圖、元素文字與座標倒出來。

用途有二：
1. 補齊 config.yaml 裡各步驟的比對字串（跑到哪一頁就對那一頁執行）。
2. 校正 rich_menu 的 top/bottom 比例，以及驗證「訂購午餐」點得到。

範例：
    python tools/calibrate.py                 # 倒出目前畫面
    python tools/calibrate.py --tap-tile      # 依設定實際點一下訂購午餐格子
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lunch_bot.config import Config  # noqa: E402
from lunch_bot.device import Screen  # noqa: E402

BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def dump_nodes(screen: Screen, out_dir: Path) -> None:
    width, height = screen.window_size()
    print(f"螢幕解析度：{width} x {height}\n")

    xml_text = screen.d.dump_hierarchy()
    (out_dir / "hierarchy.xml").write_text(xml_text, encoding="utf-8")
    shot = screen.shot("calibrate")

    root = ET.fromstring(xml_text)
    print(f"{'文字 / content-desc':<40} {'可點':<5} {'y 上緣':>7} {'y 下緣':>7}")
    print("-" * 64)
    for node in root.iter():
        label = (node.get("text") or node.get("content-desc") or "").strip()
        if not label:
            continue
        match = BOUNDS_RE.match(node.get("bounds") or "")
        if not match:
            continue
        _, y1, _, y2 = (int(g) for g in match.groups())
        clickable = "是" if node.get("clickable") == "true" else ""
        print(f"{label[:38]:<40} {clickable:<5} {y1 / height:>7.3f} {y2 / height:>7.3f}")

    print(f"\n截圖：{shot}")
    print(f"版面：{out_dir / 'hierarchy.xml'}")
    print(
        "\n提示：圖文選單是圖片，不會出現在上表。請開啟截圖量出選單上下緣的像素值，"
        f"各除以 {height}，填入 config.yaml 的 rich_menu.top / rich_menu.bottom。"
    )


def tap_tile(screen: Screen, cfg: Config) -> None:
    rm = cfg.get("rich_menu")
    pos = cfg.get("rich_menu.order_lunch")
    top, bottom = float(rm["top"]), float(rm["bottom"])
    rows, cols = int(rm["rows"]), int(rm["cols"])
    x = (int(pos["col"]) - 0.5) / cols
    y = top + (bottom - top) * (int(pos["row"]) - 0.5) / rows
    width, height = screen.window_size()
    print(f"點擊相對座標 ({x:.3f}, {y:.3f}) → 絕對座標 ({int(x * width)}, {int(y * height)})")
    screen.tap_relative(x, y)
    print("已點擊，請看手機是否開啟店家列表。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("--serial", default=None)
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--tap-tile", action="store_true", help="實際點一下訂購午餐格子")
    args = parser.parse_args()

    screen = Screen(serial=args.serial, artifacts_dir=args.artifacts)
    if args.tap_tile:
        tap_tile(screen, Config.load(args.config))
        return 0
    dump_nodes(screen, Path(args.artifacts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
