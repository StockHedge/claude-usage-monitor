"""CLI 엔트리.

  python -m claude_usage_monitor                 # GUI 팝업 실행(기본)
  python -m claude_usage_monitor --once          # 라이브 1회 조회(디버그/검증)
  python -m claude_usage_monitor --estimate      # 폴백 추정 1회
  python -m claude_usage_monitor --install-autostart
  python -m claude_usage_monitor --uninstall-autostart
  python -m claude_usage_monitor --autostart-status
"""
from __future__ import annotations

import argparse
import sys


def _reconfig_stdout() -> None:
    """Windows 콘솔(cp949)에서 한글 출력/로그 깨짐 방지."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def cmd_once() -> int:
    from .config import load
    from .credentials import read_credentials
    from .logsetup import setup_logging
    from .usage_api import fetch_live
    from .util import detect_claude_version

    setup_logging(console=True)
    cfg = load()
    creds = read_credentials()
    if creds is None:
        print("자격증명 없음 — 라이브 조회 불가")
        return 1

    print(f"토큰 만료여부: {creds.is_expired()}   구독: {creds.subscription_type}")
    ua = detect_claude_version(cfg.ua_version_fallback)
    print(f"User-Agent: claude-code/{ua}")

    res = fetch_live(creds.access_token, ua, cfg.request_timeout_sec)
    print(f"status={res.status}  percent={res.percent}  resets_at={res.resets_at}  error={res.error}")
    print("--- anthropic/ratelimit 헤더 ---")
    for key, value in sorted(res.raw_headers.items()):
        if "ratelimit" in key or "anthropic" in key:
            print(f"  {key}: {value}")
    print("--- body (앞 1200자) ---")
    print(res.raw_body[:1200])
    return 0


def cmd_estimate() -> int:
    from .config import load
    from .local_estimate import estimate
    from .logsetup import setup_logging

    setup_logging(console=True)
    cfg = load()
    est = estimate(cfg.fallback_ceiling_tokens)
    print(
        f"active={est.active}  block_tokens={est.block_tokens}  "
        f"ceiling={est.ceiling}  percent={est.percent}  block_end={est.block_end}"
    )
    return 0


def cmd_calibrate() -> int:
    from .config import load
    from .logsetup import setup_logging
    from .provider import UsageProvider

    setup_logging(console=True)
    cfg = load()
    provider = UsageProvider(cfg)
    snap = provider.get()  # 라이브 성공 시 폴백 상한 자기보정 수행
    print(f"라이브: source={snap.source}  percent={snap.percent}")
    print(f"보정된 폴백 상한: {cfg.fallback_ceiling_tokens:,} tokens")
    if snap.source not in ("live", "live-cached"):
        print("주의: 라이브 조회 실패로 보정되지 않았을 수 있음(로그 확인).")
    return 0


def cmd_setup() -> int:
    from .setup import run_setup

    run_setup()
    return 0


def cmd_autostart(action: str) -> int:
    from . import autostart

    if action == "install":
        print(f"설치됨: {autostart.install()}")
    elif action == "uninstall":
        print("제거됨" if autostart.uninstall() else "런처 없음")
    else:
        print(autostart.status())
    return 0


def main(argv=None) -> int:
    _reconfig_stdout()
    parser = argparse.ArgumentParser(prog="claude_usage_monitor")
    parser.add_argument("--once", action="store_true", help="라이브 1회 조회(디버그)")
    parser.add_argument("--estimate", action="store_true", help="폴백 추정 1회")
    parser.add_argument("--calibrate", action="store_true", help="라이브 기준으로 폴백 상한 보정")
    parser.add_argument("--setup", action="store_true", help="최초 실행 설정(요금제/자동시작)")
    parser.add_argument("--install-autostart", action="store_true", help="자동시작 등록")
    parser.add_argument("--uninstall-autostart", action="store_true", help="자동시작 해제")
    parser.add_argument("--autostart-status", action="store_true", help="자동시작 상태")
    args = parser.parse_args(argv)

    if args.once:
        return cmd_once()
    if args.estimate:
        return cmd_estimate()
    if args.calibrate:
        return cmd_calibrate()
    if args.setup:
        return cmd_setup()
    if args.install_autostart:
        return cmd_autostart("install")
    if args.uninstall_autostart:
        return cmd_autostart("uninstall")
    if args.autostart_status:
        return cmd_autostart("status")

    from .ui import main as ui_main

    ui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
