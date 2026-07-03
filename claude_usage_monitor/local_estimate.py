"""폴백: 로컬 세션 JSONL로 활성 5시간 블록의 billable 토큰을 추정.

라이브 조회가 불가(429/만료/네트워크)할 때만 쓰인다. 값은 근사치이며 UI에서 '~'로 표시된다.

5시간 블록 산정은 ccusage 방식을 따른다:
- 이벤트를 시각순 정렬.
- 블록 시작은 첫 이벤트의 '시(hour) 내림'.
- 직전 이벤트와 5시간 초과 공백이거나 블록 시작 후 5시간 경과하면 새 블록 시작.
- now를 포함하고 마지막 활동이 5시간 이내인 블록이 '활성' 블록.

토큰은 billable = input + output + cache_creation 로 계산(cache_read 제외).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .util import iter_recent_jsonl, parse_ts

log = logging.getLogger(__name__)

BLOCK_HOURS = 5


@dataclass
class EstimateResult:
    percent: "float | None"
    block_tokens: int
    ceiling: int
    active: bool
    block_end: "datetime | None"


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _billable(usage: dict) -> int:
    return (
        int(usage.get("input_tokens", 0) or 0)
        + int(usage.get("output_tokens", 0) or 0)
        + int(usage.get("cache_creation_input_tokens", 0) or 0)
    )


def collect_events(max_age_hours: float = 6.0) -> "list[tuple[datetime, int]]":
    """최근 파일에서 (timestamp, billable_tokens) 이벤트를 수집(시각순 정렬)."""
    events: "list[tuple[datetime, int]]" = []
    for path in iter_recent_jsonl(max_age_hours):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if obj.get("type") != "assistant":
                        continue
                    message = obj.get("message") or {}
                    usage = message.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    ts = parse_ts(obj.get("timestamp", ""))
                    if ts is None:
                        continue
                    events.append((ts, _billable(usage)))
        except OSError:
            continue
    events.sort(key=lambda item: item[0])
    return events


def active_block_tokens(
    events: "list[tuple[datetime, int]]", now: datetime
) -> "tuple[int, datetime | None, bool]":
    """활성 5시간 블록의 토큰 합, 블록 종료시각, 활성 여부."""
    if not events:
        return 0, None, False

    span = timedelta(hours=BLOCK_HOURS)
    block_start: "datetime | None" = None
    last_dt: "datetime | None" = None
    tokens = 0
    for dt, tok in events:
        if block_start is None or (dt - block_start) >= span or (dt - last_dt) >= span:
            block_start = _floor_hour(dt)
            tokens = 0
        tokens += tok
        last_dt = dt

    block_end = block_start + span
    active = now < block_end and (now - last_dt) < span
    return (tokens if active else 0), block_end, active


def estimate(ceiling_tokens: int, now: "datetime | None" = None) -> EstimateResult:
    now = now or datetime.now(timezone.utc)
    events = collect_events()
    tokens, block_end, active = active_block_tokens(events, now)
    percent = None
    if ceiling_tokens > 0:
        percent = round(min(100.0, tokens / ceiling_tokens * 100), 1)
    return EstimateResult(percent, tokens, ceiling_tokens, active, block_end)


def current_block_tokens(now: "datetime | None" = None) -> int:
    """자기보정용: 현재 활성 5시간 블록의 billable 토큰 합(비활성이면 0)."""
    now = now or datetime.now(timezone.utc)
    tokens, _, _ = active_block_tokens(collect_events(), now)
    return tokens
