"""``~/.claude/.credentials.json`` 읽기 전용 파서.

보안 원칙(secrets-oauth-ops): 남의 자격증명은 읽기 전용으로만 접근한다.
토큰을 절대 회전(refresh)하거나 파일에 다시 쓰지 않는다. 만료 시 폴백으로 전환한다.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from .util import claude_home

log = logging.getLogger(__name__)

CRED_PATH = claude_home() / ".credentials.json"


@dataclass
class Credentials:
    access_token: str
    expires_at_ms: "int | None"
    subscription_type: "str | None"

    def is_expired(self, skew_sec: int = 60) -> bool:
        """만료 정보가 있으면 skew를 두고 만료 여부 판단. 정보 없으면 일단 시도."""
        if not self.expires_at_ms:
            return False
        now_ms = time.time() * 1000
        return now_ms >= (self.expires_at_ms - skew_sec * 1000)


def read_credentials() -> "Credentials | None":
    """자격증명 파일을 읽어 Credentials를 반환. 없거나 깨지면 None."""
    if not CRED_PATH.exists():
        log.info("자격증명 파일 없음: %s", CRED_PATH)
        return None
    try:
        data = json.loads(CRED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("자격증명 파싱 실패: %s", exc)
        return None

    oauth = data.get("claudeAiOauth") or data.get("claudeAiOAuth") or {}
    token = oauth.get("accessToken") or oauth.get("access_token")
    if not token:
        log.info("accessToken 필드를 찾지 못함")
        return None

    return Credentials(
        access_token=token,
        expires_at_ms=oauth.get("expiresAt") or oauth.get("expires_at"),
        subscription_type=oauth.get("subscriptionType") or oauth.get("subscription_type"),
    )
