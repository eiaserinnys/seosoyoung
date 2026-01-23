"""Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.
"""

import re
import asyncio
import logging
from typing import Callable, Optional

from seosoyoung.config import Config
from seosoyoung.claude import get_claude_runner
from seosoyoung.claude.session import Session, SessionManager
from seosoyoung.trello.watcher import TrackedCard
from seosoyoung.restart import RestartType

logger = logging.getLogger(__name__)


def get_runner_for_role(role: str):
    """역할에 맞는 ClaudeRunner/ClaudeAgentRunner 반환"""
    allowed_tools = Config.ROLE_TOOLS.get(role, Config.ROLE_TOOLS["viewer"])
    # viewer는 수정/실행 도구 명시적 차단
    if role == "viewer":
        return get_claude_runner(
            allowed_tools=allowed_tools,
            disallowed_tools=["Write", "Edit", "Bash", "TodoWrite", "WebFetch", "WebSearch", "Task"]
        )
    return get_claude_runner(allowed_tools=allowed_tools)


def _escape_backticks(text: str) -> str:
    """텍스트 내 모든 백틱을 이스케이프

    슬랙에서 백틱은 인라인 코드(`)나 코드 블록(```)을 만드므로,
    텍스트 내부에 백틱이 있으면 포맷팅이 깨집니다.
    모든 백틱을 유사 문자(ˋ, modifier letter grave accent)로 대체합니다.

    변환 규칙:
    - ` (모든 백틱) → ˋ (U+02CB, modifier letter grave accent)
    """
    return text.replace('`', 'ˋ')


# 트렐로 모드 이모지 리액션 매핑
TRELLO_REACTIONS = {
    "planning": "thought_balloon",  # 💭 계획 중
    "executing": "arrow_forward",   # ▶️ 실행 중
    "success": "white_check_mark",  # ✅ 완료
    "error": "x",                   # ❌ 오류
}


def _add_reaction(client, channel: str, ts: str, emoji: str) -> bool:
    """슬랙 메시지에 이모지 리액션 추가

    Args:
        client: Slack client
        channel: 채널 ID
        ts: 메시지 타임스탬프
        emoji: 이모지 이름 (콜론 없이, 예: "thought_balloon")

    Returns:
        성공 여부
    """
    try:
        client.reactions_add(channel=channel, timestamp=ts, name=emoji)
        return True
    except Exception as e:
        logger.debug(f"이모지 리액션 추가 실패 ({emoji}): {e}")
        return False


def _remove_reaction(client, channel: str, ts: str, emoji: str) -> bool:
    """슬랙 메시지에서 이모지 리액션 제거

    Args:
        client: Slack client
        channel: 채널 ID
        ts: 메시지 타임스탬프
        emoji: 이모지 이름 (콜론 없이, 예: "thought_balloon")

    Returns:
        성공 여부
    """
    try:
        client.reactions_remove(channel=channel, timestamp=ts, name=emoji)
        return True
    except Exception as e:
        logger.debug(f"이모지 리액션 제거 실패 ({emoji}): {e}")
        return False


def _build_trello_header(card: TrackedCard, session_id: str = "") -> str:
    """트렐로 카드용 슬랙 메시지 헤더 생성

    진행 상태(계획/실행/완료)는 헤더가 아닌 슬랙 이모지 리액션으로 표시합니다.

    Args:
        card: TrackedCard 정보
        session_id: 세션 ID (표시용)

    Returns:
        헤더 문자열
    """
    session_display = f" | #️⃣ {session_id[:8]}" if session_id else ""
    return f"*🎫 <{card.card_url}|{card.card_name}>{session_display}*"


class ClaudeExecutor:
    """Claude Code 실행기

    세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
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

    def run(
        self,
        session: Session,
        prompt: str,
        msg_ts: str,
        channel: str,
        say,
        client,
        role: str = None,
        trello_card: TrackedCard = None
    ):
        """세션 내에서 Claude Code 실행 (공통 로직)

        Args:
            session: Session 객체
            prompt: Claude에 전달할 프롬프트
            msg_ts: 원본 메시지 타임스탬프 (이모지 추가용)
            channel: Slack 채널 ID
            say: Slack say 함수
            client: Slack client
            role: 실행할 역할 (None이면 session.role 사용)
            trello_card: 트렐로 워처에서 호출된 경우 TrackedCard 정보
        """
        thread_ts = session.thread_ts
        effective_role = role or session.role
        is_trello_mode = trello_card is not None

        # 스레드별 락으로 동시 실행 방지
        lock = self.get_session_lock(thread_ts)
        if not lock.acquire(blocking=False):
            say(text="이전 요청을 처리 중이에요. 잠시 후 다시 시도해주세요.", thread_ts=thread_ts)
            return

        # 실행 중 세션으로 표시
        self.mark_session_running(thread_ts)

        # 마지막 메시지 ts 추적 (최종 답변으로 교체할 대상)
        last_msg_ts = None
        main_msg_ts = msg_ts if is_trello_mode else None

        # 트렐로 모드에서 첫 번째 on_progress 호출 시 리액션 추가 여부 추적
        trello_reaction_added = False

        # 멘션 응답 메시지 ts (세션 thread_ts 업데이트용)
        mention_response_ts = None

        try:
            if is_trello_mode:
                last_msg_ts = msg_ts
            else:
                # 초기 메시지: 코드 블럭 형태로 생각 과정 표시
                if effective_role == "admin":
                    initial_text = "소영이 생각합니다..."
                else:
                    initial_text = "소영이 조회 전용 모드로 생각합니다..."

                code_text = f"```\n{initial_text}\n```"
                # 채널에 직접 메시지 생성 (스레드가 아닌 채널 루트에)
                initial_msg = client.chat_postMessage(
                    channel=channel,
                    text=code_text,
                    blocks=[{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": code_text}
                    }]
                )
                last_msg_ts = initial_msg["ts"]
                mention_response_ts = last_msg_ts

                # 세션의 thread_ts를 응답 메시지 ts로 업데이트
                # (스레드로 대화를 이어가기 위해)
                if mention_response_ts and mention_response_ts != thread_ts:
                    self.session_manager.update_thread_ts(thread_ts, mention_response_ts)
                    thread_ts = mention_response_ts  # 이후 로직에서 새 thread_ts 사용

            # 스트리밍 콜백
            async def on_progress(current_text: str):
                nonlocal last_msg_ts, trello_reaction_added
                try:
                    display_text = current_text
                    if len(display_text) > 3800:
                        display_text = "...\n" + display_text[-3800:]

                    if is_trello_mode:
                        # 첫 호출 시 상태 이모지 리액션 추가
                        if not trello_reaction_added:
                            reaction = TRELLO_REACTIONS["executing"] if trello_card.has_execute else TRELLO_REACTIONS["planning"]
                            _add_reaction(client, channel, main_msg_ts, reaction)
                            trello_reaction_added = True

                        header = _build_trello_header(trello_card, session.session_id or "")
                        escaped_text = _escape_backticks(display_text)
                        # 헤더와 코드블록 사이에 빈 줄 추가
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
                        # 일반 모드: chat_update로 기존 메시지 갱신 (트렐로 모드와 동일)
                        escaped_text = _escape_backticks(display_text)
                        code_text = f"```\n{escaped_text}\n```"
                        client.chat_update(
                            channel=channel,
                            ts=last_msg_ts,
                            text=code_text,
                            blocks=[{
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": code_text}
                            }]
                        )
                except Exception as e:
                    logger.warning(f"사고 과정 메시지 전송 실패: {e}")

            # 역할에 맞는 runner 생성
            runner = get_runner_for_role(effective_role)
            logger.info(f"Claude 실행: thread={thread_ts}, role={effective_role}")

            # Claude Code 실행
            try:
                result = asyncio.run(runner.run(
                    prompt=prompt,
                    session_id=session.session_id,
                    on_progress=on_progress
                ))

                # 세션 ID 업데이트
                if result.session_id and result.session_id != session.session_id:
                    self.session_manager.update_session_id(thread_ts, result.session_id)

                # 메시지 카운트 증가
                self.session_manager.increment_message_count(thread_ts)

                if result.success:
                    self._handle_success(
                        result, session, effective_role, is_trello_mode, trello_card,
                        channel, thread_ts, msg_ts, last_msg_ts, main_msg_ts, say, client
                    )
                else:
                    self._handle_error(
                        result.error, is_trello_mode, trello_card, session,
                        channel, last_msg_ts, main_msg_ts, say, client
                    )

            except Exception as e:
                logger.exception(f"Claude 실행 오류: {e}")
                self._handle_exception(
                    e, is_trello_mode, trello_card, session,
                    channel, thread_ts, last_msg_ts, main_msg_ts, say, client
                )

        finally:
            self.mark_session_stopped(thread_ts)
            lock.release()

    def _handle_success(
        self, result, session, effective_role, is_trello_mode, trello_card,
        channel, thread_ts, msg_ts, last_msg_ts, main_msg_ts, say, client
    ):
        """성공 결과 처리"""
        response = result.output or "(응답 없음)"

        if is_trello_mode:
            self._handle_trello_success(
                result, response, session, trello_card,
                channel, thread_ts, main_msg_ts, say, client
            )
        else:
            self._handle_normal_success(
                result, response, channel, thread_ts, msg_ts, last_msg_ts, say, client
            )

        # 재기동 마커 감지 (admin 역할만 허용)
        if effective_role == "admin":
            if result.update_requested or result.restart_requested:
                self._handle_restart_marker(
                    result, session, thread_ts, say
                )

    def _handle_trello_success(
        self, result, response, session, trello_card,
        channel, thread_ts, main_msg_ts, say, client
    ):
        """트렐로 모드 성공 처리"""
        # 이전 상태 리액션 제거 후 완료 리액션 추가
        prev_reaction = TRELLO_REACTIONS["executing"] if trello_card.has_execute else TRELLO_REACTIONS["planning"]
        _remove_reaction(client, channel, main_msg_ts, prev_reaction)
        _add_reaction(client, channel, main_msg_ts, TRELLO_REACTIONS["success"])

        final_session_id = result.session_id or session.session_id or ""
        header = _build_trello_header(trello_card, final_session_id)
        continuation_hint = "`작업을 이어가려면 이 대화에 댓글을 달아주세요.`"

        # 헤더-응답-continuation_hint 사이에 빈 줄 추가
        max_response_len = 3900 - len(header) - len(continuation_hint) - 20  # 줄바꿈 추가 분량 반영
        if len(response) <= max_response_len:
            final_text = f"{header}\n\n{response}\n\n{continuation_hint}"
            client.chat_update(
                channel=channel,
                ts=main_msg_ts,
                text=final_text,
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": final_text}
                }]
            )
        else:
            truncated = response[:max_response_len]
            final_text = f"{header}\n\n{truncated}...\n\n{continuation_hint}"
            client.chat_update(
                channel=channel,
                ts=main_msg_ts,
                text=final_text,
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": final_text}
                }]
            )
            self.send_long_message(say, response, thread_ts)

        # 첨부 파일은 스레드에 전송
        if result.attachments:
            for file_path in result.attachments:
                success, msg = self.upload_file_to_slack(client, channel, thread_ts, file_path)
                if not success:
                    say(text=f"⚠️ {msg}", thread_ts=thread_ts)

    def _handle_normal_success(
        self, result, response, channel, thread_ts, msg_ts, last_msg_ts, say, client
    ):
        """일반 모드(멘션) 성공 처리"""
        continuation_hint = "`이 대화를 이어가려면 댓글을 달아주세요.`"

        try:
            # continuation hint를 포함한 최대 응답 길이 계산
            max_response_len = 3900 - len(continuation_hint) - 10  # 줄바꿈 여유

            if len(response) <= max_response_len:
                final_text = f"{response}\n\n{continuation_hint}"
                client.chat_update(
                    channel=channel,
                    ts=last_msg_ts,
                    text=final_text,
                    blocks=[{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": final_text}
                    }]
                )
            else:
                # 첫 번째 메시지에 잘린 응답 + continuation hint
                truncated = response[:max_response_len]
                first_part = f"{truncated}...\n\n{continuation_hint}"
                client.chat_update(
                    channel=channel,
                    ts=last_msg_ts,
                    text=first_part,
                    blocks=[{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": first_part}
                    }]
                )
                # 나머지는 스레드에 전송
                remaining = response[max_response_len:]
                self.send_long_message(say, remaining, thread_ts)
        except Exception:
            self.send_long_message(say, response, thread_ts)

        # 첨부 파일 처리
        if result.attachments:
            for file_path in result.attachments:
                success, msg = self.upload_file_to_slack(client, channel, thread_ts, file_path)
                if not success:
                    say(text=f"⚠️ {msg}", thread_ts=thread_ts)

    def _handle_restart_marker(self, result, session, thread_ts, say):
        """재기동 마커 처리"""
        restart_type = RestartType.UPDATE if result.update_requested else RestartType.RESTART
        type_name = "업데이트" if result.update_requested else "재시작"

        running_count = self.get_running_session_count() - 1

        if running_count > 0:
            logger.info(f"{type_name} 마커 감지 - 다른 세션 {running_count}개 실행 중, 확인 필요")
            say(text=f"코드가 변경되었습니다. 다른 대화가 진행 중이어서 확인이 필요합니다.", thread_ts=thread_ts)
            self.send_restart_confirmation(
                client=None,  # Not needed for this call path
                channel=Config.TRELLO_NOTIFY_CHANNEL,
                restart_type=restart_type,
                running_count=running_count,
                user_id=session.user_id,
                original_thread_ts=thread_ts
            )
        else:
            logger.info(f"{type_name} 마커 감지 - 다른 실행 중인 세션 없음, 즉시 {type_name}")
            say(text=f"코드가 변경되었습니다. {type_name}합니다...", thread_ts=thread_ts)
            self.restart_manager.force_restart(restart_type)

    def _handle_error(
        self, error, is_trello_mode, trello_card, session,
        channel, last_msg_ts, main_msg_ts, say, client
    ):
        """오류 결과 처리"""
        error_msg = f"오류가 발생했습니다: {error}"

        if is_trello_mode:
            # 이전 상태 리액션 제거 후 에러 리액션 추가
            prev_reaction = TRELLO_REACTIONS["executing"] if trello_card.has_execute else TRELLO_REACTIONS["planning"]
            _remove_reaction(client, channel, main_msg_ts, prev_reaction)
            _add_reaction(client, channel, main_msg_ts, TRELLO_REACTIONS["error"])

            header = _build_trello_header(trello_card, session.session_id or "")
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
        channel, thread_ts, last_msg_ts, main_msg_ts, say, client
    ):
        """예외 처리"""
        error_msg = f"오류가 발생했습니다: {str(e)}"

        if is_trello_mode:
            try:
                # 이전 상태 리액션 제거 후 에러 리액션 추가
                prev_reaction = TRELLO_REACTIONS["executing"] if trello_card.has_execute else TRELLO_REACTIONS["planning"]
                _remove_reaction(client, channel, main_msg_ts, prev_reaction)
                _add_reaction(client, channel, main_msg_ts, TRELLO_REACTIONS["error"])

                header = _build_trello_header(trello_card, session.session_id or "")
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
                continuation_hint = "`이 대화를 이어가려면 댓글을 달아주세요.`"
                error_text = f"❌ {error_msg}\n\n{continuation_hint}"
                client.chat_update(
                    channel=channel,
                    ts=last_msg_ts,
                    text=error_text
                )
            except Exception:
                say(text=f"❌ {error_msg}", thread_ts=thread_ts)
