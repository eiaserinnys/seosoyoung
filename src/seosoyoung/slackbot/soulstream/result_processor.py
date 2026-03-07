"""Claude 실행 결과 처리

실행 결과(성공/실패/중단)에 따른 슬랙 메시지 응답 로직을 담당합니다.
"""

import logging
from typing import Any, Callable, Optional

from seosoyoung.slackbot.soulstream.message_formatter import (
    PROGRESS_MAX_LEN,
    SLACK_MSG_MAX_LEN,
    build_trello_header,
)
from seosoyoung.slackbot.soulstream.types import UpdateMessageFn

logger = logging.getLogger(__name__)


class ResultProcessor:
    """Claude 실행 결과를 처리하여 슬랙에 응답

    성공/실패/중단 분기 처리, 트렐로/일반 모드 분기,
    재기동 마커 및 LIST_RUN 마커 핸들링을 담당합니다.
    """

    def __init__(
        self,
        send_long_message: Callable,
        restart_manager,
        get_running_session_count: Callable,
        send_restart_confirmation: Callable,
        update_message_fn: UpdateMessageFn,
        *,
        trello_watcher_ref: Optional[Callable] = None,
        restart_type_update: Any = None,
        restart_type_restart: Any = None,
    ):
        self.send_long_message = send_long_message
        self.restart_manager = restart_manager
        self.get_running_session_count = get_running_session_count
        self.send_restart_confirmation = send_restart_confirmation
        self.update_message_fn = update_message_fn
        self.trello_watcher_ref = trello_watcher_ref
        self.restart_type_update = restart_type_update
        self.restart_type_restart = restart_type_restart

    def replace_thinking_message(
        self, client, channel: str, old_msg_ts: str,
        new_text: str, new_blocks: list, thread_ts: str = None
    ) -> str:
        """사고 과정 메시지를 최종 응답으로 교체 (chat_update)"""
        self.update_message_fn(client, channel, old_msg_ts, new_text, blocks=new_blocks)
        return old_msg_ts

    def handle_interrupted(self, pctx):
        """인터럽트로 중단된 실행의 사고 과정 메시지 정리"""
        try:
            if pctx.dm_channel_id and pctx.dm_last_reply_ts:
                try:
                    self.update_message_fn(pctx.client, pctx.dm_channel_id, pctx.dm_last_reply_ts,
                                   "> (중단됨)")
                except Exception as e:
                    logger.warning(f"DM 중단 메시지 업데이트 실패: {e}")

            if pctx.is_trello_mode:
                target_ts = pctx.main_msg_ts
            else:
                target_ts = pctx.last_msg_ts
            if not target_ts:
                # placeholder 없음 — 새 메시지로 중단 알림
                pctx.say(text="> (중단됨)", thread_ts=pctx.thread_ts)
                return

            if pctx.is_trello_mode:
                header = build_trello_header(pctx.trello_card, pctx.session_id or "")
                interrupted_text = f"{header}\n\n`(중단됨)`"
            else:
                interrupted_text = "> (중단됨)"

            self.update_message_fn(pctx.client, pctx.channel, target_ts, interrupted_text)
            logger.info(f"중단된 실행 메시지 업데이트: ts={target_ts}")
        except Exception as e:
            logger.warning(f"중단 메시지 업데이트 실패: {e}")

    def handle_success(self, pctx, result):
        """성공 결과 처리"""
        response = result.output or ""

        if not response.strip():
            self.handle_interrupted(pctx)
            return

        is_list_run_from_marker = bool(pctx.effective_role == "admin" and result.list_run)
        is_list_run_from_card = bool(
            pctx.trello_card and getattr(pctx.trello_card, "list_key", None) == "list_run"
        )
        is_list_run = is_list_run_from_marker or is_list_run_from_card

        if pctx.is_trello_mode:
            self.handle_trello_success(pctx, result, response, is_list_run)
        else:
            self.handle_normal_success(pctx, result, response, is_list_run)

        if pctx.effective_role == "admin":
            if result.update_requested or result.restart_requested:
                self.handle_restart_marker(
                    result, pctx.channel, pctx.thread_ts, pctx.say,
                    user_id=pctx.user_id,
                )

        if is_list_run_from_marker:
            self.handle_list_run_marker(
                result.list_run, pctx.channel, pctx.thread_ts, pctx.say, pctx.client
            )

    def handle_trello_success(
        self, pctx, result, response: str,
        is_list_run: bool,
    ):
        """트렐로 모드 성공 처리"""
        if pctx.dm_channel_id and pctx.dm_last_reply_ts:
            try:
                dm_final = response[:PROGRESS_MAX_LEN] if len(response) > PROGRESS_MAX_LEN else response
                self.update_message_fn(pctx.client, pctx.dm_channel_id, pctx.dm_last_reply_ts, dm_final)
            except Exception as e:
                logger.warning(f"DM 스레드 최종 메시지 업데이트 실패: {e}")

        final_session_id = result.session_id or pctx.session_id or ""
        header = build_trello_header(pctx.trello_card, final_session_id)

        max_response_len = SLACK_MSG_MAX_LEN - len(header) - 20
        if len(response) <= max_response_len:
            final_text = f"{header}\n\n{response}"
        else:
            truncated = response[:max_response_len]
            final_text = f"{header}\n\n{truncated}..."

        final_blocks = [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": final_text}
        }]

        if pctx.main_msg_ts:
            if is_list_run:
                self.update_message_fn(pctx.client, pctx.channel, pctx.main_msg_ts,
                               final_text, blocks=final_blocks)
            else:
                self.replace_thinking_message(
                    pctx.client, pctx.channel, pctx.main_msg_ts,
                    final_text, final_blocks, thread_ts=None,
                )
        else:
            logger.warning("main_msg_ts is None — skipping chat.update, sending as new message")
            self.send_long_message(pctx.say, response, pctx.thread_ts)
            return

        if len(response) > max_response_len:
            self.send_long_message(pctx.say, response, pctx.thread_ts)

    def handle_normal_success(
        self, pctx, result, response: str,
        is_list_run: bool,
    ):
        """일반 모드(멘션) 성공 처리"""
        reply_thread_ts = pctx.thread_ts

        # placeholder가 없으면 (last_msg_ts=None) 새 메시지로 결과 게시
        if not pctx.last_msg_ts:
            self.send_long_message(pctx.say, response, pctx.thread_ts)
            return

        if not pctx.is_thread_reply:
            # 채널 최초 응답: 미리보기를 채널에, 전문은 스레드에
            try:
                lines = response.strip().split("\n")
                preview_lines = []
                for line in lines:
                    preview_lines.append(line)
                    if len(preview_lines) >= 3:
                        break
                channel_text = "\n".join(preview_lines)
                is_truncated = len(lines) > 3
                if is_truncated:
                    channel_text += "\n..."

                final_text = channel_text
                final_blocks = [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": final_text}
                }]

                if is_list_run:
                    self.update_message_fn(pctx.client, pctx.channel, pctx.last_msg_ts,
                                   final_text, blocks=final_blocks)
                else:
                    self.replace_thinking_message(
                        pctx.client, pctx.channel, pctx.last_msg_ts,
                        final_text, final_blocks, thread_ts=reply_thread_ts,
                    )

                # 미리보기가 잘린 경우에만 전문을 스레드에 전송
                if is_truncated:
                    self.send_long_message(pctx.say, response, pctx.thread_ts)

            except Exception:
                self.send_long_message(pctx.say, response, pctx.thread_ts)
        else:
            display_response = response

            try:
                if len(display_response) <= SLACK_MSG_MAX_LEN:
                    final_text = display_response
                    final_blocks = [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": final_text}
                    }]
                    self.replace_thinking_message(
                        pctx.client, pctx.channel, pctx.last_msg_ts,
                        final_text, final_blocks, thread_ts=reply_thread_ts,
                    )
                else:
                    truncated = display_response[:SLACK_MSG_MAX_LEN]
                    first_part = f"{truncated}..."
                    first_blocks = [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": first_part}
                    }]
                    self.replace_thinking_message(
                        pctx.client, pctx.channel, pctx.last_msg_ts,
                        first_part, first_blocks, thread_ts=reply_thread_ts,
                    )
                    remaining = display_response[SLACK_MSG_MAX_LEN:]
                    self.send_long_message(pctx.say, remaining, pctx.thread_ts)
            except Exception:
                self.send_long_message(pctx.say, display_response, pctx.thread_ts)

    def handle_restart_marker(self, result, channel, thread_ts, say, *, user_id=None):
        """재기동 마커 처리"""
        restart_type = self.restart_type_update if result.update_requested else self.restart_type_restart
        type_name = "업데이트" if result.update_requested else "재시작"

        running_count = self.get_running_session_count() - 1

        if running_count > 0:
            logger.info(f"{type_name} 마커 감지 - 다른 세션 {running_count}개 실행 중, 확인 필요")
            say(text=f"코드가 변경되었습니다. 다른 대화가 진행 중이어서 확인이 필요합니다.", thread_ts=thread_ts)
            self.send_restart_confirmation(
                client=None,
                channel=channel,
                restart_type=restart_type,
                running_count=running_count,
                user_id=user_id,
                original_thread_ts=thread_ts
            )
        else:
            logger.info(f"{type_name} 마커 감지 - 다른 실행 중인 세션 없음, 즉시 {type_name}")
            say(text=f"코드가 변경되었습니다. {type_name}합니다...", thread_ts=thread_ts)
            self.restart_manager.force_restart(restart_type)

    def handle_list_run_marker(
        self, list_name: str, channel: str, thread_ts: str, say, client
    ):
        """LIST_RUN 마커 처리 - 정주행 시작"""
        logger.info(f"리스트 정주행 요청: {list_name}")

        trello_watcher = self.trello_watcher_ref() if self.trello_watcher_ref else None
        if not trello_watcher:
            logger.warning("TrelloWatcher가 설정되지 않아 정주행을 시작할 수 없습니다.")
            say(
                text="❌ TrelloWatcher가 설정되지 않아 정주행을 시작할 수 없습니다.",
                thread_ts=thread_ts
            )
            return

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

            say(
                text=f"📋 리스트 정주행을 시작합니다: *{list_name}* ({len(cards)}개 카드)\n"
                     f"정주행 상태는 별도 스레드에서 확인하실 수 있습니다.",
                thread_ts=thread_ts
            )

            trello_watcher._start_list_run(list_id, list_name, cards)

        except Exception as e:
            logger.error(f"정주행 시작 실패: {e}")
            say(
                text=f"❌ 정주행 시작에 실패했습니다: {e}",
                thread_ts=thread_ts
            )

    def handle_error(self, pctx, error):
        """오류 결과 처리

        ClaudeResult.error 또는 Exception에서 발생한 오류를 처리합니다.
        update_message 실패 시 pctx.say 폴백을 사용합니다.
        """
        error_msg = f"오류가 발생했습니다: {error}"

        if pctx.dm_channel_id and pctx.dm_last_reply_ts:
            try:
                self.update_message_fn(pctx.client, pctx.dm_channel_id, pctx.dm_last_reply_ts,
                               f"❌ {error_msg}")
            except Exception as e:
                logger.warning(f"DM 에러 메시지 업데이트 실패: {e}")

        if pctx.is_trello_mode:
            if pctx.main_msg_ts:
                try:
                    header = build_trello_header(pctx.trello_card, pctx.session_id or "")
                    error_text = f"{header}\n\n❌ {error_msg}"
                    self.update_message_fn(pctx.client, pctx.channel, pctx.main_msg_ts, error_text,
                                   blocks=[{"type": "section",
                                            "text": {"type": "mrkdwn", "text": error_text}}])
                except Exception:
                    pctx.say(text=f"❌ {error_msg}", thread_ts=pctx.thread_ts)
            else:
                pctx.say(text=f"❌ {error_msg}", thread_ts=pctx.thread_ts)
        else:
            if not pctx.last_msg_ts:
                pctx.say(text=f"❌ {error_msg}", thread_ts=pctx.thread_ts)
            else:
                try:
                    error_text = f"❌ {error_msg}"
                    self.update_message_fn(pctx.client, pctx.channel, pctx.last_msg_ts, error_text,
                                   blocks=[{"type": "section",
                                            "text": {"type": "mrkdwn", "text": error_text}}])
                except Exception:
                    pctx.say(text=f"❌ {error_msg}", thread_ts=pctx.thread_ts)

    def handle_exception(self, pctx, e: Exception):
        """예외 처리 — handle_error에 위임"""
        self.handle_error(pctx, str(e))
