"""Claude 5시간 사용량 모니터링 팝업.

Windows 화면에 항상 고정되는 작은 직사각형 팝업으로 Claude Code의
5시간 롤링 사용량(%)을 표시한다.

- 1차 소스: Anthropic OAuth usage 엔드포인트(정확값).
- 폴백: 로컬 세션 JSONL 기반 토큰 추정.

의존성 없음(stdlib만): tkinter, urllib, json.
"""

__version__ = "0.1.0"
