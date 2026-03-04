# 로그 분석 스킬

seosoyoung/soulstream 런타임 로그를 체계적으로 분석하는 스킬.

"로그 확인", "로그 검색", "에러 로그", "봇 로그", "워치독 로그", "봇 재시작 언제", "이 스레드 관련 로그", "장애 원인", "로그 분석", "MCP 로그" 같은 요청 시 사용.
Do NOT use for: 코드 수정, 설정 변경, 프로세스 재시작 등 로그 조회 외의 작업.

## 도구 경로

```
.tools/log-analyzer/main.py
```

## 워크플로우

### 1. 이슈 발생 시 — thread_ts 기반 상관관계

슬랙 스레드에서 문제가 보고되면, 해당 스레드 시점 전후의 로그를 수집한다.

```bash
python .tools/log-analyzer/main.py context {thread_ts} --window 5
python .tools/log-analyzer/main.py context {thread_ts} --component bot --level ERROR
```

### 2. 최근 에러 확인

```bash
python .tools/log-analyzer/main.py search --last-hours 1 --level ERROR
python .tools/log-analyzer/main.py search --last-hours 1 --level ERROR --component bot
```

### 3. 재시작 이력 확인

```bash
python .tools/log-analyzer/main.py segments --component watchdog --last 5
python .tools/log-analyzer/main.py segments --component bot --last 5
```

### 4. 파일 목록 확인

```bash
python .tools/log-analyzer/main.py locate
python .tools/log-analyzer/main.py locate --component bot
```

### 5. 특정 패턴/시간 범위 검색

```bash
python .tools/log-analyzer/main.py search --last-hours 24 --pattern "crash|exception|traceback" --level ERROR
python .tools/log-analyzer/main.py search --start "2026-03-04 10:00" --end "2026-03-04 12:00" --component supervisor
```

## 로그 위치

| 런타임 | 경로 |
|--------|------|
| seosoyoung | `D:/soyoung_root/seosoyoung_runtime/logs/` |
| soulstream | `D:/soyoung_root/soulstream_runtime/logs/` |

## 컴포넌트 목록

| 컴포넌트 | 설명 | 로그 형식 |
|----------|------|-----------|
| bot | 슬랙 봇 일별 로그 | `YYYY-MM-DD HH:MM:SS,mmm [LEVEL] msg` |
| bot-error | 슬랙 봇 에러 전용 | 동일 |
| watchdog | 프로세스 감시자 | `[YYYY-MM-DD HH:MM:SS] [watchdog] msg` |
| supervisor | 프로세스 관리자 | `[YYYY-MM-DD HH:MM:SS] supervisor: [LEVEL] msg` |
| soulstream-server | 소울스트림 서버 | `YYYY-MM-DD HH:MM:SS - name - LEVEL - msg` |
| mcp-* | MCP 서버 로그 | Fallback 파서 |
| cli-stderr | Claude CLI stderr | Fallback 파서 |

## 주의사항

- `bot-error.log`은 600MB 이상일 수 있음. 반드시 `--last-hours`나 `--start/--end`로 시간 범위를 지정할 것.
- 바이너리 서치는 10MB 이상 파일에서 자동 적용됨.
- 세션 경계는 `bot`, `watchdog`, `supervisor`, `soulstream-server`만 지원.
