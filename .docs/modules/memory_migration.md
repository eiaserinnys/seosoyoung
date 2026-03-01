# memory/migration.py

> 경로: `seosoyoung/slackbot/plugins/memory/migration.py`

## 개요

OM 마크다운 → JSON 마이그레이션

런타임 memory/ 디렉토리의 .md 파일들을 .json으로 일괄 변환합니다.

사용:
    from seosoyoung.slackbot.plugins.memory.migration import migrate_memory_dir
    report = migrate_memory_dir("/path/to/memory", dry_run=True)

## 클래스

### `MigrationReport`
- 위치: 줄 21
- 설명: 마이그레이션 결과 보고서

#### 메서드

- `total_converted(self)` (줄 31): 
- `summary(self)` (줄 34): 

## 함수

### `_backup_md(md_path)`
- 위치: 줄 46
- 설명: 원본 .md를 .md.bak으로 백업합니다.

### `migrate_observations(observations_dir, dry_run)`
- 위치: 줄 53
- 설명: observations/ 디렉토리의 .md 파일을 .json으로 변환합니다.

변환 대상: {thread_ts}.md → {thread_ts}.json
이미 .json이 존재하면 건너뜁니다.

### `migrate_persistent(persistent_dir, dry_run)`
- 위치: 줄 105
- 설명: persistent/recent.md → recent.json 변환.

Returns:
    True: 변환 수행됨, False: 변환 불필요

### `migrate_memory_dir(base_dir, dry_run)`
- 위치: 줄 145
- 설명: memory/ 디렉토리 전체를 마이그레이션합니다.

Args:
    base_dir: memory/ 디렉토리 경로
    dry_run: True면 실제 변환 없이 대상만 출력

Returns:
    MigrationReport

## 내부 의존성

- `seosoyoung.slackbot.plugins.memory.store.parse_md_observations`
- `seosoyoung.slackbot.plugins.memory.store.parse_md_persistent`
