# log-analyzer

seosoyoung/soulstream 런타임 로그를 체계적으로 탐색하는 CLI 도구.

## 사용법

```bash
python .tools/log-analyzer/main.py <command> [options]
```

## 서브커맨드

### locate — 로그 파일 목록

전체 로그 파일의 이름, 컴포넌트, 런타임, 크기, 수정시각을 표시한다.

```bash
# 전체 목록
python .tools/log-analyzer/main.py locate

# 특정 컴포넌트만
python .tools/log-analyzer/main.py locate --component bot

# 특정 런타임만
python .tools/log-analyzer/main.py locate --runtime soulstream
```

### segments — 세션 경계 탐색

봇/워치독/수퍼바이저 등의 기동/종료 세션을 식별한다.

```bash
# 워치독 최근 5세션
python .tools/log-analyzer/main.py segments --component watchdog --last 5

# 봇 전체 세션
python .tools/log-analyzer/main.py segments --component bot
```

지원 컴포넌트: `bot`, `watchdog`, `supervisor`, `soulstream-server`

### search — 시간/레벨/패턴 기반 검색

```bash
# 최근 1시간 ERROR 이상
python .tools/log-analyzer/main.py search --last-hours 1 --level ERROR

# 특정 시간 범위 + 패턴
python .tools/log-analyzer/main.py search --start "2026-03-04 10:00" --end "2026-03-04 12:00" --pattern "connection"

# 봇 에러 최근 10건
python .tools/log-analyzer/main.py search --last-hours 24 --level ERROR --component bot --tail 10
```

대용량 파일(10MB+)은 바이너리 서치로 시작 위치를 O(log n)에 특정하여 빠르게 검색한다.

### context — 슬랙 thread_ts 상관관계

슬랙 스레드 시점 전후의 로그를 수집한다.

```bash
# thread_ts 전후 5분
python .tools/log-analyzer/main.py context 1772584610.882089

# 윈도우 조정
python .tools/log-analyzer/main.py context 1772584610.882089 --window 10

# 특정 컴포넌트만
python .tools/log-analyzer/main.py context 1772584610.882089 --component bot --level ERROR
```

## 아키텍처

```
main.py        CLI 진입점 (argparse 서브커맨드 4개)
parsers.py     로그 형식 파서 5종 (watchdog/supervisor/bot/soulstream/fallback)
scanner.py     파일 탐색 및 메타데이터
searcher.py    시간 범위 검색 (바이너리 서치)
segments.py    세션 경계 탐색
context.py     슬랙 thread_ts 상관관계
formatter.py   출력 포맷팅
test_main.py   유닛 테스트 38건
```

## 의존성

stdlib만 사용. 외부 패키지 설치 불필요.

## 테스트

```bash
python -m pytest .tools/log-analyzer/test_main.py -v
```
