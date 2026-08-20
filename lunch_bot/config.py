"""設定檔載入與驗證。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# 缺少任何一項就沒辦法安全地跑完流程，啟動時就擋下來，
# 不要等點到一半才發現訂錯餐。
REQUIRED_KEYS = (
    "calendar.timezone",
    "calendar.home_keywords",
    "line.package",
    "rich_menu.order_lunch",
    "order.store",
    "order.category",
    "order.item_full",
    "order.item_match",
    "order.payment",
    "guards.unavailable_markers",
)


class ConfigError(RuntimeError):
    """設定檔格式或內容有問題。"""


class Config:
    def __init__(self, data: dict[str, Any]):
        self._data = data
        self._validate()

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path)
        if not path.exists():
            raise ConfigError(
                f"找不到設定檔 {path}，請先複製 config.example.yaml 成 config.yaml"
            )
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ConfigError(f"{path} 最外層必須是 YAML 物件")
        return cls(data)

    def _validate(self) -> None:
        missing = [key for key in REQUIRED_KEYS if self.get(key) is None]
        if missing:
            raise ConfigError("設定檔缺少必要欄位：" + "、".join(missing))

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def list_of_str(self, dotted: str) -> list[str]:
        """取出字串陣列；單一字串也接受，統一轉成 list。"""
        value = self.get(dotted, [])
        if isinstance(value, str):
            return [value]
        if not isinstance(value, list):
            raise ConfigError(f"{dotted} 必須是字串或字串陣列")
        return [str(v) for v in value]
