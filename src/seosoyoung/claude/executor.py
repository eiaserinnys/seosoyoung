"""Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.
인터벤션(intervention) 기능을 지원하여, 실행 중 새 메시지가 도착하면
현재 실행을 중단하고 새 프롬프트로 이어서 실행합니다.
"""

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from seosoyoung.config import Config
from seosoyoung.claude import get_claude_runner
from seosoyoung.claude.session import Session, SessionManager
from seosoyoung.claude.message_formatter import (
    escape_backticks,
    parse_summary_details,
    strip_summary_details_markers,
    build_trello_header,
    build_context_usage_bar,
)
from seosoyoung.claude.reaction_manager import (
    TRELLO_REACTIONS,
    INTERVENTION_EMOJI,
    INTERVENTION_ACCEPTED_EMOJI,
    add_reaction,
    remove_reaction
)
from seosoyoung.trello.watcher import TrackedCard
from seosoyoung.restart import RestartType

logger = logging.getLogger(__name__)


def _get_mcp_config_path() -> Optional[Path]:
    """MCP 설정 파일 경로 반환 (없으면 None)"""
    config_path = Path(__file__).resolve().parents[3] / "mcp_config.json"
    return config_path if config_path.exists() else None


def get_runner_for_role(role: str):
    """역할에 맞는 ClaudeAgentRunner 반환"""
    allowed_tools = Config.ROLE_TOOLS.get(role, Config.ROLE_TOOLS["viewer"])
    # viewer는 수정/실행 도구 명시적 차단, MCP 도구 불필요
    if role == "viewer":
        return get_claude_runner(
            allowed_tools=allowed_tools,
            disallowed_tools=["Write", "Edit", "Bash", "TodoWrite", "WebFetch", "WebSearch", "Task"]
        )
    return get_claude_runner(
        allowed_tools=allowed_tools,
        mcp_config_path=_get_mcp_config_path(),
    )


@dataclass
class PendingPrompt:
    """인터벤션 대기 중인 프롬프트 정보"""
    prompt: str
    msg_ts: str
    channel: str
    say: object
    client: object
    role: Optional[str] = None
    trello_card: Optional[TrackedCard] = None
    is_existing_thread: bool = False
    initial_msg_ts: Optional[str] = None
    dm_channel_id: Optional[str] = None
    dm_thread_ts: Optional[str] = None


class ClaudeExecutor:
    """Claude Code 실행기

    세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
    인터벤션 기능을 지원합니다.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        get_session_lock: Callable,
        mark_session_running: Callable,
        mark_session_stopped: Callable,
        get_running_session_count: Callable,
        restart_manager,
        upload_file_to_slack: Callable,
        send_long_message: Callable,
        send_restart_confirmation: Callable,
        trello_watcher_ref: Optional[Callable] = None,
        list_runner_ref: Optional[Callable] = None,
    ):
        self.session_manager = session_manager
        self.get_session_lock = get_session_lock
        self.mark_session_running = mark_session_running
        self.mark_session_stopped = mark_session_stopped
        self.get_running_session_count = get_running_session_count
        self.restart_manager = restart_manager
        self.upload_file_to_slack = upload_file_to_slack
        self.send_long_message = send_long_message
        self.send_restart_confirmation = send_restart_confirmation
        self.trello_watcher_ref = trello_watcher_ref
        self.list_runner_ref = list_runner_ref

        # 인터벤션: 스레드별 대기 중인 프롬프트
        self._pending_prompts: dict[str, PendingPrompt] = {}
        self._pending_lock = threading.Lock()
        # 인터벤션: 실행 중인 runner 추적 (interrupt 전송용)
        self._active_runners: dict[str, object] = {}
        self._runners_lock = threading.Lock()

    def run(
        self,
        session: Session,
        prompt: str,
        msg_ts: str,
        channel: str,
        say,
        client,
        role: str = None,
        trello_card: TrackedCard = None,
        is_existing_thread: bool = False,
        initial_msg_ts: str = None,
        dm_channel_id: str = None,
        dm_thread_ts: str = None,
    ):
        """세션 내에서 Claude Code 실행 (공통 로직)

        인터벤션 지원:
        - 락 획득 실패 시 ⚡ 리액션 + pending 저장 + interrupt
        - 실행 완료 후 pending이 있으면 이어서 실행

        Args:
            session: Session 객체
            prompt: Claude에 전달할 프롬프트
            msg_ts: 원본 메시지 타임스탬프 (이모지 추가용)
            channel: Slack 채널 ID
            say: Slack say 함수
            client: Slack client
            role: 실행할 역할 (None이면 session.role 사용)
            trello_card: 트렐로 워처에서 호출된 경우 TrackedCard 정보
            is_existing_thread: 기존 스레드에서 호출된 경우 True (세션 없이 스레드에서 처음 호출)
            initial_msg_ts: 이미 생성된 초기 메시지 ts (있으면 새로 생성하지 않음)
            dm_channel_id: 트렐로 모드에서 사고 과정을 출력할 DM 채널 ID
            dm_thread_ts: DM 스레드의 앵커 메시지 ts
        """
        thread_ts = session.thread_ts

        # 스레드별 락으로 동시 실행 방지
        lock = self.get_session_lock(thread_ts)
        if not lock.acquire(blocking=False):
            # 인터벤션: 리액션만 추가하고 pending에 저장 후 interrupt
            self._handle_intervention(
                thread_ts, prompt, msg_ts, channel, say, client,
                role=role, trello_card=trello_card,
                is_existing_thread=is_existing_thread,
                initial_msg_ts=initial_msg_ts,
                dm_channel_id=dm_channel_id,
                dm_thread_ts=dm_thread_ts,
            )
            return

        try:
            self._run_with_lock(
                session, prompt, msg_ts, channel, say, client,
                role=role, trello_card=trello_card,
                is_existing_thread=is_existing_thread,
                initial_msg_ts=initial_msg_ts,
                dm_channel_id=dm_channel_id,
                dm_thread_ts=dm_thread_ts,
            )
        finally:
            lock.release()

    def _handle_intervention(
        self,
        thread_ts: str,
        prompt: str,
        msg_ts: str,
        channel: str,
        say,
        client,
        role: str = None,
        trello_card: TrackedCard = None,
        is_existing_thread: bool = False,
        initial_msg_ts: str = None,
        dm_channel_id: str = None,
        dm_thread_ts: str = None,
    ):
        """인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우

        ⚡ 리액션 추가 → pending 저장 → interrupt fire → 즉시 return
        """
        logger.info(f"인터벤션 발생: thread={thread_ts}")

        # ⚡ 리액션 추가 (메시지 없음)
        add_reaction(client, channel, msg_ts, INTERVENTION_EMOJI)

        # pending에 저장 (최신 것으로 덮어씀)
        pending = PendingPrompt(
            prompt=prompt,
            msg_ts=msg_ts,
            channel=channel,
            say=say,
            client=client,
            role=role,
            trello_card=trello_card,
            is_existing_thread=is_existing_thread,
            initial_msg_ts=initial_msg_ts,
            dm_channel_id=dm_channel_id,
            dm_thread_ts=dm_thread_ts,
        )
        with self._pending_lock:
            self._pending_prompts[thread_ts] = pending

        # interrupt fire-and-forget (실행 중인 runner에게 전송)
        with self._runners_lock:
            runner = self._active_runners.get(thread_ts)
        if runner:
            try:
                runner.run_sync(runner.interrupt(thread_ts))
                logger.info(f"인터럽트 전송 완료: thread={thread_ts}")
            except Exception as e:
                logger.warning(f"인터럽트 전송 실패 (무시): thread={thread_ts}, {e}")
        else:
            logger.warning(f"인터럽트 전송 불가: 실행 중인 runner 없음 (thread={thread_ts})")

    def _pop_pending(self, thread_ts: str) -> Optional[PendingPrompt]:
        """pending 프롬프트를 꺼내고 제거"""
        with self._pending_lock:
            return self._pending_prompts.pop(thread_ts, None)

    def _run_with_lock(
        self,
        session: Session,
        prompt: str,
        msg_ts: str,
        channel: str,
        say,
        client,
        role: str = None,
        trello_card: TrackedCard = None,
        is_existing_thread: bool = False,
        initial_msg_ts: str = None,
        dm_channel_id: str = None,
        dm_thread_ts: str = None,
    ):
        """락을 보유한 상태에서 실행 (while 루프로 pending 처리)"""
        thread_ts = session.thread_ts
        original_thread_ts = thread_ts
        effective_role = role or session.role
        is_trello_mode = trello_card is not None

        # 실행 중 세션으로 표시
        self.mark_session_running(original_thread_ts)

        try:
            # 첫 번째 실행
            last_msg_ts, thread_ts = self._execute_once(
                session, prompt, msg_ts, channel, say, client,
                effective_role=effective_role,
                trello_card=trello_card,
                is_existing_thread=is_existing_thread,
                initial_msg_ts=initial_msg_ts,
                is_trello_mode=is_trello_mode,
                thread_ts_override=None,
                dm_channel_id=dm_channel_id,
                dm_thread_ts=dm_thread_ts,
            )

            # pending 확인 → while 루프
            while True:
                pending = self._pop_pending(original_thread_ts)
                if not pending:
                    break

                logger.info(f"인터벤션 이어가기: thread={original_thread_ts}")

                # 📩 → ✅ 리액션 교체
                remove_reaction(pending.client, pending.channel, pending.msg_ts, INTERVENTION_EMOJI)
                add_reaction(pending.client, pending.channel, pending.msg_ts, INTERVENTION_ACCEPTED_EMOJI)

                # pending의 정보로 다음 실행
                p_role = pending.role or session.role
                p_trello = pending.trello_card
                p_is_trello = p_trello is not None

                last_msg_ts, thread_ts = self._execute_once(
                    session, pending.prompt, pending.msg_ts, pending.channel,
                    pending.say, pending.client,
                    effective_role=p_role,
                    trello_card=p_trello,
                    is_existing_thread=pending.is_existing_thread,
                    initial_msg_ts=pending.initial_msg_ts,
                    is_trello_mode=p_is_trello,
                    thread_ts_override=thread_ts,  # 이전 실행의 thread_ts 사용
                    dm_channel_id=pending.dm_channel_id or dm_channel_id,
                    dm_thread_ts=pending.dm_thread_ts or dm_thread_ts,
                )

        finally:
            self.mark_session_stopped(original_thread_ts)

    def _execute_once(
        self,
        session: Session,
        prompt: str,
        msg_ts: str,
        channel: str,
        say,
        client,
        effective_role: str,
        trello_card: Optional[TrackedCard],
        is_existing_thread: bool,
        initial_msg_ts: Optional[str],
        is_trello_mode: bool,
        thread_ts_override: Optional[str] = None,
        dm_channel_id: Optional[str] = None,
        dm_thread_ts: Optional[str] = None,
    ) -> tuple[Optional[str], str]:
        """단일 Claude 실행

        Returns:
            (last_msg_ts, thread_ts) - 다음 실행에서 사용할 정보
        """
        thread_ts = thread_ts_override or session.thread_ts

        # 마지막 메시지 ts 추적 (최종 답변으로 교체할 대상)
        last_msg_ts = None
        main_msg_ts = msg_ts if is_trello_mode else None

        # 트렐로 모드에서 첫 번째 on_progress 호출 시 리액션 추가 여부 추적
        trello_reaction_added = False

        # DM 스레드 사고 과정: 마지막 답글 ts 추적 (트렐로 DM 모드용)
        dm_last_reply_ts: Optional[str] = None
        # DM 스레드 사고 과정 메시지 길이 제한 (슬랙 메시지 최대 길이 고려)
        DM_MSG_MAX_LEN = 3000

        # 스레드 내 후속 대화인지 판단
        is_thread_reply = session.message_count > 0 or is_existing_thread

        if is_trello_mode:
            last_msg_ts = msg_ts
        elif initial_msg_ts:
            # 이미 초기 메시지가 있으면 재사용 (P = 사고 과정 메시지)
            last_msg_ts = initial_msg_ts
            # 세션의 thread_ts는 M(멘션 메시지)의 ts를 유지
            # P의 ts를 세션 thread_ts로 바꾸지 않음
        else:
            # 초기 메시지: blockquote 형태로 생각 과정 표시
            if effective_role == "admin":
                initial_text = "소영이 생각합니다..."
            else:
                initial_text = "소영이 조회 전용 모드로 생각합니다..."

            quote_text = f"> {initial_text}"

            # 사고 과정 메시지는 항상 스레드에 답글로 달기
            initial_msg = client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=quote_text,
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": quote_text}
                }]
            )
            last_msg_ts = initial_msg["ts"]

        # 스트리밍 콜백
        async def on_progress(current_text: str):
            nonlocal last_msg_ts, trello_reaction_added, dm_last_reply_ts
            try:
                display_text = current_text.lstrip("\n")
                if not display_text:
                    return
                if len(display_text) > 3800:
                    display_text = "...\n" + display_text[-3800:]

                if is_trello_mode:
                    if not trello_reaction_added:
                        reaction = TRELLO_REACTIONS["executing"] if trello_card.has_execute else TRELLO_REACTIONS["planning"]
                        add_reaction(client, channel, main_msg_ts, reaction)
                        trello_reaction_added = True

                    # DM 스레드가 있으면 DM에 blockquote 답글 추가
                    # current_text는 턴 단위 텍스트이므로 전체를 새 메시지로 전송
                    if dm_channel_id and dm_thread_ts:
                        # blockquote 형태로 변환
                        escaped_text = escape_backticks(display_text)
                        if len(escaped_text) > DM_MSG_MAX_LEN:
                            escaped_text = escaped_text[-DM_MSG_MAX_LEN:]
                        quote_lines = [f"> {line}" for line in escaped_text.split("\n")]
                        quote_text = "\n".join(quote_lines)

                        # 항상 새 메시지로 추가 (로그처럼 쌓이는 방식)
                        # dm_last_reply_ts는 최종 응답 교체용으로만 추적
                        reply = client.chat_postMessage(
                            channel=dm_channel_id,
                            thread_ts=dm_thread_ts,
                            text=quote_text,
                            blocks=[{
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": quote_text}
                            }]
                        )
                        dm_last_reply_ts = reply["ts"]
                    else:
                        # DM 스레드 없으면 기존 동작: 알림 채널 메인 메시지 덮어쓰기
                        header = build_trello_header(trello_card, session.session_id or "")
                        escaped_text = escape_backticks(display_text)
                        update_text = f"{header}\n\n```\n{escaped_text}\n```"

                        client.chat_update(
                            channel=channel,
                            ts=main_msg_ts,
                            text=update_text,
                            blocks=[{
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": update_text}
                            }]
                        )
                else:
                    # blockquote 형태로 사고 과정 표시
                    escaped_text = escape_backticks(display_text)
                    quote_lines = [f"> {line}" for line in escaped_text.split("\n")]
                    quote_text = "\n".join(quote_lines)
                    client.chat_update(
                        channel=channel,
                        ts=last_msg_ts,
                        text=quote_text,
                        blocks=[{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": quote_text}
                        }]
                    )
            except Exception as e:
                logger.warning(f"사고 과정 메시지 전송 실패: {e}")

        # 컴팩션 알림 콜백
        async def on_compact(trigger: str, message: str):
            try:
                if trigger == "auto":
                    text = "🔄 컨텍스트가 자동 압축됩니다..."
                else:
                    text = "📦 컨텍스트를 압축하는 중입니다..."
                say(text=text, thread_ts=thread_ts)
            except Exception as e:
                logger.warning(f"컴팩션 알림 전송 실패: {e}")

        # 역할에 맞는 runner 생성 및 등록
        # original_thread_ts: session.thread_ts (변경 전) — _active_runners 키로 사용
        original_thread_ts = session.thread_ts
        runner = get_runner_for_role(effective_role)
        with self._runners_lock:
            self._active_runners[original_thread_ts] = runner
        logger.info(f"Claude 실행: thread={thread_ts}, role={effective_role}")

        # Claude Code 실행
        try:
            result = runner.run_sync(runner.run(
                prompt=prompt,
                session_id=session.session_id,
                on_progress=on_progress,
                on_compact=on_compact,
                user_id=session.user_id,
                thread_ts=thread_ts,
                channel=channel,
            ))

            # 세션 ID 업데이트
            if result.session_id and result.session_id != session.session_id:
                self.session_manager.update_session_id(thread_ts, result.session_id)

            # 메시지 카운트 증가
            self.session_manager.increment_message_count(thread_ts)

            if result.interrupted:
                # 인터럽트로 중단됨: 사고 과정 메시지를 "(중단됨)"으로 업데이트
                self._handle_interrupted(
                    last_msg_ts, main_msg_ts, is_trello_mode, trello_card,
                    session, channel, client,
                    dm_channel_id=dm_channel_id,
                    dm_last_reply_ts=dm_last_reply_ts,
                )
            elif result.success:
                self._handle_success(
                    result, session, effective_role, is_trello_mode, trello_card,
                    channel, thread_ts, msg_ts, last_msg_ts, main_msg_ts, say, client,
                    is_thread_reply=is_thread_reply,
                    dm_channel_id=dm_channel_id,
                    dm_thread_ts=dm_thread_ts,
                    dm_last_reply_ts=dm_last_reply_ts,
                )
            else:
                self._handle_error(
                    result.error, is_trello_mode, trello_card, session,
                    channel, msg_ts, last_msg_ts, main_msg_ts, say, client,
                    is_thread_reply=is_thread_reply,
                    dm_channel_id=dm_channel_id,
                    dm_last_reply_ts=dm_last_reply_ts,
                )

        except Exception as e:
            logger.exception(f"Claude 실행 오류: {e}")
            self._handle_exception(
                e, is_trello_mode, trello_card, session,
                channel, msg_ts, thread_ts, last_msg_ts, main_msg_ts, say, client,
                is_thread_reply=is_thread_reply,
                dm_channel_id=dm_channel_id,
                dm_last_reply_ts=dm_last_reply_ts,
            )
        finally:
            with self._runners_lock:
                self._active_runners.pop(original_thread_ts, None)

        return last_msg_ts, thread_ts

    def _replace_thinking_message(
        self, client, channel: str, old_msg_ts: str,
        new_text: str, new_blocks: list, thread_ts: str = None
    ) -> str:
        """사고 과정 메시지를 최종 응답으로 교체 (chat_update)

        Args:
            client: Slack client
            channel: 채널 ID
            old_msg_ts: 교체 대상 메시지 ts
            new_text: 새 메시지 텍스트
            new_blocks: 새 메시지 blocks
            thread_ts: 미사용 (하위 호환용으로 유지)

        Returns:
            최종 메시지 ts
        """
        client.chat_update(
            channel=channel,
            ts=old_msg_ts,
            text=new_text,
            blocks=new_blocks,
        )
        return old_msg_ts

    def _handle_interrupted(
        self, last_msg_ts, main_msg_ts, is_trello_mode, trello_card,
        session, channel, client,
        dm_channel_id: str = None,
        dm_last_reply_ts: str = None,
    ):
        """인터럽트로 중단된 실행의 사고 과정 메시지 정리"""
        try:
            # DM 스레드의 마지막 답글을 "(중단됨)"으로 업데이트
            if dm_channel_id and dm_last_reply_ts:
                try:
                    client.chat_update(
                        channel=dm_channel_id,
                        ts=dm_last_reply_ts,
                        text="> (중단됨)",
                        blocks=[{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "> (중단됨)"}
                        }]
                    )
                except Exception as e:
                    logger.warning(f"DM 중단 메시지 업데이트 실패: {e}")

            target_ts = main_msg_ts if is_trello_mode else last_msg_ts
            if not target_ts:
                return

            if is_trello_mode:
                header = build_trello_header(trello_card, session.session_id or "")
                interrupted_text = f"{header}\n\n`(중단됨)`"
            else:
                interrupted_text = "> (중단됨)"

            client.chat_update(
                channel=channel,
                ts=target_ts,
                text=interrupted_text,
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": interrupted_text}
                }]
            )
            logger.info(f"중단된 실행 메시지 업데이트: ts={target_ts}")
        except Exception as e:
            logger.warning(f"중단 메시지 업데이트 실패: {e}")

    def _handle_success(
        self, result, session, effective_role, is_trello_mode, trello_card,
        channel, thread_ts, msg_ts, last_msg_ts, main_msg_ts, say, client,
        is_thread_reply: bool = False,
        dm_channel_id: str = None,
        dm_thread_ts: str = None,
        dm_last_reply_ts: str = None,
    ):
        """성공 결과 처리"""
        response = result.output or ""

        if not response.strip():
            # 응답이 비어있으면 사고 과정 메시지를 (중단됨)으로 정리
            self._handle_interrupted(
                last_msg_ts, main_msg_ts, is_trello_mode, trello_card,
                session, channel, client
            )
            return

        # 컨텍스트 사용량 바 (설정이 켜져 있고 usage 정보가 있을 때)
        usage_bar = None
        if Config.SHOW_CONTEXT_USAGE:
            usage_bar = build_context_usage_bar(result.usage)

        # LIST_RUN: 초기 메시지 삭제를 방지해야 하는 경우
        # 1) result.list_run 마커가 있거나 (새 정주행 시작)
        # 2) trello_card.list_key == "list_run"이면 (정주행 중 개별 카드 실행)
        is_list_run_from_marker = bool(effective_role == "admin" and result.list_run)
        is_list_run_from_card = bool(
            trello_card and getattr(trello_card, "list_key", None) == "list_run"
        )
        is_list_run = is_list_run_from_marker or is_list_run_from_card

        if is_trello_mode:
            self._handle_trello_success(
                result, response, session, trello_card,
                channel, thread_ts, main_msg_ts, say, client,
                is_list_run=is_list_run,
                usage_bar=usage_bar,
                dm_channel_id=dm_channel_id,
                dm_thread_ts=dm_thread_ts,
                dm_last_reply_ts=dm_last_reply_ts,
            )
        else:
            self._handle_normal_success(
                result, response, channel, thread_ts, msg_ts, last_msg_ts, say, client,
                is_thread_reply=is_thread_reply,
                is_list_run=is_list_run,
                usage_bar=usage_bar,
            )

        # 재기동 마커 감지 (admin 역할만 허용)
        if effective_role == "admin":
            if result.update_requested or result.restart_requested:
                self._handle_restart_marker(
                    result, session, channel, thread_ts, say
                )

        # LIST_RUN 마커 감지 (admin 역할만, 새 정주행 시작 마커일 때만)
        if is_list_run_from_marker:
            self._handle_list_run_marker(
                result.list_run, channel, thread_ts, say, client
            )

    def _handle_trello_success(
        self, result, response, session, trello_card,
        channel, thread_ts, main_msg_ts, say, client,
        is_list_run: bool = False,
        usage_bar: str = None,
        dm_channel_id: str = None,
        dm_thread_ts: str = None,
        dm_last_reply_ts: str = None,
    ):
        """트렐로 모드 성공 처리"""
        # DM 스레드의 마지막 blockquote를 평문으로 교체 (완료 표시)
        if dm_channel_id and dm_last_reply_ts:
            try:
                # 응답 미리보기를 DM 스레드에 최종 메시지로 표시
                dm_final = response[:3800] if len(response) > 3800 else response
                client.chat_update(
                    channel=dm_channel_id,
                    ts=dm_last_reply_ts,
                    text=dm_final,
                    blocks=[{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": dm_final}
                    }]
                )
            except Exception as e:
                logger.warning(f"DM 스레드 최종 메시지 업데이트 실패: {e}")

        # 이전 상태 리액션 제거 후 완료 리액션 추가
        prev_reaction = TRELLO_REACTIONS["executing"] if trello_card.has_execute else TRELLO_REACTIONS["planning"]
        remove_reaction(client, channel, main_msg_ts, prev_reaction)
        add_reaction(client, channel, main_msg_ts, TRELLO_REACTIONS["success"])

        final_session_id = result.session_id or session.session_id or ""
        header = build_trello_header(trello_card, final_session_id)
        continuation_hint = "`작업을 이어가려면 이 대화에 댓글을 달아주세요.`"
        if usage_bar:
            continuation_hint = f"{usage_bar}\n{continuation_hint}"

        # 요약/상세 분리 파싱 (멘션과 동일하게 처리)
        summary, details, remainder = parse_summary_details(response)
        logger.info(f"[Trello] 파싱 결과 - summary: {summary is not None}, details: {details is not None}, response 길이: {len(response)}")
        if summary:
            logger.debug(f"[Trello] summary 내용: {summary[:100]}...")

        if summary:
            # 요약/상세 마커가 있는 경우: 메인 메시지에 요약, 스레드에 상세
            max_summary_len = 3900 - len(header) - len(continuation_hint) - 20
            if len(summary) <= max_summary_len:
                final_text = f"{header}\n\n{summary}\n\n{continuation_hint}"
            else:
                truncated = summary[:max_summary_len]
                final_text = f"{header}\n\n{truncated}...\n\n{continuation_hint}"

            final_blocks = [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": final_text}
            }]

            if is_list_run:
                # LIST_RUN: 삭제하면 트렐로 워처가 깨지므로 항상 chat_update만 사용
                client.chat_update(
                    channel=channel,
                    ts=main_msg_ts,
                    text=final_text,
                    blocks=final_blocks,
                )
            else:
                # 트렐로 메시지는 채널 루트이므로 thread_ts=None
                self._replace_thinking_message(
                    client, channel, main_msg_ts,
                    final_text, final_blocks, thread_ts=None,
                )

            # 스레드에 상세 내용 전송 (remainder가 있으면 앞에 붙여서)
            if details:
                if remainder:
                    thread_content = f"{remainder}\n\n{details}"
                else:
                    thread_content = details
                self.send_long_message(say, thread_content, thread_ts)
            elif remainder:
                self.send_long_message(say, remainder, thread_ts)
        else:
            # 기존 로직: 마커가 없는 경우
            max_response_len = 3900 - len(header) - len(continuation_hint) - 20
            if len(response) <= max_response_len:
                final_text = f"{header}\n\n{response}\n\n{continuation_hint}"
            else:
                truncated = response[:max_response_len]
                final_text = f"{header}\n\n{truncated}...\n\n{continuation_hint}"

            final_blocks = [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": final_text}
            }]

            if is_list_run:
                # LIST_RUN: 삭제 방지
                client.chat_update(
                    channel=channel,
                    ts=main_msg_ts,
                    text=final_text,
                    blocks=final_blocks,
                )
            else:
                self._replace_thinking_message(
                    client, channel, main_msg_ts,
                    final_text, final_blocks, thread_ts=None,
                )

            if len(response) > max_response_len:
                self.send_long_message(say, response, thread_ts)

    def _handle_normal_success(
        self, result, response, channel, thread_ts, msg_ts, last_msg_ts, say, client,
        is_thread_reply: bool = False,
        is_list_run: bool = False,
        usage_bar: str = None,
    ):
        """일반 모드(멘션) 성공 처리"""
        continuation_hint = "`자세한 내용을 확인하시거나 대화를 이어가려면 스레드를 확인해주세요.`"
        if usage_bar:
            continuation_hint = f"{usage_bar}\n{continuation_hint}"

        # 요약/상세 분리 파싱
        summary, details, remainder = parse_summary_details(response)

        # P(사고 과정)는 항상 스레드 내에 있으므로 thread_ts를 전달
        reply_thread_ts = thread_ts

        if not is_thread_reply:
            # 채널 최초 응답: P(스레드 내)를 요약으로 교체, 전문도 스레드에
            try:
                if summary:
                    channel_text = summary
                else:
                    # SUMMARY 마커가 없는 경우: 3줄 이내 미리보기
                    lines = response.strip().split("\n")
                    preview_lines = []
                    for line in lines:
                        preview_lines.append(line)
                        if len(preview_lines) >= 3:
                            break
                    channel_text = "\n".join(preview_lines)
                    if len(lines) > 3:
                        channel_text += "\n..."

                # 스레드 내 P를 요약으로 교체
                final_text = f"{channel_text}\n\n{continuation_hint}"
                final_blocks = [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": final_text}
                }]

                if is_list_run:
                    client.chat_update(
                        channel=channel,
                        ts=last_msg_ts,
                        text=final_text,
                        blocks=final_blocks,
                    )
                else:
                    self._replace_thinking_message(
                        client, channel, last_msg_ts,
                        final_text, final_blocks, thread_ts=reply_thread_ts,
                    )

                # 전문을 스레드에 전송
                if summary and details:
                    if remainder:
                        thread_content = f"{remainder}\n\n{details}"
                    else:
                        thread_content = details
                    self.send_long_message(say, thread_content, thread_ts)
                else:
                    full_response = strip_summary_details_markers(response)
                    self.send_long_message(say, full_response, thread_ts)

            except Exception:
                self.send_long_message(say, response, thread_ts)
        else:
            # 스레드 내 후속 대화: 마커가 있으면 태그만 제거하고 스레드에 응답
            display_response = strip_summary_details_markers(response) if (summary or details) else response
            if usage_bar:
                display_response = f"{display_response}\n\n{usage_bar}"

            try:
                if len(display_response) <= 3900:
                    final_text = display_response
                    final_blocks = [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": final_text}
                    }]
                    self._replace_thinking_message(
                        client, channel, last_msg_ts,
                        final_text, final_blocks, thread_ts=reply_thread_ts,
                    )
                else:
                    # 긴 응답: 첫 부분은 사고 과정 메시지를 교체, 나머지는 추가 메시지
                    truncated = display_response[:3900]
                    first_part = f"{truncated}..."
                    first_blocks = [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": first_part}
                    }]
                    self._replace_thinking_message(
                        client, channel, last_msg_ts,
                        first_part, first_blocks, thread_ts=reply_thread_ts,
                    )
                    remaining = display_response[3900:]
                    self.send_long_message(say, remaining, thread_ts)
            except Exception:
                self.send_long_message(say, display_response, thread_ts)

    def _handle_restart_marker(self, result, session, channel, thread_ts, say):
        """재기동 마커 처리"""
        restart_type = RestartType.UPDATE if result.update_requested else RestartType.RESTART
        type_name = "업데이트" if result.update_requested else "재시작"

        running_count = self.get_running_session_count() - 1

        if running_count > 0:
            logger.info(f"{type_name} 마커 감지 - 다른 세션 {running_count}개 실행 중, 확인 필요")
            say(text=f"코드가 변경되었습니다. 다른 대화가 진행 중이어서 확인이 필요합니다.", thread_ts=thread_ts)
            self.send_restart_confirmation(
                client=None,  # Not needed for this call path
                channel=channel,
                restart_type=restart_type,
                running_count=running_count,
                user_id=session.user_id,
                original_thread_ts=thread_ts
            )
        else:
            logger.info(f"{type_name} 마커 감지 - 다른 실행 중인 세션 없음, 즉시 {type_name}")
            say(text=f"코드가 변경되었습니다. {type_name}합니다...", thread_ts=thread_ts)
            self.restart_manager.force_restart(restart_type)

    def _handle_list_run_marker(
        self, list_name: str, channel: str, thread_ts: str, say, client
    ):
        """LIST_RUN 마커 처리 - 정주행 시작

        Args:
            list_name: 정주행할 리스트 이름
            channel: 슬랙 채널 ID
            thread_ts: 스레드 타임스탬프
            say: Slack say 함수
            client: Slack client
        """
        logger.info(f"리스트 정주행 요청: {list_name}")

        # TrelloWatcher 참조 확인
        trello_watcher = self.trello_watcher_ref() if self.trello_watcher_ref else None
        if not trello_watcher:
            logger.warning("TrelloWatcher가 설정되지 않아 정주행을 시작할 수 없습니다.")
            say(
                text="❌ TrelloWatcher가 설정되지 않아 정주행을 시작할 수 없습니다.",
                thread_ts=thread_ts
            )
            return

        # 리스트 이름으로 리스트 ID와 카드 목록 조회
        try:
            lists = trello_watcher.trello.get_lists()
            target_list = None
            for lst in lists:
                if lst.get("name") == list_name:
                    target_list = lst
                    break

            if not target_list:
                logger.warning(f"리스트를 찾을 수 없습니다: {list_name}")
                say(
                    text=f"❌ 리스트를 찾을 수 없습니다: *{list_name}*",
                    thread_ts=thread_ts
                )
                return

            list_id = target_list["id"]
            cards = trello_watcher.trello.get_cards_in_list(list_id)

            if not cards:
                logger.warning(f"리스트에 카드가 없습니다: {list_name}")
                say(
                    text=f"❌ 리스트에 카드가 없습니다: *{list_name}*",
                    thread_ts=thread_ts
                )
                return

            # 정주행 시작 알림 (현재 스레드에 답글로)
            say(
                text=f"📋 리스트 정주행을 시작합니다: *{list_name}* ({len(cards)}개 카드)\n"
                     f"정주행 상태는 별도 스레드에서 확인하실 수 있습니다.",
                thread_ts=thread_ts
            )

            # TrelloWatcher의 _start_list_run 호출
            trello_watcher._start_list_run(list_id, list_name, cards)

        except Exception as e:
            logger.error(f"정주행 시작 실패: {e}")
            say(
                text=f"❌ 정주행 시작에 실패했습니다: {e}",
                thread_ts=thread_ts
            )

    def _handle_error(
        self, error, is_trello_mode, trello_card, session,
        channel, msg_ts, last_msg_ts, main_msg_ts, say, client,
        is_thread_reply: bool = False,
        dm_channel_id: str = None,
        dm_last_reply_ts: str = None,
    ):
        """오류 결과 처리"""
        error_msg = f"오류가 발생했습니다: {error}"

        # DM 스레드에 에러 표시
        if dm_channel_id and dm_last_reply_ts:
            try:
                client.chat_update(
                    channel=dm_channel_id,
                    ts=dm_last_reply_ts,
                    text=f"❌ {error_msg}",
                )
            except Exception as e:
                logger.warning(f"DM 에러 메시지 업데이트 실패: {e}")

        if is_trello_mode:
            # 이전 상태 리액션 제거 후 에러 리액션 추가
            prev_reaction = TRELLO_REACTIONS["executing"] if trello_card.has_execute else TRELLO_REACTIONS["planning"]
            remove_reaction(client, channel, main_msg_ts, prev_reaction)
            add_reaction(client, channel, main_msg_ts, TRELLO_REACTIONS["error"])

            header = build_trello_header(trello_card, session.session_id or "")
            continuation_hint = "`작업을 이어가려면 이 대화에 댓글을 달아주세요.`"
            error_text = f"{header}\n\n❌ {error_msg}\n\n{continuation_hint}"
            client.chat_update(
                channel=channel,
                ts=main_msg_ts,
                text=error_text,
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": error_text}
                }]
            )
        else:
            # 스레드 내 후속 대화에는 continuation hint 불필요
            if is_thread_reply:
                error_text = f"❌ {error_msg}"
            else:
                continuation_hint = "`이 대화를 이어가려면 댓글을 달아주세요.`"
                error_text = f"❌ {error_msg}\n\n{continuation_hint}"
            client.chat_update(
                channel=channel,
                ts=last_msg_ts,
                text=error_text,
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": error_text}
                }]
            )

    def _handle_exception(
        self, e, is_trello_mode, trello_card, session,
        channel, msg_ts, thread_ts, last_msg_ts, main_msg_ts, say, client,
        is_thread_reply: bool = False,
        dm_channel_id: str = None,
        dm_last_reply_ts: str = None,
    ):
        """예외 처리"""
        error_msg = f"오류가 발생했습니다: {str(e)}"

        # DM 스레드에 에러 표시
        if dm_channel_id and dm_last_reply_ts:
            try:
                client.chat_update(
                    channel=dm_channel_id,
                    ts=dm_last_reply_ts,
                    text=f"❌ {error_msg}",
                )
            except Exception:
                pass

        if is_trello_mode:
            try:
                # 이전 상태 리액션 제거 후 에러 리액션 추가
                prev_reaction = TRELLO_REACTIONS["executing"] if trello_card.has_execute else TRELLO_REACTIONS["planning"]
                remove_reaction(client, channel, main_msg_ts, prev_reaction)
                add_reaction(client, channel, main_msg_ts, TRELLO_REACTIONS["error"])

                header = build_trello_header(trello_card, session.session_id or "")
                continuation_hint = "`작업을 이어가려면 이 대화에 댓글을 달아주세요.`"
                client.chat_update(
                    channel=channel,
                    ts=main_msg_ts,
                    text=f"{header}\n\n❌ {error_msg}\n\n{continuation_hint}"
                )
            except Exception:
                say(text=f"❌ {error_msg}", thread_ts=thread_ts)
        else:
            try:
                # 스레드 내 후속 대화에는 continuation hint 불필요
                if is_thread_reply:
                    error_text = f"❌ {error_msg}"
                else:
                    continuation_hint = "`이 대화를 이어가려면 댓글을 달아주세요.`"
                    error_text = f"❌ {error_msg}\n\n{continuation_hint}"
                client.chat_update(
                    channel=channel,
                    ts=last_msg_ts,
                    text=error_text
                )
            except Exception:
                say(text=f"❌ {error_msg}", thread_ts=thread_ts)

