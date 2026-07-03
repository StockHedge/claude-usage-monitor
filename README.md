# Claude 5시간 사용량 모니터

Windows에서 **항상 맨 앞에 떠 있는 작은 팝업**(다른 창으로 바꿔도 가려지지 않음)으로 Claude Code의
**5시간 롤링 사용량(%)**을 실시간에 가깝게 보여주는 개인용 도구입니다. 팝업은 원하는 위치로 드래그해
둘 수 있고, `/usage`를 매번 열지 않아도 됩니다.

```
▧  5시간 사용량
   72%  ▮▮▮▮▮▮▮▯▯▯
```

> A tiny always-on-top Windows widget that shows your Claude Code 5-hour usage %.
> Reads the same number as `/usage`, with a local estimate fallback. Python stdlib only.

## 요구 사항

- **Windows** + **Python 3.8+** (python.org 설치본이면 tkinter 포함). 설치 시 *Add Python to PATH* 체크 권장.
- 정확값을 보려면 **Claude Code에 로그인**되어 있어야 합니다(구독 OAuth 토큰 사용). 없으면 추정 모드로 동작합니다.
- 외부 라이브러리 설치 불필요(표준 라이브러리만 사용).

## 빠른 시작

1. 이 저장소를 다운로드/클론합니다.
2. **`install.bat` 더블클릭** → 요금제 선택 → *설치하고 시작*.
   - 요금제 선택, Windows 로그인 시 자동 시작 등록, 팝업 실행이 한 번에 진행됩니다.
3. 우상단에 팝업이 뜹니다. 끝.

수동 실행: **`start.bat`** 더블클릭(또는 `run.pyw` 더블클릭). 자동 시작 해제: **`uninstall.bat`**.

## 사용

- **드래그**: 좌클릭으로 팝업 이동(위치 자동 저장·복원).
- **크기 조절**: 오른쪽-아래 모서리를 드래그해 크기(비율)를 조절합니다(최소 0.75배 ~ 최대 2.2배).
- **마우스를 올리면**: 5시간 한도 **리셋 시각**과 남은 시간을 툴팁으로 보여줍니다.
- **음성 알림**: 사용량이 25% 구간(25/50/75/100%)을 넘길 때마다 한국어로
  "N퍼센트 소진했습니다"라고 알려줍니다(Windows SAPI, 설정에서 끌 수 있음).
- **우클릭 메뉴**: 지금 새로고침 / 설정… / 위치 초기화 / 크기 초기화 / 종료.
- **설정 창**에서 즉시 수정: 요금제, 캐릭터 아이콘 표시, 음성 알림, 숫자·아이콘 크기,
  투명도, 주의/위험 임계값, 갱신 주기, 색상(배경·정상·주의·위험·아이콘).
- 색상 규칙: `< 주의%` 정상색, `주의%~위험%` 주의색, `≥ 위험%` 위험색.
  폴백 추정값은 `~72%`, 오래된 캐시는 뒤에 ` ·`로 표시됩니다.

## 어떻게 동작하나

1. **라이브 정확값(1차)** — `~/.claude/.credentials.json`의 OAuth 토큰(읽기 전용)으로
   `GET https://api.anthropic.com/api/oauth/usage`를 조회합니다. 응답의 `five_hour.utilization`이
   Claude Code `/usage` 표시값과 동일합니다. 기본 60초 간격 + 429 지수 백오프로 젠틀하게 폴링합니다.
2. **로컬 추정(폴백)** — 라이브가 막히면(429/토큰 만료) `~/.claude/projects/**/*.jsonl`
   세션 로그로 활성 5시간 블록의 토큰을 합산해 상한 대비 %로 추정하고 `~`로 표시합니다.
3. **자기보정** — 라이브가 살아있을 때 `(로컬 토큰 ÷ 실제 %)`로 폴백 상한을 학습해,
   폴백도 본인 사용 패턴에 맞게 정확해집니다.

## 자동 시작 원리

로그인 시 시작프로그램 폴더의 `ClaudeUsageMonitor.vbs`가 `pythonw run.pyw`를 콘솔 없이 실행합니다.
`install.bat`에서 등록되며, `uninstall.bat`으로 제거됩니다.

## 보안·유의

- 자격증명은 **읽기 전용**으로만 접근하며, 토큰을 회전/저장/전송하지 않습니다.
- `/api/oauth/usage`는 비공식·미문서 엔드포인트입니다. 개인용 읽기 전용 모니터링 목적으로만 사용하세요.
- always-on-top은 일반 창 위에는 안정적이지만, 다른 topmost 창/독점 전체화면 위에는 밀릴 수 있습니다.
- 음성 알림은 Windows SAPI를 쓰며, 한국어 음성(예: Microsoft Heami)이 있으면 자동 선택합니다.

## 설정 파일 / 로그

- 설정: `~/.claude_usage_monitor/config.json`
- 로그: `~/.claude_usage_monitor/monitor.log`

## CLI (고급)

```
python -m claude_usage_monitor            # 팝업 실행
python -m claude_usage_monitor --setup    # 최초 설정 GUI
python -m claude_usage_monitor --once      # 라이브 1회 조회(진단)
python -m claude_usage_monitor --estimate  # 폴백 추정 1회
python -m claude_usage_monitor --calibrate # 폴백 상한 보정
python -m claude_usage_monitor --install-autostart / --uninstall-autostart / --autostart-status
```

## 라이선스

MIT. 자세한 사용법은 [사용설명서.md](사용설명서.md) 참고.
