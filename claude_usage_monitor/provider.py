"""데이터 소스 오케스트레이션.

우선순위:
1. 라이브 정확값(usage 엔드포인트) — 성공 시 캐시.
2. 신선한 라이브 캐시(stale_after_sec 이내).
3. 로컬 추정(폴백).
4. 오래된 라이브 캐시(그것도 없으면 unavailable).

429/인증오류 시 지수 백오프로 재호출을 억제한다.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from .config import Config, save as save_config
from .credentials import read_credentials
from .local_estimate import current_block_tokens, estimate
from .usage_api import fetch_live
from .util import detect_claude_version

log = logging.getLogger(__name__)


@dataclass
class UsageSnapshot:
    percent: "float | None"
    source: str  # live | live-cached | estimate | unavailable
    stale: bool = False
    resets_at: "datetime | None" = None
    detail: str = ""


class UsageProvider:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ua_version: "str | None" = None
        self._last_live_percent: "float | None" = None
        self._last_live_ts = 0.0
        self._last_live_resets: "datetime | None" = None
        self._backoff_until = 0.0
        self._backoff = 0
        self._last_calibrate = 0.0

    def _ua(self) -> str:
        if self._ua_version is None:
            self._ua_version = detect_claude_version(self.cfg.ua_version_fallback)
            log.info("User-Agent 버전: claude-code/%s", self._ua_version)
        return self._ua_version

    def _maybe_calibrate(self, live_percent: float) -> None:
        """라이브 성공 시, (로컬 블록 토큰 / 라이브%)로 폴백 상한을 학습.

        라이브가 죽었을 때 폴백 추정이 현실을 추종하도록 상한을 지속 보정한다.
        낮은 사용률(<10%)은 노이즈가 커서 건너뛴다. EMA로 완만히 수렴.
        """
        if live_percent < 10:
            return
        now = time.time()
        if self._last_calibrate and (now - self._last_calibrate) < self.cfg.calibrate_interval_sec:
            return
        try:
            tokens = current_block_tokens()
        except Exception:
            log.exception("보정용 토큰 계산 실패")
            return
        if tokens <= 0:
            return
        implied = int(tokens / (live_percent / 100.0))
        if self._last_calibrate:
            new_ceiling = int(self.cfg.fallback_ceiling_tokens * 0.7 + implied * 0.3)
        else:
            new_ceiling = implied  # 최초 관측은 그대로 시드
        self._last_calibrate = now
        if new_ceiling > 0 and new_ceiling != self.cfg.fallback_ceiling_tokens:
            self.cfg.fallback_ceiling_tokens = new_ceiling
            save_config(self.cfg)
            log.info(
                "폴백 상한 자기보정 → %d (live=%.1f%%, block=%d)",
                new_ceiling, live_percent, tokens,
            )

    def _bump_backoff(self) -> None:
        self._backoff = min(
            self.cfg.backoff_max_sec,
            (self._backoff * 2) if self._backoff else self.cfg.backoff_start_sec,
        )
        self._backoff_until = time.time() + self._backoff

    def _try_live(self) -> "UsageSnapshot | None":
        now = time.time()
        if now < self._backoff_until:
            return None
        creds = read_credentials()
        if creds is None:
            return None
        if creds.is_expired():
            log.info("토큰 만료 — 라이브 건너뜀(폴백)")
            return None

        res = fetch_live(creds.access_token, self._ua(), self.cfg.request_timeout_sec)

        if res.status == "ok" and res.percent is not None:
            self._backoff = 0
            self._backoff_until = 0
            self._last_live_percent = res.percent
            self._last_live_ts = now
            self._last_live_resets = res.resets_at
            self._maybe_calibrate(res.percent)
            return UsageSnapshot(res.percent, "live", False, res.resets_at)

        if res.status == "ok":
            log.warning(
                "라이브 200이나 %% 파싱 실패. headers=%s body=%.300s",
                sorted(res.raw_headers), res.raw_body,
            )
            return None

        if res.status == "rate_limited":
            self._bump_backoff()
            log.info("429 — %ds 백오프", self._backoff)
            return None

        if res.status == "auth_error":
            log.info("인증 오류 %s — 폴백", res.error)
            self._backoff_until = now + self.cfg.backoff_start_sec
            return None

        log.info("라이브 오류: %s", res.error)
        return None

    def get(self) -> UsageSnapshot:
        live = self._try_live()
        if live is not None:
            return live

        # 신선한 라이브 캐시 우선
        if self._last_live_percent is not None:
            age = time.time() - self._last_live_ts
            if age < self.cfg.stale_after_sec:
                return UsageSnapshot(
                    self._last_live_percent, "live-cached", False,
                    self._last_live_resets, f"{int(age)}s ago",
                )

        # 로컬 추정
        est = estimate(self.cfg.fallback_ceiling_tokens)
        if est.percent is not None:
            return UsageSnapshot(
                est.percent, "estimate", False, est.block_end,
                f"{est.block_tokens}/{est.ceiling} tok",
            )

        # 오래된 라이브 캐시라도
        if self._last_live_percent is not None:
            return UsageSnapshot(
                self._last_live_percent, "live-cached", True,
                self._last_live_resets, "stale",
            )

        return UsageSnapshot(None, "unavailable", detail="데이터 없음")
