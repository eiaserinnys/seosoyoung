"""스레드 메시지 핸들러"""

import re
import logging
import threading
import asyncio

from seosoyoung.config import Config
from seosoyoung.handlers.translate import process_translate_message
from seosoyoung.slack import download_files_sync, build_file_context
from seosoyoung.claude import get_claude_runner

logger = logging.getLogger(__name__)

# 채널별 소화 파이프라인 실행 중 여부 (중복 실행 방지)
_digest_running: dict[str, bool] = {}


def process_thread_message(
    event, text, thread_ts, ts, channel, session, say, client,
    get_user_role, run_claude_in_session, log_prefix="메시지"
):
    """세션이 있는 스레드에서 메시지를 처리하는 공통 로직.

    mention.py와 message.py에서 공유합니다.

    Returns:
        True if processed, False if skipped (empty message)
    """
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

    prompt_parts = []
    if clean_text:
        prompt_parts.append(clean_text)
    if file_context:
        prompt_parts.append(file_context)
    prompt = "\n".join(prompt_parts)

    logger.info(
        f"{log_prefix} 처리: thread_ts={thread_ts}, "
        f"user={user_info['username']}, role={user_info['role']}, "
        f"text={clean_text[:50] if clean_text else '(파일 첨부)'}"
    )

    run_claude_in_session(session, prompt, ts, channel, say, client, role=user_info["role"])
    return True


def _contains_bot_mention(text: str) -> bool:
    """텍스트에 봇 멘션이 포함되어 있는지 확인"""
    if not Config.BOT_USER_ID:
        # 봇 ID를 알 수 없으면 안전하게 모든 멘션을 봇 멘션으로 간주
        return "<@" in text
    return f"<@{Config.BOT_USER_ID}>" in text


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

    @app.event("message")
    def handle_message(event, say, client):
        """스레드 메시지 처리

        세션이 있는 스레드 내 일반 메시지를 처리합니다.
        (멘션 없이 스레드에 작성된 메시지)
        """
        # 채널 관찰 수집 (봇 메시지 포함이므로 bot_id 체크보다 먼저)
        if channel_collector:
            try:
                ch = event.get("channel", "")
                collected = channel_collector.collect(event)
                if collected:
                    is_self = (
                        Config.BOT_USER_ID
                        and event.get("user") == Config.BOT_USER_ID
                    )
                    # 개입 모드 중이면 소화 대신 즉시 반응
                    # 단, 자기 자신의 메시지에는 반응하지 않음 (자기 대화 루프 방지)
                    if channel_cooldown and channel_cooldown.is_active(ch):
                        if not is_self:
                            _maybe_trigger_intervention_response(
                                ch, client,
                                channel_store, channel_observer, channel_cooldown,
                            )
                    else:
                        _maybe_trigger_digest(
                            ch, client,
                            channel_store, channel_observer,
                            channel_compressor, channel_cooldown,
                        )
            except Exception as e:
                logger.error(f"채널 메시지 수집 실패: {e}")

        # 봇 자신의 메시지는 무시
        if event.get("bot_id"):
            return

        channel = event.get("channel")
        text = event.get("text", "")

        # 번역 채널인 경우: 멘션이 없으면 번역, 멘션이 있으면 기존 로직 (handle_mention에서 처리)
        if channel in Config.TRANSLATE_CHANNELS:
            if "<@" not in text:
                process_translate_message(event, client)
            return

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
            get_user_role, run_claude_in_session, log_prefix="메시지"
        )

    @app.event("reaction_added")
    def handle_reaction(event, client):
        """이모지 리액션 처리

        트렐로 워처가 계획 수립 후 Backlog로 이동한 카드의 슬랙 메시지에
        사용자가 실행 리액션(rocket)을 달면, 해당 스레드에서 세션을 이어서 실행합니다.

        워크플로우:
        1. 리액션이 EXECUTE_EMOJI인지 확인
        2. 리액션된 메시지가 트렐로 워처의 결과인지 TrackedCard로 확인
        3. 기존 세션 조회 및 compact 처리
        4. Execute 레이블이 있는 것과 동일한 프롬프트로 실행
        5. 원본 메시지의 스레드에 응답
        """
        reaction = event.get("reaction", "")
        item = event.get("item", {})
        item_ts = item.get("ts", "")
        item_channel = item.get("channel", "")
        user_id = event.get("user", "")

        # 1. 실행 리액션인지 확인
        if reaction != Config.EXECUTE_EMOJI:
            return

        logger.info(f"실행 리액션 감지: {reaction} on {item_ts} by {user_id}")

        # 2. 트렐로 워처 참조 가져오기
        trello_watcher = dependencies.get("trello_watcher_ref", lambda: None)()
        if not trello_watcher:
            logger.debug("트렐로 워처가 없습니다.")
            return

        # 3. ThreadCardInfo 조회 (해당 메시지가 트렐로 워처 결과인지 확인)
        tracked = trello_watcher.get_tracked_by_thread_ts(item_ts)
        if not tracked:
            logger.debug(f"ThreadCardInfo를 찾을 수 없습니다: {item_ts}")
            return

        logger.info(f"ThreadCardInfo 발견: {tracked.card_name} (card_id={tracked.card_id})")

        # 4. 기존 세션 조회
        session = session_manager.get(item_ts)
        if not session:
            logger.warning(f"세션을 찾을 수 없습니다: {item_ts}")
            # 세션이 없으면 새로 생성
            session = session_manager.create(
                thread_ts=item_ts,
                channel_id=item_channel,
                user_id=user_id,
                username="reaction_executor",
                role="admin"
            )

        # 5. 재시작 대기 중이면 무시
        if restart_manager.is_pending:
            try:
                client.chat_postMessage(
                    channel=item_channel,
                    thread_ts=item_ts,
                    text="재시작을 대기하는 중입니다. 재시작이 완료되면 다시 시도해주세요."
                )
            except Exception as e:
                logger.error(f"리액션 실행 거부 메시지 전송 실패: {e}")
            return

        # 6. 스레드에 실행 시작 알림 (원본 메시지의 스레드에)
        try:
            start_msg = client.chat_postMessage(
                channel=item_channel,
                thread_ts=item_ts,
                text="`🚀 리액션으로 실행을 시작합니다. 세션을 정리하는 중...`"
            )
            start_msg_ts = start_msg["ts"]
        except Exception as e:
            logger.error(f"실행 시작 알림 전송 실패: {e}")
            return

        # 7. 실행 프롬프트 생성
        prompt = trello_watcher.build_reaction_execute_prompt(tracked)

        # 8. 실행을 위해 TrackedCard에 has_execute 플래그 설정
        tracked.has_execute = True

        # 9. 별도 스레드에서 compact + 실행
        def run_with_compact():
            lock = None
            get_session_lock = dependencies.get("get_session_lock")
            if get_session_lock:
                lock = get_session_lock(item_ts)
                if not lock.acquire(blocking=False):
                    try:
                        client.chat_update(
                            channel=item_channel,
                            ts=start_msg_ts,
                            text="이전 요청을 처리 중이에요. 잠시 후 다시 시도해주세요."
                        )
                    except Exception:
                        pass
                    return

            try:
                # Compact 처리
                if session.session_id:
                    try:
                        client.chat_update(
                            channel=item_channel,
                            ts=start_msg_ts,
                            text="`🚀 세션 정리 중... (compact)`"
                        )

                        runner = get_claude_runner()
                        compact_result = asyncio.run(runner.compact_session(session.session_id))

                        if compact_result.success:
                            logger.info(f"세션 컴팩트 성공: {session.session_id}")
                        else:
                            logger.warning(f"세션 컴팩트 실패: {compact_result.error}")

                        # 컴팩트 후 세션 ID가 변경될 수 있음
                        if compact_result.session_id:
                            session_manager.update_session_id(item_ts, compact_result.session_id)

                    except Exception as e:
                        logger.error(f"세션 컴팩트 오류: {e}")

                # say 함수 정의
                def say(text, thread_ts=None):
                    client.chat_postMessage(
                        channel=item_channel,
                        thread_ts=thread_ts or item_ts,
                        text=text
                    )

                # Claude 실행 (trello_card 정보 전달)
                run_claude_in_session(
                    session=session,
                    prompt=prompt,
                    msg_ts=start_msg_ts,
                    channel=item_channel,
                    say=say,
                    client=client,
                    trello_card=tracked
                )

            except Exception as e:
                logger.exception(f"리액션 기반 실행 오류: {e}")
                try:
                    client.chat_update(
                        channel=item_channel,
                        ts=start_msg_ts,
                        text=f"❌ 실행 오류: {str(e)}"
                    )
                except Exception:
                    pass
            finally:
                if lock:
                    lock.release()

        # 백그라운드 스레드에서 실행
        execute_thread = threading.Thread(target=run_with_compact, daemon=True)
        execute_thread.start()


def _maybe_trigger_digest(
    channel_id, client, store, observer, compressor, cooldown
):
    """버퍼 토큰 임계치를 초과하면 별도 스레드에서 소화 파이프라인을 실행합니다."""
    if not all([store, observer, cooldown]):
        return

    # 간이 토큰 체크 (실제 임계치 체크는 digest_channel 내부에서 수행)
    buffer_tokens = store.count_buffer_tokens(channel_id)
    if buffer_tokens < Config.CHANNEL_OBSERVER_BUFFER_THRESHOLD:
        return

    # 이미 실행 중이면 스킵
    if _digest_running.get(channel_id):
        return

    def run():
        _digest_running[channel_id] = True
        try:
            from seosoyoung.memory.channel_pipeline import run_digest_and_intervene

            asyncio.run(
                run_digest_and_intervene(
                    store=store,
                    observer=observer,
                    channel_id=channel_id,
                    slack_client=client,
                    cooldown=cooldown,
                    buffer_threshold=Config.CHANNEL_OBSERVER_BUFFER_THRESHOLD,
                    compressor=compressor,
                    digest_max_tokens=Config.CHANNEL_OBSERVER_DIGEST_MAX_TOKENS,
                    digest_target_tokens=Config.CHANNEL_OBSERVER_DIGEST_TARGET_TOKENS,
                    debug_channel=Config.CHANNEL_OBSERVER_DEBUG_CHANNEL,
                    max_intervention_turns=Config.CHANNEL_OBSERVER_MAX_INTERVENTION_TURNS,
                )
            )
        except Exception as e:
            logger.error(f"채널 소화 파이프라인 실행 실패 ({channel_id}): {e}")
        finally:
            _digest_running[channel_id] = False

    digest_thread = threading.Thread(target=run, daemon=True)
    digest_thread.start()


# 채널별 개입 반응 실행 중 여부 (중복 실행 방지)
_intervention_running: dict[str, bool] = {}


def _maybe_trigger_intervention_response(
    channel_id, client, store, observer, cooldown
):
    """개입 모드 중일 때 별도 스레드에서 반응을 생성합니다."""
    if not all([store, observer, cooldown]):
        return

    # 이미 실행 중이면 스킵
    if _intervention_running.get(channel_id):
        return

    def run():
        _intervention_running[channel_id] = True
        try:
            from seosoyoung.memory.channel_pipeline import respond_in_intervention_mode

            async def llm_call(system_prompt, user_prompt):
                response = await observer.client.chat.completions.create(
                    model=observer.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_completion_tokens=1000,
                )
                return response.choices[0].message.content or ""

            asyncio.run(
                respond_in_intervention_mode(
                    store=store,
                    channel_id=channel_id,
                    slack_client=client,
                    cooldown=cooldown,
                    llm_call=llm_call,
                )
            )
        except Exception as e:
            logger.error(f"개입 모드 반응 실패 ({channel_id}): {e}")
        finally:
            _intervention_running[channel_id] = False

    intervention_thread = threading.Thread(target=run, daemon=True)
    intervention_thread.start()
