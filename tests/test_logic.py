"""不需要實體手機就能跑的邏輯測試。"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lunch_bot.calendar_check import check_today  # noqa: E402
from lunch_bot.config import Config, ConfigError  # noqa: E402
from lunch_bot.device import xpath_literal  # noqa: E402
from lunch_bot.line_flow import LineOrderFlow, OrderAborted  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//EN
BEGIN:VEVENT
UID:wfh@test
DTSTART;TZID=Asia/Taipei:20260101T090000
DTEND;TZID=Asia/Taipei:20260101T180000
RRULE:FREQ=WEEKLY;BYDAY=TH
SUMMARY:居家辦公
END:VEVENT
BEGIN:VEVENT
UID:mtg@test
DTSTART;TZID=Asia/Taipei:20260819T140000
DTEND;TZID=Asia/Taipei:20260819T150000
SUMMARY:團隊週會
END:VEVENT
END:VCALENDAR
"""


def fake_get(*_args, **_kwargs):
    resp = mock.Mock()
    resp.content = ICS.encode()
    resp.raise_for_status = lambda: None
    return resp


class FakeScreen:
    """只實作 LineOrderFlow 會用到的部分。"""

    def __init__(self, texts: list[str]):
        self._texts = texts

    def page_contains(self, needles: list[str]) -> list[str]:
        blob = "\n".join(self._texts)
        return [n for n in needles if n in blob]


class XPathLiteralTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(xpath_literal("健康特餐"), "'健康特餐'")

    def test_contains_single_quote(self):
        self.assertEqual(xpath_literal("it's"), '"it\'s"')

    def test_contains_double_quote(self):
        self.assertEqual(xpath_literal('say "hi"'), "'say \"hi\"'")

    def test_contains_both_quotes(self):
        self.assertEqual(xpath_literal("it's \"x\""), "concat('it', \"'\", 's \"x\"')")


class ConfigTest(unittest.TestCase):
    def test_example_config_is_valid(self):
        cfg = Config.load(REPO / "config.example.yaml")
        self.assertEqual(cfg.get("order.item_full"), "12FIT - 特餐_七味蒜香雞胸(B)")
        self.assertIn("臺北文創大樓", cfg.list_of_str("order.store"))

    def test_missing_key_rejected(self):
        with self.assertRaises(ConfigError):
            Config({"calendar": {"timezone": "Asia/Taipei"}})

    def test_list_of_str_accepts_bare_string(self):
        cfg = Config.load(REPO / "config.example.yaml")
        cfg._data["order"]["category"] = "健康特餐"
        self.assertEqual(cfg.list_of_str("order.category"), ["健康特餐"])


class CalendarTest(unittest.TestCase):
    KEYWORDS = ["居家", "WFH"]

    @mock.patch("lunch_bot.calendar_check.requests.get", side_effect=fake_get)
    def test_recurring_home_day_detected(self, _):
        # 2026-08-20 是週四，命中 BYDAY=TH 的重複活動
        v = check_today("http://x/cal.ics", self.KEYWORDS, day=dt.date(2026, 8, 20))
        self.assertTrue(v.checked)
        self.assertTrue(v.is_home)
        self.assertEqual(v.matched, ["居家辦公"])

    @mock.patch("lunch_bot.calendar_check.requests.get", side_effect=fake_get)
    def test_office_day_not_home(self, _):
        # 2026-08-19 是週三，只有團隊週會
        v = check_today("http://x/cal.ics", self.KEYWORDS, day=dt.date(2026, 8, 19))
        self.assertTrue(v.checked)
        self.assertFalse(v.is_home)
        self.assertEqual(v.all_titles, ["團隊週會"])

    def test_missing_url_is_not_checked(self):
        v = check_today("", self.KEYWORDS)
        self.assertFalse(v.checked)
        self.assertFalse(v.is_home)

    @mock.patch("lunch_bot.calendar_check.requests.get", side_effect=OSError("boom"))
    def test_network_error_is_not_checked(self, _):
        v = check_today("http://x/cal.ics", self.KEYWORDS)
        self.assertFalse(v.checked)
        self.assertFalse(v.is_home)
        self.assertIn("boom", v.error)


class FlowLogicTest(unittest.TestCase):
    def _flow(self, texts: list[str], ignore: bool = False) -> LineOrderFlow:
        cfg = Config.load(REPO / "config.example.yaml")
        return LineOrderFlow(
            FakeScreen(texts), cfg, log=lambda _m: None, ignore_availability=ignore
        )

    def test_tile_center_top_left_of_3x4_grid(self):
        flow = self._flow([])
        x, y = flow._tile_center("rich_menu.order_lunch")
        self.assertAlmostEqual(x, 0.125)                     # (1-0.5)/4
        self.assertAlmostEqual(y, 0.608 + (0.927 - 0.608) / 6)

    def test_available_page_passes(self):
        self._flow(["我要點餐", "健康特餐"])._assert_available("測試頁")

    def test_unavailable_page_aborts(self):
        flow = self._flow(["作燴 - 臺北文創大樓", "暫不供應"])
        with self.assertRaises(OrderAborted) as ctx:
            flow._assert_available("店家資訊頁")
        self.assertIn("暫不供應", str(ctx.exception))

    def test_closed_ordering_aborts(self):
        flow = self._flow(["健康特餐", "暫不開放點餐"])
        with self.assertRaises(OrderAborted):
            flow._assert_available("點餐頁")

    def test_ignore_flag_allows_continue(self):
        flow = self._flow(["暫不供應"], ignore=True)
        flow._assert_available("店家資訊頁")  # 不應拋錯


if __name__ == "__main__":
    unittest.main(verbosity=2)
