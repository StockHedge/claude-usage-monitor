"""라이브 정확값 조회: ``GET https://api.anthropic.com/api/oauth/usage``.

주의:
- ``User-Agent: claude-code/<version>`` 가 없으면 공격적으로 429 버킷에 걸린다(필수).
- 이 엔드포인트는 자주 호출하면 지속 429를 반환한다 → 호출 측에서 백오프한다.
- 응답 스키마가 완전 문서화돼 있지 않아, 헤더 우선 + 본문 보조로 관대하게 파싱한다.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .util import parse_ts

log = logging.getLogger(__name__)

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"


@dataclass
class LiveResult:
    status: str  # ok | rate_limited | auth_error | error
    percent: "float | None" = None
    resets_at: "datetime | None" = None
    raw_headers: dict = field(default_factory=dict)
    raw_body: str = ""
    error: "str | None" = None


def _lower_headers(headers) -> dict:
    return {(k or "").lower(): v for k, v in headers.items()}


def _num(value) -> "float | None":
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_live(body_text: str) -> "tuple[float | None, datetime | None]":
    """usage 응답 본문에서 5시간 세션 사용률(%)과 리셋 시각을 추출.

    실측 스키마(2026-07)::

        {"five_hour": {"utilization": 70.0, "resets_at": "..."},
         "seven_day": {...},
         "limits": [{"kind": "session", "group": "session", "percent": 70,
                     "resets_at": "...", "is_active": true}, ...]}

    utilization/percent 는 이미 퍼센트(0..100) 단위다(분수 아님).
    """
    if not body_text:
        return None, None
    try:
        body = json.loads(body_text)
    except ValueError:
        return None, None
    if not isinstance(body, dict):
        return None, None

    percent = None
    resets_at = None

    five = body.get("five_hour")
    if isinstance(five, dict):
        percent = _num(five.get("utilization"))
        resets_at = parse_ts(str(five.get("resets_at") or ""))

    # 보조: five_hour가 없으면 limits 배열의 session(5시간) 엔트리 사용
    if percent is None:
        for lim in body.get("limits") or []:
            if not isinstance(lim, dict):
                continue
            if lim.get("group") == "session" or lim.get("kind") == "session":
                percent = _num(lim.get("percent"))
                resets_at = parse_ts(str(lim.get("resets_at") or ""))
                break

    if percent is not None:
        percent = round(max(0.0, min(100.0, percent)), 1)
    return percent, resets_at


def fetch_live(access_token: str, ua_version: str, timeout: int = 10) -> LiveResult:
    """usage 엔드포인트를 1회 조회한다. 예외는 status로 표현(예외 전파 없음)."""
    req = urllib.request.Request(USAGE_URL, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("anthropic-beta", OAUTH_BETA)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", f"claude-code/{ua_version}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = _lower_headers(resp.headers)
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        headers = _lower_headers(exc.headers or {})
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except (OSError, ValueError):
            body = ""
        if exc.code == 429:
            return LiveResult("rate_limited", raw_headers=headers, raw_body=body, error="429")
        if exc.code in (401, 403):
            return LiveResult("auth_error", raw_headers=headers, raw_body=body, error=str(exc.code))
        return LiveResult("error", raw_headers=headers, raw_body=body, error=f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return LiveResult("error", error=str(exc))

    percent, resets_at = parse_live(body)
    return LiveResult("ok", percent=percent, resets_at=resets_at, raw_headers=headers, raw_body=body)
