"""로깅 설정. GUI(pythonw, 콘솔 없음)는 파일로만, CLI는 콘솔도 함께."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import CONFIG_DIR

LOG_PATH = CONFIG_DIR / "monitor.log"


def setup_logging(console: bool = False, level: int = logging.INFO) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=2, encoding="utf-8")
    ]
    if console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
