# presentation/execution.py

> 경로: `seosoyoung/slackbot/presentation/execution.py`

## 개요

실행 오케스트레이션 헬퍼

placeholder 게시 → 콜백 빌드 → executor 실행 → cleanup 패턴과
on_compact 래핑 보일러플레이트를 캡슐화합니다.

## 함수

### `run_with_event_callbacks(pctx, executor_fn, executor_kwargs)`
- 위치: 줄 20
- 설명: placeholder 게시 → 콜백 빌드 → executor 실행 → cleanup 패턴을 캡슐화

Args:
    pctx: 프레젠테이션 컨텍스트
    executor_fn: run_claude_in_session 또는 SoulstreamBackendImpl._executor
    executor_kwargs: executor에 전달할 키워드 인자 (prompt, thread_ts 등).
        on_compact와 세분화 이벤트 콜백(on_thinking 등)은 이 헬퍼가 주입합니다.
        on_progress 등 다른 executor 파라미터는 executor_kwargs에 포함할 수 있습니다.
    mode: "clean" (일반 채널, 완료 후 삭제) 또는 "keep" (DM, 유지)
    on_compact_override: 외부에서 제공된 on_compact — None이면 event_cbs 기본값 사용
    on_compact_wrapper: on_compact를 래핑하는 함수 (예: 메모리 플래그 래핑).
        override와 함께 사용 시, override된 콜백에 wrapper가 적용됩니다.

Returns:
    build_event_callbacks가 반환한 event_cbs dict

### `wrap_on_compact_with_memory(on_compact, pm, thread_ts)`
- 위치: 줄 81
- 설명: on_compact 콜백에 MemoryPlugin compact 플래그를 래핑

MemoryPlugin이 없으면 원본 콜백을 그대로 반환합니다.

Args:
    on_compact: 원본 on_compact 콜백
    pm: PluginManager 인스턴스 (None 허용)
    thread_ts: 스레드 타임스탬프

Returns:
    래핑된 on_compact 콜백 (memory 플러그인이 없으면 원본 그대로)

## 내부 의존성

- `seosoyoung.slackbot.presentation.node_map.SlackNodeMap`
- `seosoyoung.slackbot.presentation.progress.build_event_callbacks`
- `seosoyoung.slackbot.presentation.progress.post_initial_placeholder`
- `seosoyoung.slackbot.presentation.types.PresentationContext`
