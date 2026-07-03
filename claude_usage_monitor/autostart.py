"""Windows 로그인 시 자동 시작 등록/해제.

시작프로그램(Startup) 폴더에 pythonw를 숨김 실행하는 .vbs 런처를 배치한다.
경로에 한글 사용자명이 포함될 수 있으므로 .vbs는 UTF-16(LE, BOM)으로 기록한다
(Windows Script Host가 BOM 없는 파일을 ANSI/cp949로 읽어 한글 경로가 깨지는 것을 방지).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ClaudeUsageMonitor"


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _launcher_path() -> Path:
    return _startup_dir() / f"{APP_NAME}.vbs"


def _pythonw() -> Path:
    """현재 인터프리터와 같은 위치의 pythonw.exe(콘솔 창 없음)."""
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def _run_target() -> Path:
    """리포 루트의 run.pyw (이 패키지의 부모 디렉터리)."""
    return Path(__file__).resolve().parent.parent / "run.pyw"


def install() -> Path:
    startup = _startup_dir()
    startup.mkdir(parents=True, exist_ok=True)
    pythonw = _pythonw()
    target = _run_target()
    vbs = (
        'Set WshShell = CreateObject("WScript.Shell")\r\n'
        f'WshShell.Run """{pythonw}"" ""{target}""", 0, False\r\n'
    )
    path = _launcher_path()
    path.write_text(vbs, encoding="utf-16")  # BOM 포함 UTF-16 → WSH가 한글 경로 정상 처리
    return path


def uninstall() -> bool:
    path = _launcher_path()
    if path.exists():
        path.unlink()
        return True
    return False


def status() -> str:
    path = _launcher_path()
    if path.exists():
        return f"자동시작 등록됨: {path}\n--- 내용 ---\n{path.read_text(encoding='utf-16')}"
    return f"자동시작 미등록 ({path} 없음)"
