"""스레드 메시지 핸들러 + DM 채널 핸들러"""

import re
import logging
import threading

from seosoyoung.slackbot.config import Config
from seosoyoung.utils.async_bridge import run_in_new_loop
from seosoyoung.core.context import create_hook_context
from seosoyoung.slackbot.slack import download_files_sync, build_file_context
from seosoyoung.slackbot.slack.message_formatter import format_slack_message
from seosoyoung.slackbot.claude.session_context import build_followup_context

logger = logging.getLogger(__name__)

# 채널별 소화 파이프라인 실행 중 여부 (중복 실행 방지)
_digest_running: dict[str, bool] = {}


def build_slack_context(
    channel: str,
    user_id: str,
    thread_ts: str | None = None,
    parent_thread_ts: str | None = None,
) -> str:
    """슬랙 컨텍스트 블록 문자열을 생성합니다.

    Args:
        channel: 채널 ID
        user_id: 사용자 ID
        thread_ts: 현재 메시지의 스레드 타임스탬프
        parent_thread_ts: 상위 스레드 타임스탬프 (스레드 내 메시지인 경우)
    """
    lines = [
        "[사용자의 요청 컨텍스트는 다음과 같습니다]",
        f"- 채널: {channel}",
        f"- 사용자: {user_id}",
    ]
    if parent_thread_ts:
        lines.append(f"- 상위 스레드: {parent_thread_ts}")
    if thread_ts:
        lines.append(f"- 스레드: {thread_ts}")
    return "\n".join(lines)


def process_thread_message(
    event, text, thread_ts, ts, channel, session, say, client,
    get_user_role, run_claude_in_session, log_prefix="메시지",
    channel_store=None, session_manager=None,
    update_message_fn=None, prepare_memory_fn=None,
    trigger_observation_fn=None, on_compact_om_flag=None,
):
    """세션이 있는 스레드에서 메시지를 처리하는 공통 로직.

    mention.py와 message.py에서 공유합니다.

    Returns:
        True if processed, False if skipped (empty message)
    """
    from seosoyoung.slackbot.presentation.types import PresentationContext
    from seosoyoung.slackbot.presentation.progress import build_progress_callbacks

    user_id = event["user"]

    clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

    file_context = ""
    if event.get("files"):
        try:
            downloaded_files = download_files_sync(event, thread_ts)
            if downloaded_files:
                file_context = build_file_context(downloaded_files)
                logger.info(f"파일 {len(downloaded_files)}개 다운로드 완료")
        except Exception as e:
            logger.error(f"파일 다운로드 실패: {e}")

    if not clean_text and not file_context:
        return False

    user_info = get_user_role(user_id, client)
    if not user_info:
        say(text="사용자 정보를 확인할 수 없습니다.", thread_ts=thread_ts)
        return True

    slack_context = build_slack_context(
        channel=channel,
        user_id=user_id,
        thread_ts=ts,
        parent_thread_ts=thread_ts,
    )

    # 후속 채널 컨텍스트 주입 (hybrid 세션이고 channel_store가 있는 경우)
    followup_context = ""
    if session.source_type == "hybrid" and channel_store and session.last_seen_ts:
        followup = build_followup_context(
            channel_id=channel,
            last_seen_ts=session.last_seen_ts,
            channel_store=channel_store,
            monitored_channels=Config.channel_observer.channels,
        )
        if followup["messages"]:
            lines = [
                format_slack_message(msg, channel=channel)
                for msg in followup["messages"]
            ]
            followup_context = (
                "[이전 대화 이후 채널에서 새로 발생한 대화입니다]\n"
                + "\n".join(lines)
            )

            # last_seen_ts 업데이트
            if session_manager:
                session_manager.update_last_seen_ts(thread_ts, followup["last_seen_ts"])

    prompt_parts = [slack_context]
    if followup_context:
        prompt_parts.append(followup_context)
    if clean_text:
        prompt_parts.append(clean_text)
    if file_context:
        prompt_parts.append(file_context)
    prompt = "\n\n".join(prompt_parts)

    logger.info(
        f"{log_prefix} 처리: thread_ts={thread_ts}, "
        f"user={user_info['username']}, role={user_info['role']}, "
        f"text={clean_text[:50] if clean_text else '(파일 첨부)'}"
    )

    # 초기 메시지 표시 (사고 과정 업데이트용)
    initial_text = ("> 소영이 생각합니다..." if user_info["role"] == "admin"
                    else "> 소영이 조회 전용 모드로 생각합니다...")
    initial_msg = client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=initial_text,
        blocks=[{
            "type": "section",
            "text": {"type": "mrkdwn", "text": initial_text}
        }]
    )
    initial_msg_ts = initial_msg["ts"]

    # PresentationContext 구성
    pctx = PresentationContext(
        channel=channel,
        thread_ts=thread_ts,
        msg_ts=ts,
        say=say,
        client=client,
        effective_role=user_info["role"],
        session_id=session.session_id,
        user_id=user_id,
        last_msg_ts=initial_msg_ts,
        is_existing_thread=True,
        is_thread_reply=True,
    )

    # 콜백 팩토리
    on_progress, on_compact = build_progress_callbacks(pctx, update_message_fn)

    # OM: 메모리 주입
    effective_prompt = prompt
    if prepare_memory_fn:
        memory_prompt, anchor_ts = prepare_memory_fn(
            thread_ts, channel, session.session_id, prompt,
        )
        pctx.om_anchor_ts = anchor_ts or None
        if memory_prompt:
            effective_prompt = (
                f"{memory_prompt}\n\n"
                f"위 컨텍스트를 참고하여 질문에 답변해주세요.\n\n"
                f"사용자의 질문: {prompt}"
            )

    # OM: on_compact에 OM 플래그 래핑
    if on_compact_om_flag:
        original_on_compact = on_compact

        async def on_compact_with_om(trigger, message):
            try:
                on_compact_om_flag(thread_ts)
            except Exception as e:
                logger.warning(f"OM inject 플래그 설정 실패 (PreCompact, 무시): {e}")
            await original_on_compact(trigger, message)

        on_compact = on_compact_with_om

    # OM: 결과 핸들러
    def on_result(result, thread_ts_arg, user_message_arg):
        if (trigger_observation_fn
                and result.success
                and session.user_id
                and thread_ts_arg
                and result.collected_messages):
            observation_input = user_message_arg if user_message_arg is not None else prompt
            trigger_observation_fn(
                thread_ts_arg, session.user_id, observation_input,
                result.collected_messages, anchor_ts=pctx.om_anchor_ts or "",
            )

    run_claude_in_session(
        prompt=effective_prompt,
        thread_ts=thread_ts,
        msg_ts=ts,
        on_progress=on_progress,
        on_compact=on_compact,
        presentation=pctx,
        session_id=session.session_id,
        role=user_info["role"],
        user_message=clean_text,
        on_result=on_result,
    )
    return True


def _contains_bot_mention(text: str) -> bool:
    """텍스트에 봇 멘션이 포함되어 있는지 확인"""
    if not Config.slack.bot_user_id:
        # 봇 ID를 알 수 없으면 안전하게 모든 멘션을 봇 멘션으로 간주
        return "<@" in text
    return f"<@{Config.slack.bot_user_id}>" in text


def _handle_dm_message(event, say, client, dependencies):
    """DM 채널 메시지 처리

    앱 DM에서 보낸 메시지를 일반 채널 멘션과 동일하게 처리합니다.
    - 첫 메시지 (thread_ts 없음): 명령어 처리 또는 세션 생성 + Claude 실행
    - 스레드 메시지 (thread_ts 있음): 기존 세션에서 후속 처리
    """
    from seosoyoung.slackbot.handlers.mention import (
        extract_command,
        try_handle_command,
        create_session_and_run_claude,
    )

    session_manager = dependencies["session_manager"]
    restart_manager = dependencies["restart_manager"]
    run_claude_in_session = dependencies["run_claude_in_session"]
    get_user_role = dependencies["get_user_role"]
    channel_store = dependencies.get("channel_store")

    # subtype이 있으면 무시 (message_changed, message_deleted 등)
    if event.get("subtype"):
        return

    text = event.get("text", "")
    thread_ts = event.get("thread_ts")
    ts = event["ts"]
    channel = event["channel"]
    user_id = event["user"]

    # 스레드 메시지: 기존 세션에서 후속 처리
    if thread_ts:
        logger.info(f"DM 스레드 답글 수신: user={user_id}, channel={channel}, thread_ts={thread_ts}, ts={ts}, text={text[:50]}")
        session = session_manager.get(thread_ts)
        if not session:
            logger.warning(f"DM 스레드 세션 미발견: thread_ts={thread_ts}, user={user_id}, channel={channel}")
            return

        if restart_manager.is_pending:
            say(
                text="재시작을 대기하는 중입니다.\n재시작이 완료되면 다시 대화를 요청해주세요.",
                thread_ts=thread_ts
            )
            return

        process_thread_message(
            event, text, thread_ts, ts, channel, session, say, client,
            get_user_role, run_claude_in_session, log_prefix="DM 메시지",
            channel_store=channel_store, session_manager=session_manager,
            update_message_fn=dependencies.get("update_message_fn"),
            prepare_memory_fn=dependencies.get("prepare_memory_fn"),
            trigger_observation_fn=dependencies.get("trigger_observation_fn"),
            on_compact_om_flag=dependencies.get("on_compact_om_flag"),
        )
        return

    # 첫 메시지: 명령어 또는 질문
    clean_text = text.strip()
    if not clean_text and not event.get("files"):
        return

    command = clean_text.lower()

    logger.info(f"DM 수신: user={user_id}, text={clean_text[:50]}")

    # 명령어 처리 (공유 함수)
    if try_handle_command(
        command, text, channel, ts, None, user_id,
        say, client, dependencies,
    ):
        return

    # 일반 질문: 세션 생성 + Claude 실행 (공유 함수)
    create_session_and_run_claude(
        event, clean_text, channel, ts, None, user_id,
        say, client, dependencies,
    )


def register_message_handlers(app, dependencies: dict):
    """메시지 핸들러 등록

    Args:
        app: Slack Bolt App 인스턴스
        dependencies: 의존성 딕셔너리
    """
    session_manager = dependencies["session_manager"]
    restart_manager = dependencies["restart_manager"]
    run_claude_in_session = dependencies["run_claude_in_session"]
    get_user_role = dependencies["get_user_role"]
    channel_collector = dependencies.get("channel_collector")
    channel_store = dependencies.get("channel_store")
    channel_observer = dependencies.get("channel_observer")
    channel_compressor = dependencies.get("channel_compressor")
    channel_cooldown = dependencies.get("channel_cooldown")
    mention_tracker = dependencies.get("mention_tracker")
    pm = dependencies.get("plugin_manager")

    @app.event("message")
    def handle_message(event, say, client):
        """스레드 메시지 + DM 메시지 처리

        - 채널 스레드: 세션이 있는 스레드 내 일반 메시지를 처리
        - DM 채널: 앱 DM에서 보낸 메시지를 멘션과 동일하게 처리
        """
        # 채널 관찰 수집 (봇 메시지 포함이므로 bot_id 체크보다 먼저)
        if channel_collector:
            try:
                ch = event.get("channel", "")
                collected = channel_collector.collect(event)
                if collected:
                    # 수집 디버그 로그
                    _send_collect_log(
                        client, ch, channel_store, event,
                    )
                    force = _contains_trigger_word(event.get("text", ""))
                    _maybe_trigger_digest(
                        ch, client,
                        channel_store, channel_observer,
                        channel_compressor, channel_cooldown,
                        force=force,
                        mention_tracker=mention_tracker,
                    )
            except Exception as e:
                logger.error(f"채널 메시지 수집 실패: {e}")

        # 봇 자신의 메시지는 무시
        if event.get("bot_id"):
            return

        channel = event.get("channel")
        text = event.get("text", "")

        # DM 채널 메시지 → 전용 핸들러로 라우팅
        channel_type = event.get("channel_type", "")
        if channel_type == "im":
            _handle_dm_message(event, say, client, dependencies)
            return

        # DM 채널인데 channel_type이 없는 경우 감지 (Slack API 불일치 디버깅)
        if channel and channel.startswith("D") and channel_type != "im":
            logger.warning(f"DM 채널인데 channel_type 불일치: channel={channel}, channel_type={channel_type!r}, thread_ts={event.get('thread_ts')}, user={event.get('user')}")

        # Plugin hook dispatch: on_message
        # 번역 등 플러그인이 처리할 메시지를 디스패치합니다.
        # 플러그인이 STOP을 반환하면 핸들러 체인을 중단합니다.
        if pm and pm.plugins and "<@" not in text:
            try:
                ctx = create_hook_context("on_message", event=event, client=client)
                ctx = run_in_new_loop(pm.dispatch("on_message", ctx))
                if ctx.stopped:
                    return
            except Exception as e:
                logger.error(f"Plugin dispatch 실패: {e}")

        # 스레드 메시지인 경우만 처리
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return

        # 봇 멘션이 포함된 경우 handle_mention에서 처리 (중복 방지)
        # 다른 사람에 대한 멘션은 무시하지 않음
        if _contains_bot_mention(text):
            return

        user_id = event["user"]
        channel = event["channel"]
        ts = event["ts"]

        # 세션 확인
        session = session_manager.get(thread_ts)
        if not session:
            return

        # 재시작 대기 중이면 안내 메시지
        if restart_manager.is_pending:
            say(
                text="재시작을 대기하는 중입니다.\n재시작이 완료되면 다시 대화를 요청해주세요.",
                thread_ts=thread_ts
            )
            return

        process_thread_message(
            event, text, thread_ts, ts, channel, session, say, client,
            get_user_role, run_claude_in_session, log_prefix="메시지",
            channel_store=channel_store, session_manager=session_manager,
            update_message_fn=dependencies.get("update_message_fn"),
            prepare_memory_fn=dependencies.get("prepare_memory_fn"),
            trigger_observation_fn=dependencies.get("trigger_observation_fn"),
            on_compact_om_flag=dependencies.get("on_compact_om_flag"),
        )

    @app.event("reaction_added")
    def handle_reaction(event, client):
        """이모지 리액션 처리

        채널 리액션 수집 후, 플러그인 on_reaction 훅으로 디스패치합니다.
        Execute emoji 처리 등은 TrelloPlugin에서 담당합니다.
        """
        # 채널 리액션 수집
        if channel_collector:
            try:
                channel_collector.collect_reaction(event, action="added")
            except Exception as e:
                logger.error(f"채널 리액션 수집 실패 (added): {e}")

        # Plugin hook dispatch: on_reaction
        if pm and pm.plugins:
            try:
                ctx = create_hook_context("on_reaction", event=event, client=client)
                ctx = run_in_new_loop(pm.dispatch("on_reaction", ctx))
                if ctx.stopped:
                    return
            except Exception as e:
                logger.error(f"Plugin on_reaction dispatch 실패: {e}")


    @app.event("reaction_removed")
    def handle_reaction_removed(event, client):
        """리액션 제거 이벤트 처리

        채널 모니터링 대상의 리액션 제거를 수집합니다.
        """
        if channel_collector:
            try:
                channel_collector.collect_reaction(event, action="removed")
            except Exception as e:
                logger.error(f"채널 리액션 수집 실패 (removed): {e}")


def _contains_trigger_word(text: str) -> bool:
    """텍스트에 트리거 워드가 포함되어 있는지 확인합니다."""
    if not Config.channel_observer.trigger_words:
        return False
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in Config.channel_observer.trigger_words)


def _maybe_trigger_digest(
    channel_id, client, store, observer, compressor, cooldown,
    *, force=False, mention_tracker=None,
):
    """pending 토큰이 threshold_A 이상이면 별도 스레드에서 파이프라인을 실행합니다.

    force=True이면 임계치와 무관하게 즉시 트리거합니다.
    """
    if not all([store, observer, cooldown]):
        return

    pending_tokens = store.count_pending_tokens(channel_id)
    if not force and pending_tokens < Config.channel_observer.threshold_a:
        return

    # 이미 실행 중이면 스킵
    if _digest_running.get(channel_id):
        return

    threshold_a = 1 if force else Config.channel_observer.threshold_a

    def run():
        _digest_running[channel_id] = True
        try:
            from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

            async def _llm_call(system_prompt: str, user_prompt: str) -> str | None:
                response = await observer.client.chat.completions.create(
                    model=observer.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                if not response.choices:
                    return None
                return response.choices[0].message.content

            run_in_new_loop(
                run_channel_pipeline(
                    store=store,
                    observer=observer,
                    channel_id=channel_id,
                    slack_client=client,
                    cooldown=cooldown,
                    threshold_a=threshold_a,
                    threshold_b=Config.channel_observer.threshold_b,
                    compressor=compressor,
                    digest_max_tokens=Config.channel_observer.digest_max_tokens,
                    digest_target_tokens=Config.channel_observer.digest_target_tokens,
                    debug_channel=Config.channel_observer.debug_channel,
                    intervention_threshold=Config.channel_observer.intervention_threshold,
                    llm_call=_llm_call,
                    bot_user_id=Config.slack.bot_user_id,
                    mention_tracker=mention_tracker,
                )
            )
        except Exception as e:
            logger.error(f"채널 파이프라인 실행 실패 ({channel_id}): {e}")
        finally:
            _digest_running[channel_id] = False

    digest_thread = threading.Thread(target=run, daemon=True)
    digest_thread.start()


def _send_collect_log(client, channel_id, store, event):
    """수집 디버그 로그를 전송합니다."""
    debug_channel = Config.channel_observer.debug_channel
    if not debug_channel:
        return
    try:
        from seosoyoung.slackbot.memory.channel_intervention import send_collect_debug_log

        # message_changed subtype: 실제 내용은 event["message"] 안에 있음
        if event.get("subtype") == "message_changed":
            source = event.get("message", {})
        else:
            source = event

        buffer_tokens = store.count_pending_tokens(channel_id) if store else 0
        send_collect_debug_log(
            client=client,
            debug_channel=debug_channel,
            source_channel=channel_id,
            buffer_tokens=buffer_tokens,
            threshold=Config.channel_observer.threshold_a,
            message_text=source.get("text", ""),
            user=source.get("user", ""),
            is_thread=bool(source.get("thread_ts") or event.get("thread_ts")),
        )
    except Exception as e:
        logger.error(f"수집 디버그 로그 전송 실패: {e}")
