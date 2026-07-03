"""설정 로드/저장. 사용자 홈의 ``~/.claude_usage_monitor/config.json`` 에 영속화."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".claude_usage_monitor"
CONFIG_PATH = CONFIG_DIR / "config.json"

# 폴백(로컬 추정)의 100% 기준이 되는 5시간 billable 토큰 상한(대략치).
# billable = input + output + cache_creation (cache_read 제외 — 값이 커서 왜곡).
# 정확한 플랜 한도는 비공개/변동이라 사용자 보정을 전제로 한 근사치다.
PLAN_CEILINGS = {
    "pro": 300_000,
    "max5x": 1_500_000,
    "max20x": 6_000_000,
}


@dataclass
class Config:
    # 폴링/네트워크
    poll_interval_sec: int = 60
    request_timeout_sec: int = 10
    backoff_start_sec: int = 60
    backoff_max_sec: int = 600
    stale_after_sec: int = 900  # 라이브 캐시가 이보다 오래되면 폴백으로 전환
    calibrate_interval_sec: int = 300  # 라이브 성공 시 폴백 상한 자기보정 최소 간격

    # 폴백 상한
    plan: str = "max5x"
    fallback_ceiling_tokens: int = PLAN_CEILINGS["max5x"]

    # 색상 임계값(%)
    warn_percent: float = 50.0
    danger_percent: float = 80.0

    # 외형 (font_size = 큰 퍼센트 숫자 크기)
    opacity: float = 0.94
    font_family: str = "Malgun Gothic"   # 한글 라벨용
    num_font_family: str = "Consolas"    # 퍼센트 숫자(터미널 느낌)
    font_size: int = 15
    corner_radius: int = 12

    # 색상 (따뜻한 다크 + Claude 테라코타)
    color_bg: str = "#23201c"
    color_border: str = "#3a352e"
    color_track: str = "#37322b"
    color_normal: str = "#6fbf73"
    color_warn: str = "#e0a33b"
    color_danger: str = "#e5544b"
    color_dim: str = "#b8ae9e"

    # Claude 캐릭터 아이콘
    show_icon: bool = True
    icon_color: str = "#d97757"
    icon_size: int = 26

    # 음성 알림 (25%마다 한국어 TTS)
    voice_enabled: bool = True

    # 라이브 요청 User-Agent 버전(감지 실패 시 폴백)
    ua_version_fallback: str = "2.1.197"

    # 창 위치(드래그로 저장)
    window_x: "int | None" = None
    window_y: "int | None" = None

    def apply_plan(self, plan: str) -> None:
        """요금제 선택 → 폴백 상한 프리셋 적용.

        라이브가 살아있으면 이후 자기보정(provider)이 상한을 실제값 기준으로 정밀화한다.
        """
        self.plan = plan
        if plan in PLAN_CEILINGS:
            self.fallback_ceiling_tokens = PLAN_CEILINGS[plan]


def load() -> Config:
    """설정 파일을 읽어 Config를 만든다. 없거나 깨지면 기본값."""
    cfg = Config()
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for key, value in data.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)
        except (OSError, ValueError) as exc:
            log.warning("설정 로드 실패, 기본값 사용: %s", exc)
    return cfg


def save(cfg: Config) -> None:
    """Config를 설정 파일에 기록한다."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("설정 저장 실패: %s", exc)
