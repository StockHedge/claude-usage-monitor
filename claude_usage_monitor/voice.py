"""한국어 음성 알림 (Windows SAPI).

25% 구간을 넘길 때 "N퍼센트 소진했습니다"를 읽어준다. 외부 라이브러리 없이,
한국어 음성이 깨지지 않도록 임시 VBScript를 **UTF-16(BOM)** 으로 써서 wscript로 실행한다.
한국어 TTS 음성(Microsoft Heami 등)이 있으면 자동 선택하고, 없으면 기본 음성을 쓴다.
"""
from __future__ import annotations

import logging
import subprocess

from .config import CONFIG_DIR

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000
_VBS_PATH = CONFIG_DIR / "_tts.vbs"

_VBS_TEMPLATE = (
    'Set v = CreateObject("SAPI.SpVoice")\r\n'
    'On Error Resume Next\r\n'
    'For Each t In v.GetVoices\r\n'
    '  d = t.GetDescription()\r\n'
    '  If InStr(d, "Korean") > 0 Or InStr(d, "Heami") > 0 Or InStr(d, "한국") > 0 Then\r\n'
    '    Set v.Voice = t\r\n'
    '  End If\r\n'
    'Next\r\n'
    'On Error Goto 0\r\n'
    'v.Speak {literal}\r\n'
)


def speak(text: str) -> None:
    """텍스트를 한국어 TTS로 읽는다(비차단, 실패해도 조용히 무시)."""
    try:
        literal = '"' + text.replace('"', '""') + '"'
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # WSH가 한글을 올바로 읽도록 UTF-16(BOM) 로 기록
        _VBS_PATH.write_text(_VBS_TEMPLATE.format(literal=literal), encoding="utf-16")
        subprocess.Popen(["wscript.exe", str(_VBS_PATH)], creationflags=CREATE_NO_WINDOW)
    except Exception:
        log.exception("음성 재생 실패")
