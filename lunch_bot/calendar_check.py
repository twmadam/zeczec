"""從 Google 行事曆的 iCal 私密網址判斷今天是不是「居家」。"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests


@dataclass
class CalendarVerdict:
    """今日行事曆的判斷結果。"""

    checked: bool           # 有沒有真的查到行事曆
    is_home: bool           # 今天是否為居家日
    matched: list[str]      # 命中的活動標題
    all_titles: list[str]   # 今天全部的活動標題（方便你確認有抓對行事曆）
    error: str | None = None

    def describe(self) -> str:
        if not self.checked:
            return f"行事曆查詢失敗：{self.error}"
        if self.is_home:
            return "今天是居家日（命中：" + "、".join(self.matched) + "）"
        if self.all_titles:
            return "今天不是居家日，今日行程：" + "、".join(self.all_titles)
        return "今天不是居家日（行事曆今天沒有任何活動）"


def check_today(
    ics_url: str,
    home_keywords: list[str],
    timezone: str = "Asia/Taipei",
    day: dt.date | None = None,
    timeout: int = 30,
) -> CalendarVerdict:
    """抓取 iCal 並檢查當日活動標題是否含有居家關鍵字。

    會展開重複性活動（RRULE），所以「每週三居家」這種設定也讀得到。
    """
    if not ics_url:
        return CalendarVerdict(
            checked=False,
            is_home=False,
            matched=[],
            all_titles=[],
            error="尚未在設定檔填入 calendar.ics_url",
        )

    tzinfo = ZoneInfo(timezone)
    day = day or dt.datetime.now(tzinfo).date()

    try:
        resp = requests.get(ics_url, timeout=timeout)
        resp.raise_for_status()
        calendar = icalendar.Calendar.from_ical(resp.content)
        events = recurring_ical_events.of(calendar).between(
            day, day + dt.timedelta(days=1)
        )
    except Exception as exc:  # 網路、憑證、ICS 格式都可能出錯，一律當成「查不到」
        return CalendarVerdict(
            checked=False, is_home=False, matched=[], all_titles=[], error=str(exc)
        )

    titles = [str(ev.get("SUMMARY", "")).strip() for ev in events]
    titles = [t for t in titles if t]
    matched = [t for t in titles if any(kw in t for kw in home_keywords)]

    return CalendarVerdict(
        checked=True,
        is_home=bool(matched),
        matched=matched,
        all_titles=titles,
    )
