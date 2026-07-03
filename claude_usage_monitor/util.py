"""공용 경로/파서 유틸."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def claude_home() -> Path:
    return Path.home() / ".claude"


def projects_dir() -> Path:
    return claude_home() / "projects"


def parse_ts(value: str) -> "datetime | None":
    """ISO8601(예: '2026-07-03T07:03:11.926Z')을 aware datetime으로."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def iter_recent_jsonl(max_age_hours: float):
    """projects 하위 *.jsonl 중 mtime이 최근 max_age_hours 이내인 파일 경로."""
    base = projects_dir()
    if not base.exists():
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).timestamp()
    for path in base.rglob("*.jsonl"):
        try:
            if path.stat().st_mtime >= cutoff:
                yield path
        except OSError:
            continue


def newest_jsonl() -> "Path | None":
    """mtime 기준 가장 최근 *.jsonl."""
    base = projects_dir()
    if not base.exists():
        return None
    newest = None
    newest_mtime = -1.0
    for path in base.rglob("*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > newest_mtime:
            newest_mtime = mtime
            newest = path
    return newest


def _tail_text(path: Path, nbytes: int = 8192) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - nbytes))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def detect_claude_version(default: str) -> str:
    """가장 최근 세션 로그의 version 필드에서 Claude Code 버전을 추정."""
    path = newest_jsonl()
    if path is None:
        return default
    for line in reversed(_tail_text(path).splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        version = obj.get("version")
        if version:
            return str(version)
    return default
