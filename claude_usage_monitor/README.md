# claude_usage_monitor

Claude Code의 **5시간 롤링 사용량(%)** 을 화면 우상단에 항상 고정되는 작은 팝업으로 표시하는
개인용 Windows 도구. 의존성 없음(Python stdlib: tkinter, urllib, json).

```
5시간 사용량 : 72%
```

## 데이터 소스

1. **라이브 정확값 (1차)** — `~/.claude/.credentials.json`의 OAuth 토큰으로
   `GET https://api.anthropic.com/api/oauth/usage` 를 조회. 응답 본문의
   `five_hour.utilization`(%)가 Claude Code `/usage` 표시값과 동일하다.
   - 필수 헤더: `Authorization: Bearer …`, `anthropic-beta: oauth-2025-04-20`,
     `User-Agent: claude-code/<version>` (UA 누락 시 공격적 429).
   - 자격증명은 **읽기 전용**으로만 접근한다. 토큰을 회전/덮어쓰지 않는다.
2. **로컬 추정 (폴백)** — 라이브가 429/만료/네트워크 오류로 막히면,
   `~/.claude/projects/**/*.jsonl` 세션 로그에서 활성 5시간 블록의 billable 토큰
   (input+output+cache_creation)을 합산해 상한 대비 %로 추정. UI에 `~`로 표시.
3. **자기보정** — 라이브가 살아있을 때마다 `(로컬 블록 토큰 ÷ 라이브%)`로 폴백 상한을
   학습(EMA)해 `~/.claude_usage_monitor/config.json`에 저장. 폴백이 현실을 추종하게 된다.

## 실행

```powershell
# GUI 팝업 (콘솔 창 없이)
pythonw run.pyw
# 또는
python -m claude_usage_monitor

# 진단/검증
python -m claude_usage_monitor --once        # 라이브 1회 조회(원문 덤프)
python -m claude_usage_monitor --estimate     # 폴백 추정 1회
python -m claude_usage_monitor --calibrate    # 라이브 기준으로 폴백 상한 보정

# 자동 시작 (Windows 로그인 시)
python -m claude_usage_monitor --install-autostart
python -m claude_usage_monitor --autostart-status
python -m claude_usage_monitor --uninstall-autostart
```

## 조작

- **드래그**: 좌클릭으로 팝업 이동(위치는 자동 저장·복원).
- **우클릭**: 지금 새로고침 / 위치 초기화 / 종료.
- 색상: <50% 녹색, 50–80% 주황, ≥80% 빨강. 폴백 추정은 `~`, 오래된 캐시는 뒤에 ` ·`.

## 설정

`~/.claude_usage_monitor/config.json` (첫 실행 시 생성). 주요 항목:
`poll_interval_sec`(기본 60), `warn_percent`(50), `danger_percent`(80),
`opacity`(0.92), `font_family`("Malgun Gothic"), `fallback_ceiling_tokens`(자기보정됨).

## 한계 / 유의

- `/api/oauth/usage`는 비공식·미문서 엔드포인트다. 자주 폴링하면 지속 429가 나므로
  기본 60초 + 지수 백오프(60→120→300→600초)로 젠틀하게 조회한다.
- 토큰은 ~60분마다 만료된다. Claude Code 실행 중이면 자동 갱신된 토큰을 파일에서 다시 읽는다.
  만료 + Claude Code 미실행이면 폴백(추정)으로 저하된다.
- always-on-top(tkinter `-topmost`)은 일반 창 위에는 안정적으로 고정되지만, 다른 topmost
  창이나 독점 전체화면 앱 위에는 밀릴 수 있다.
- 구독 OAuth 토큰으로 Anthropic 엔드포인트를 직접 호출하는 것은 회색지대다.
  개인용 읽기 전용 모니터링 목적으로만 사용한다.
