"""Claude 실행 결과 처리

실행 결과(성공/실패/중단)에 따른 슬랙 메시지 응답 로직을 담당합니다.
"""

import logging
from typing import Any, Callable, Optional

from seosoyoung.slackbot.claude.message_formatter import (
    build_context_usage_bar,
    build_trello_header,
)
from seosoyoung.slackbot.claude.types import UpdateMessageFn

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
        show_context_usage: bool = False,
        restart_type_update: Any = None,
        restart_type_restart: Any = None,
    ):
        self.send_long_message = send_long_message
        self.restart_manager = restart_manager
        self.get_running_session_count = get_running_session_count
        self.send_restart_confirmation = send_restart_confirmation
        self.update_message_fn = update_message_fn
        self.trello_watcher_ref = trello_watcher_ref
        self.show_context_usage = show_context_usage
        self.restart_type_update = restart_type_update
        self.restart_type_restart = restart_type_restart

    def replace_thinking_message(
        self, client, channel: str, old_msg_ts: str,
        new_text: str, new_blocks: list, thread_ts: str = None
    ) -> str:
        """사고 과정 메시지를 최종 응답으로 교체 (chat_update)"""
        self.update_message_fn(client, channel, old_msg_ts, new_text, blocks=new_blocks)
        return old_msg_ts

    def handle_interrupted(self, ctx):
        """인터럽트로 중단된 실행의 사고 과정 메시지 정리"""
        try:
            if ctx.dm_channel_id and ctx.dm_last_reply_ts:
                try:
                    self.update_message_fn(ctx.client, ctx.dm_channel_id, ctx.dm_last_reply_ts,
                                   "> (중단됨)")
                except Exception as e:
                    logger.warning(f"DM 중단 메시지 업데이트 실패: {e}")

            target_ts = ctx.main_msg_ts if ctx.is_trello_mode else ctx.last_msg_ts
            if not target_ts:
                return

            if ctx.is_trello_mode:
                header = build_trello_header(ctx.trello_card, ctx.session.session_id or "")
                interrupted_text = f"{header}\n\n`(중단됨)`"
            else:
                interrupted_text = "> (중단됨)"

            self.update_message_fn(ctx.client, ctx.channel, target_ts, interrupted_text)
            logger.info(f"중단된 실행 메시지 업데이트: ts={target_ts}")
        except Exception as e:
            logger.warning(f"중단 메시지 업데이트 실패: {e}")

    def handle_success(self, ctx, result):
        """성공 결과 처리"""
        response = result.output or ""

        if not response.strip():
            self.handle_interrupted(ctx)
            return

        usage_bar = None
        if self.show_context_usage:
            usage_bar = build_context_usage_bar(result.usage)

        is_list_run_from_marker = bool(ctx.effective_role == "admin" and result.list_run)
        is_list_run_from_card = bool(
            ctx.trello_card and getattr(ctx.trello_card, "list_key", None) == "list_run"
        )
        is_list_run = is_list_run_from_marker or is_list_run_from_card

        if ctx.is_trello_mode:
            self.handle_trello_success(ctx, result, response, is_list_run, usage_bar)
        else:
            self.handle_normal_success(ctx, result, response, is_list_run, usage_bar)

        if ctx.effective_role == "admin":
            if result.update_requested or result.restart_requested:
                self.handle_restart_marker(
                    result, ctx.session, ctx.channel, ctx.thread_ts, ctx.say
                )

        if is_list_run_from_marker:
            self.handle_list_run_marker(
                result.list_run, ctx.channel, ctx.thread_ts, ctx.say, ctx.client
            )

    def handle_trello_success(
        self, ctx, result, response: str,
        is_list_run: bool, usage_bar: Optional[str],
    ):
        """트렐로 모드 성공 처리"""
        if ctx.dm_channel_id and ctx.dm_last_reply_ts:
            try:
                dm_final = response[:3800] if len(response) > 3800 else response
                self.update_message_fn(ctx.client, ctx.dm_channel_id, ctx.dm_last_reply_ts, dm_final)
            except Exception as e:
                logger.warning(f"DM 스레드 최종 메시지 업데이트 실패: {e}")

        final_session_id = result.session_id or ctx.session.session_id or ""
        header = build_trello_header(ctx.trello_card, final_session_id)
        footer = usage_bar or ""

        max_response_len = 3900 - len(header) - len(footer) - 20
        if len(response) <= max_response_len:
            final_text = f"{header}\n\n{response}"
            if footer:
                final_text = f"{final_text}\n\n{footer}"
        else:
            truncated = response[:max_response_len]
            final_text = f"{header}\n\n{truncated}..."
            if footer:
                final_text = f"{final_text}\n\n{footer}"

        final_blocks = [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": final_text}
        }]

        if is_list_run:
            self.update_message_fn(ctx.client, ctx.channel, ctx.main_msg_ts,
                           final_text, blocks=final_blocks)
        else:
            self.replace_thinking_message(
                ctx.client, ctx.channel, ctx.main_msg_ts,
                final_text, final_blocks, thread_ts=None,
            )

        if len(response) > max_response_len:
            self.send_long_message(ctx.say, response, ctx.thread_ts)

    def handle_normal_success(
        self, ctx, result, response: str,
        is_list_run: bool, usage_bar: Optional[str],
    ):
        """일반 모드(멘션) 성공 처리"""
        reply_thread_ts = ctx.thread_ts

        if not ctx.is_thread_reply:
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
                if usage_bar:
                    final_text = f"{final_text}\n\n{usage_bar}"
                final_blocks = [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": final_text}
                }]

                if is_list_run:
                    self.update_message_fn(ctx.client, ctx.channel, ctx.last_msg_ts,
                                   final_text, blocks=final_blocks)
                else:
                    self.replace_thinking_message(
                        ctx.client, ctx.channel, ctx.last_msg_ts,
                        final_text, final_blocks, thread_ts=reply_thread_ts,
                    )

                # 미리보기가 잘린 경우에만 전문을 스레드에 전송
                if is_truncated:
                    self.send_long_message(ctx.say, response, ctx.thread_ts)

            except Exception:
                self.send_long_message(ctx.say, response, ctx.thread_ts)
        else:
            display_response = response
            if usage_bar:
                display_response = f"{display_response}\n\n{usage_bar}"

            try:
                if len(display_response) <= 3900:
                    final_text = display_response
                    final_blocks = [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": final_text}
                    }]
                    self.replace_thinking_message(
                        ctx.client, ctx.channel, ctx.last_msg_ts,
                        final_text, final_blocks, thread_ts=reply_thread_ts,
                    )
                else:
                    truncated = display_response[:3900]
                    first_part = f"{truncated}..."
                    first_blocks = [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": first_part}
                    }]
                    self.replace_thinking_message(
                        ctx.client, ctx.channel, ctx.last_msg_ts,
                        first_part, first_blocks, thread_ts=reply_thread_ts,
                    )
                    remaining = display_response[3900:]
                    self.send_long_message(ctx.say, remaining, ctx.thread_ts)
            except Exception:
                self.send_long_message(ctx.say, display_response, ctx.thread_ts)

    def handle_restart_marker(self, result, session, channel, thread_ts, say):
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
                user_id=session.user_id,
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

    def handle_error(self, ctx, error):
        """오류 결과 처리

        ClaudeResult.error 또는 Exception에서 발생한 오류를 처리합니다.
        update_message 실패 시 ctx.say 폴백을 사용합니다.
        """
        error_msg = f"오류가 발생했습니다: {error}"

        if ctx.dm_channel_id and ctx.dm_last_reply_ts:
            try:
                self.update_message_fn(ctx.client, ctx.dm_channel_id, ctx.dm_last_reply_ts,
                               f"❌ {error_msg}")
            except Exception as e:
                logger.warning(f"DM 에러 메시지 업데이트 실패: {e}")

        if ctx.is_trello_mode:
            try:
                header = build_trello_header(ctx.trello_card, ctx.session.session_id or "")
                error_text = f"{header}\n\n❌ {error_msg}"
                self.update_message_fn(ctx.client, ctx.channel, ctx.main_msg_ts, error_text,
                               blocks=[{"type": "section",
                                        "text": {"type": "mrkdwn", "text": error_text}}])
            except Exception:
                ctx.say(text=f"❌ {error_msg}", thread_ts=ctx.thread_ts)
        else:
            try:
                error_text = f"❌ {error_msg}"
                self.update_message_fn(ctx.client, ctx.channel, ctx.last_msg_ts, error_text,
                               blocks=[{"type": "section",
                                        "text": {"type": "mrkdwn", "text": error_text}}])
            except Exception:
                ctx.say(text=f"❌ {error_msg}", thread_ts=ctx.thread_ts)

    def handle_exception(self, ctx, e: Exception):
        """예외 처리 — handle_error에 위임"""
        self.handle_error(ctx, str(e))
