"""檢查 Google 日曆今天是否有包含特定關鍵字的活動。

首次使用前，需要先在 Google Cloud Console 建立 OAuth 用戶端密鑰並啟用
Calendar API，下載後存成 config/google_credentials.json（詳見
README.md）。第一次執行時會開啟瀏覽器要求登入並授權，授權結果會存成
config/google_token.json 供之後重複使用。
"""

import datetime as dt
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_PATH = BASE_DIR / "config" / "google_credentials.json"
TOKEN_PATH = BASE_DIR / "config" / "google_token.json"


def get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise SystemExit(
                    f"找不到 Google OAuth 憑證檔: {CREDENTIALS_PATH}\n"
                    "請依照 README.md 的「Google 日曆設定」步驟，從 Google Cloud "
                    "Console 下載 OAuth 用戶端密鑰，存成 config/google_credentials.json。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds


def has_keyword_event_today(keyword: str, calendar_id: str = "primary") -> bool:
    """檢查今天（依本機時區）是否有任何活動標題包含 keyword。"""
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    today = dt.date.today()
    local_tz = dt.datetime.now().astimezone().tzinfo
    time_min = dt.datetime.combine(today, dt.time.min, tzinfo=local_tz).isoformat()
    time_max = dt.datetime.combine(today, dt.time.max, tzinfo=local_tz).isoformat()

    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
    return any(keyword in event.get("summary", "") for event in events)
