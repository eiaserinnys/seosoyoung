"""OM(Observational Memory) 주입 및 관찰 트리거 로직

agent_runner.py에서 분리된 메모리 주입 전용 모듈.
ClaudeRunner가 이 모듈의 함수를 호출하여 OM 기능을 사용합니다.
"""

import asyncio
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


def prepare_memory_injection(
    thread_ts: str,
    channel: Optional[str],
    session_id: Optional[str],
    prompt: Optional[str],
) -> tuple[Optional[str], str]:
    """OM 메모리 주입을 준비합니다.

    장기 기억, 세션 관찰, 채널 관찰 등을 수집하여
    첫 번째 query 메시지에 프리픽스로 주입할 프롬프트를 생성합니다.

    Args:
        thread_ts: 스레드 타임스탬프
        channel: 채널 ID
        session_id: 세션 ID (None이면 새 세션)
        prompt: 사용자 프롬프트 (앵커 미리보기용)

    Returns:
        (memory_prompt, anchor_ts) 튜플
    """
    if not thread_ts:
        return None, ""

    try:
        from seosoyoung.config import Config
        if not Config.OM_ENABLED:
            return None, ""

        from seosoyoung.memory.context_builder import ContextBuilder, InjectionResult
        from seosoyoung.memory.store import MemoryStore

        store = MemoryStore(Config.get_memory_path())
        is_new_session = session_id is None
        should_inject_session = store.check_and_clear_inject_flag(thread_ts)

        # 채널 관찰: 관찰 대상 채널에서 멘션될 때만 주입
        channel_store = None
        include_channel_obs = False
        if (
            is_new_session
            and Config.CHANNEL_OBSERVER_ENABLED
            and channel
            and channel in Config.CHANNEL_OBSERVER_CHANNELS
        ):
            from seosoyoung.memory.channel_store import ChannelStore
            channel_store = ChannelStore(Config.get_memory_path())
            include_channel_obs = True

        builder = ContextBuilder(store, channel_store=channel_store)
        result: InjectionResult = builder.build_memory_prompt(
            thread_ts,
            max_tokens=Config.OM_MAX_OBSERVATION_TOKENS,
            include_persistent=is_new_session,
            include_session=should_inject_session,
            include_channel_observation=include_channel_obs,
            channel_id=channel,
            include_new_observations=True,
        )

        memory_prompt: Optional[str] = None
        if result.prompt:
            memory_prompt = result.prompt
            logger.info(
                f"OM 주입 준비 완료 (thread={thread_ts}, "
                f"LTM={result.persistent_tokens} tok, "
                f"새관찰={result.new_observation_tokens} tok, "
                f"세션={result.session_tokens} tok, "
                f"채널={result.channel_digest_tokens}+{result.channel_buffer_tokens} tok)"
            )

        # 앵커 ts: 새 세션이면 생성, 기존 세션이면 MemoryRecord에서 로드
        anchor_ts = create_or_load_debug_anchor(
            thread_ts, session_id, store, prompt, Config.OM_DEBUG_CHANNEL,
        )

        # 디버그 로그 이벤트 #7, #8: 주입 정보
        send_injection_debug_log(
            thread_ts, result, Config.OM_DEBUG_CHANNEL, anchor_ts=anchor_ts,
        )

        return memory_prompt, anchor_ts
    except Exception as e:
        logger.warning(f"OM 주입 실패 (무시): {e}")
        return None, ""


def create_or_load_debug_anchor(
    thread_ts: str,
    session_id: Optional[str],
    store: "MemoryStore",
    prompt: Optional[str],
    debug_channel: str,
) -> str:
    """디버그 앵커 메시지를 생성하거나 기존 앵커를 로드합니다.

    새 세션이면 앵커 메시지를 생성하고 MemoryRecord에 저장합니다.
    기존 세션이면 MemoryRecord에서 저장된 anchor_ts를 로드합니다.

    Args:
        thread_ts: 스레드 타임스탬프
        session_id: 세션 ID (None이면 새 세션)
        store: MemoryStore 인스턴스
        prompt: 사용자 프롬프트 (앵커 미리보기용)
        debug_channel: 디버그 채널 ID

    Returns:
        anchor_ts (빈 문자열이면 앵커 없음)
    """
    if not debug_channel:
        return ""

    # 기존 세션: MemoryRecord에서 저장된 anchor_ts 로드
    if session_id is not None:
        record = store.get_record(thread_ts)
        return getattr(record, "anchor_ts", "") or ""

    # 새 세션: 앵커 메시지 생성
    try:
        from seosoyoung.config import Config
        from seosoyoung.memory.observation_pipeline import _send_debug_log
        from seosoyoung.memory.store import MemoryRecord

        safe_prompt = prompt or ""
        preview = safe_prompt[:80]
        if len(safe_prompt) > 80:
            preview += "…"
        anchor_ts = _send_debug_log(
            debug_channel,
            f"{Config.EMOJI_TEXT_SESSION_START} *OM | 세션 시작 감지* `{thread_ts}`\n>{preview}",
        )
        if anchor_ts:
            record = store.get_record(thread_ts)
            if record is None:
                record = MemoryRecord(thread_ts=thread_ts)
            record.anchor_ts = anchor_ts
            store.save_record(record)
        return anchor_ts or ""
    except Exception as e:
        logger.warning(f"OM 앵커 메시지 생성 실패 (무시): {e}")
        return ""


def send_injection_debug_log(
    thread_ts: str,
    result: "InjectionResult",
    debug_channel: str,
    anchor_ts: str = "",
) -> None:
    """디버그 이벤트 #7, #8: 주입 정보를 슬랙에 발송

    LTM/세션 각각 별도 메시지로 발송하며, 주입 내용을 blockquote로 표시.
    anchor_ts가 있으면 해당 스레드에 답글로 발송.
    anchor_ts가 비었으면 채널 본문 오염 방지를 위해 스킵.
    """
    if not debug_channel:
        return
    if not anchor_ts:
        return
    has_any = (
        result.persistent_tokens
        or result.session_tokens
        or result.channel_digest_tokens
        or result.channel_buffer_tokens
        or result.new_observation_tokens
    )
    if not has_any:
        return

    try:
        from seosoyoung.config import Config
        from seosoyoung.memory.observation_pipeline import (
            _blockquote,
            _format_tokens,
            _send_debug_log,
        )

        sid = thread_ts

        # LTM 주입
        if result.persistent_tokens:
            ltm_quote = _blockquote(result.persistent_content)
            _send_debug_log(
                debug_channel,
                f"{Config.EMOJI_TEXT_LTM_INJECT} *OM 장기 기억 주입* `{sid}`\n"
                f">`LTM {_format_tokens(result.persistent_tokens)} tok`\n"
                f"{ltm_quote}",
                thread_ts=anchor_ts,
            )

        # 새 관찰 주입
        if result.new_observation_tokens:
            new_obs_quote = _blockquote(result.new_observation_content)
            _send_debug_log(
                debug_channel,
                f"{Config.EMOJI_TEXT_NEW_OBS_INJECT} *OM 새 관찰 주입* `{sid}`\n"
                f">`새관찰 {_format_tokens(result.new_observation_tokens)} tok`\n"
                f"{new_obs_quote}",
                thread_ts=anchor_ts,
            )

        # 세션 관찰 주입
        if result.session_tokens:
            session_quote = _blockquote(result.session_content)
            _send_debug_log(
                debug_channel,
                f"{Config.EMOJI_TEXT_SESSION_OBS_INJECT} *OM 세션 관찰 주입* `{sid}`\n"
                f">`세션 {_format_tokens(result.session_tokens)} tok`\n"
                f"{session_quote}",
                thread_ts=anchor_ts,
            )

        # 채널 관찰 주입
        if result.channel_digest_tokens or result.channel_buffer_tokens:
            ch_total = result.channel_digest_tokens + result.channel_buffer_tokens
            _send_debug_log(
                debug_channel,
                f"{Config.EMOJI_TEXT_CHANNEL_OBS_INJECT} *채널 관찰 주입* `{sid}`\n"
                f">`digest {_format_tokens(result.channel_digest_tokens)} tok + "
                f"buffer {_format_tokens(result.channel_buffer_tokens)} tok = "
                f"총 {_format_tokens(ch_total)} tok`",
                thread_ts=anchor_ts,
            )
    except Exception as e:
        logger.warning(f"OM 주입 디버그 로그 실패 (무시): {e}")


def trigger_observation(
    thread_ts: str,
    user_id: str,
    prompt: str,
    collected_messages: list[dict],
    anchor_ts: str = "",
) -> None:
    """관찰 파이프라인을 별도 스레드에서 비동기로 트리거 (봇 응답 블로킹 없음)

    공유 이벤트 루프에서 ClaudeSDKClient가 실행되므로,
    별도 스레드에서 새 이벤트 루프를 생성하여 OM 파이프라인을 실행합니다.
    """
    try:
        from seosoyoung.config import Config
        if not Config.OM_ENABLED:
            return

        # tool_use/tool_result 메시지를 필터링하여 순수 user/assistant 텍스트만 전달
        # tool 메시지가 포함되면 턴 토큰이 항상 min_turn_tokens를 초과하여
        # Observer 스킵 로직이 작동하지 않는 문제를 방지
        text_messages = [
            m for m in collected_messages
            if m.get("role") != "tool"
            and not (m.get("content", "").startswith("[tool_use:"))
        ]
        messages = [{"role": "user", "content": prompt}] + text_messages

        def _run_in_thread():
            try:
                from seosoyoung.memory.observation_pipeline import (
                    observe_conversation,
                )
                from seosoyoung.memory.observer import Observer
                from seosoyoung.memory.promoter import Compactor, Promoter
                from seosoyoung.memory.reflector import Reflector
                from seosoyoung.memory.store import MemoryStore

                debug_channel = Config.OM_DEBUG_CHANNEL

                store = MemoryStore(Config.get_memory_path())
                observer = Observer(
                    api_key=Config.OPENAI_API_KEY,
                    model=Config.OM_MODEL,
                )
                reflector = Reflector(
                    api_key=Config.OPENAI_API_KEY,
                    model=Config.OM_MODEL,
                )
                promoter = Promoter(
                    api_key=Config.OPENAI_API_KEY,
                    model=Config.OM_PROMOTER_MODEL,
                )
                compactor = Compactor(
                    api_key=Config.OPENAI_API_KEY,
                    model=Config.OM_PROMOTER_MODEL,
                )
                asyncio.run(observe_conversation(
                    store=store,
                    observer=observer,
                    thread_ts=thread_ts,
                    user_id=user_id,
                    messages=messages,
                    min_turn_tokens=Config.OM_MIN_TURN_TOKENS,
                    reflector=reflector,
                    reflection_threshold=Config.OM_REFLECTION_THRESHOLD,
                    promoter=promoter,
                    promotion_threshold=Config.OM_PROMOTION_THRESHOLD,
                    compactor=compactor,
                    compaction_threshold=Config.OM_PERSISTENT_COMPACTION_THRESHOLD,
                    compaction_target=Config.OM_PERSISTENT_COMPACTION_TARGET,
                    debug_channel=debug_channel,
                    anchor_ts=anchor_ts,
                ))
            except Exception as e:
                logger.error(f"OM 관찰 파이프라인 비동기 실행 오류 (무시): {e}")
                try:
                    from seosoyoung.memory.observation_pipeline import _send_debug_log
                    if Config.OM_DEBUG_CHANNEL:
                        _send_debug_log(
                            Config.OM_DEBUG_CHANNEL,
                            f"❌ *OM 스레드 오류*\n• user: `{user_id}`\n• thread: `{thread_ts}`\n• error: `{e}`",
                            thread_ts=anchor_ts,
                        )
                except Exception:
                    pass

        thread = threading.Thread(target=_run_in_thread, daemon=True)
        thread.start()
        logger.info(f"OM 관찰 파이프라인 트리거됨 (user={user_id}, thread={thread_ts})")
    except Exception as e:
        logger.warning(f"OM 관찰 트리거 실패 (무시): {e}")
