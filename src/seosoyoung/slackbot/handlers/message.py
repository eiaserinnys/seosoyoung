"""스레드 메시지 핸들러 + DM 채널 핸들러"""

import re
import logging

from seosoyoung.slackbot.config import Config
from seosoyoung.utils.async_bridge import run_in_new_loop
from seosoyoung.core.context import create_hook_context
from seosoyoung.slackbot.slack import download_files_sync, build_file_context
from seosoyoung.slackbot.slack.message_formatter import format_slack_message
from seosoyoung.slackbot.claude.session_context import build_followup_context

logger = logging.getLogger(__name__)


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


def _get_plugin_instance(pm, name):
    """PluginManager에서 플러그인 인스턴스를 가져옵니다."""
    if not pm or not pm.plugins:
        return None
    return pm.plugins.get(name)


def process_thread_message(
    event, text, thread_ts, ts, channel, session, say, client,
    get_user_role, run_claude_in_session, log_prefix="메시지",
    session_manager=None, update_message_fn=None,
    plugin_manager=None,
):
    """세션이 있는 스레드에서 메시지를 처리하는 공통 로직.

    mention.py와 message.py에서 공유합니다.
    Memory injection과 observation은 plugin hooks로 처리합니다.

    Returns:
        True if processed, False if skipped (empty message)
    """
    from seosoyoung.slackbot.presentation.types import PresentationContext
    from seosoyoung.slackbot.presentation.progress import build_progress_callbacks

    pm = plugin_manager
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

    # 후속 채널 컨텍스트 주입 (hybrid 세션)
    followup_context = ""
    co_plugin = _get_plugin_instance(pm, "channel_observer")
    channel_store = co_plugin.store if co_plugin else None
    channel_observer_channels = co_plugin.channels if co_plugin else []

    if (
        session.source_type == "hybrid"
        and channel_store
        and session.last_seen_ts
    ):
        followup = build_followup_context(
            channel_id=channel,
            last_seen_ts=session.last_seen_ts,
            channel_store=channel_store,
            monitored_channels=channel_observer_channels,
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
                session_manager.update_last_seen_ts(
                    thread_ts, followup["last_seen_ts"]
                )

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

    # Plugin: before_execute hook — memory injection
    effective_prompt = prompt
    if pm:
        try:
            ctx = create_hook_context(
                "before_execute",
                thread_ts=thread_ts,
                channel=channel,
                session_id=session.session_id,
                prompt=prompt,
                channel_observer_channels=channel_observer_channels,
            )
            ctx = run_in_new_loop(pm.dispatch("before_execute", ctx))
            for result in ctx.results:
                if isinstance(result, dict):
                    if "prompt" in result:
                        effective_prompt = result["prompt"]
                    if "anchor_ts" in result:
                        pctx.om_anchor_ts = result["anchor_ts"]
        except Exception as e:
            logger.warning(f"before_execute hook 실패 (무시): {e}")

    # Plugin: on_compact에 MemoryPlugin compact 플래그 래핑
    memory_plugin = _get_plugin_instance(pm, "memory")
    if memory_plugin:
        original_on_compact = on_compact

        async def on_compact_with_om(trigger, message):
            try:
                memory_plugin.on_compact_flag(thread_ts)
            except Exception as e:
                logger.warning(
                    f"OM inject 플래그 설정 실패 (PreCompact, 무시): {e}"
                )
            await original_on_compact(trigger, message)

        on_compact = on_compact_with_om

    # Plugin: after_execute hook — observation trigger
    def on_result(result, thread_ts_arg, user_message_arg):
        if (
            pm
            and result.success
            and session.user_id
            and thread_ts_arg
            and result.collected_messages
        ):
            observation_input = (
                user_message_arg
                if user_message_arg is not None
                else prompt
            )
            try:
                ctx = create_hook_context(
                    "after_execute",
                    thread_ts=thread_ts_arg,
                    user_id=session.user_id,
                    prompt=observation_input,
                    collected_messages=result.collected_messages,
                    anchor_ts=pctx.om_anchor_ts or "",
                )
                run_in_new_loop(pm.dispatch("after_execute", ctx))
            except Exception as e:
                logger.warning(f"after_execute hook 실패 (무시): {e}")

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
    pm = dependencies.get("plugin_manager")

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
            session_manager=session_manager,
            update_message_fn=dependencies.get("update_message_fn"),
            plugin_manager=pm,
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
    pm = dependencies.get("plugin_manager")

    @app.event("message")
    def handle_message(event, say, client):
        """스레드 메시지 + DM 메시지 처리

        - 채널 스레드: 세션이 있는 스레드 내 일반 메시지를 처리
        - DM 채널: 앱 DM에서 보낸 메시지를 멘션과 동일하게 처리
        """
        # Plugin hook dispatch: on_message (collection phase)
        # 봇 메시지 포함 모든 메시지를 플러그인에 전달합니다.
        # ChannelObserverPlugin이 수집+소화 트리거를 처리합니다.
        # TranslatePlugin은 자체 bot_id 가드를 가집니다.
        if pm and pm.plugins:
            try:
                ctx = create_hook_context(
                    "on_message", event=event, client=client,
                )
                ctx = run_in_new_loop(pm.dispatch("on_message", ctx))
                if ctx.stopped:
                    return
            except Exception as e:
                logger.error(f"Plugin on_message dispatch 실패: {e}")

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
            session_manager=session_manager,
            update_message_fn=dependencies.get("update_message_fn"),
            plugin_manager=pm,
        )

    @app.event("reaction_added")
    def handle_reaction(event, client):
        """이모지 리액션 처리

        채널 리액션 수집 후, 플러그인 on_reaction 훅으로 디스패치합니다.
        Execute emoji 처리 등은 TrelloPlugin에서 담당합니다.
        """
        # 채널 리액션 수집 (ChannelObserverPlugin)
        co_plugin = _get_plugin_instance(pm, "channel_observer")
        if co_plugin:
            try:
                co_plugin.collect_reaction(event, action="added")
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
        co_plugin = _get_plugin_instance(pm, "channel_observer")
        if co_plugin:
            try:
                co_plugin.collect_reaction(event, action="removed")
            except Exception as e:
                logger.error(f"채널 리액션 수집 실패 (removed): {e}")
