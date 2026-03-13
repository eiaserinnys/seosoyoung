"""rescue-bot 메인 모듈 (메인 봇 기본 대화 기능 완전 복제)

슬랙 멘션/스레드 메시지 → Claude Code SDK 직접 호출 → 결과 응답
soul 서버를 경유하지 않는 독립 경량 봇입니다.

메인 봇에서 복제한 기능:
- SessionManager 기반 세션 관리
- 인터벤션 (interrupt → pending prompt → while loop)
- on_compact 컴팩션 알림
- help/status/compact 명령어
- 슬랙 컨텍스트 블록 (채널/스레드/파일 정보)
- 긴 메시지 분할 전송

제외 기능:
- OM, Recall, 트렐로 연동, 번역, 채널 관찰
- 프로필 관리, 정주행, NPC 대화, Remote 모드
"""

# SDK 자동 설치 (임시 조치)
def _ensure_sdk_installed():
    """claude-agent-sdk가 없으면 자동 설치 시도"""
    try:
        import claude_agent_sdk  # noqa: F401
        return True
    except ImportError:
        import subprocess
        import sys
        print("[rescue-bot] claude-agent-sdk가 설치되어 있지 않습니다. 자동 설치를 시도합니다...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "claude-agent-sdk>=0.1.43",
                "--quiet"
            ])
            print("[rescue-bot] claude-agent-sdk 설치 완료!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[rescue-bot] claude-agent-sdk 설치 실패: {e}")
            print("[rescue-bot] 수동으로 설치해주세요: pip install claude-agent-sdk>=0.1.43")
            return False

_ensure_sdk_installed()

import logging
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from seosoyoung.rescue.config import RescueConfig
from seosoyoung.rescue.engine_adapter import create_runner, interrupt, compact_session_sync
from seosoyoung.rescue.claude.engine_types import EngineResult
from seosoyoung.rescue.reflect import reflect
from seosoyoung.rescue.session import Session, SessionManager
from seosoyoung.rescue.slack_utils import update_message

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("rescue-bot")


@dataclass
class PendingPrompt:
    """인터벤션 대기 중인 프롬프트 정보"""
    prompt: str
    msg_ts: str
    channel: str
    say: object
    client: object


class RescueBotApp:
    """rescue-bot 애플리케이션

    메인 봇의 ClaudeExecutor + 핸들러를 하나의 클래스로 통합한 경량 버전.
    """

    def __init__(self):
        # 세션 관리
        self.sessions = SessionManager()

        # 스레드별 실행 락 (동시 실행 방지)
        self._thread_locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

        # 인터벤션: 대기 중인 프롬프트
        self._pending_prompts: dict[str, PendingPrompt] = {}
        self._pending_lock = threading.Lock()

        # 인터벤션: 실행 중인 runner 추적
        self._active_runners: dict[str, object] = {}
        self._runners_lock = threading.Lock()

        # 봇 사용자 ID (런타임에 설정)
        self.bot_user_id: Optional[str] = None

    # === 세션 관리 ===

    def _get_or_create_session(self, thread_ts: str, channel: str) -> Session:
        """세션 조회, 없으면 생성"""
        return self.sessions.get_or_create(thread_ts, channel)

    def _get_session(self, thread_ts: str) -> Optional[Session]:
        """세션 조회"""
        return self.sessions.get(thread_ts)

    # === 동시 실행 제어 ===

    def _get_thread_lock(self, thread_ts: str) -> threading.Lock:
        """스레드별 락을 가져오거나 생성"""
        with self._locks_lock:
            if thread_ts not in self._thread_locks:
                self._thread_locks[thread_ts] = threading.Lock()
            return self._thread_locks[thread_ts]

    # === 텍스트 유틸리티 ===

    def _extract_command(self, text: str) -> str:
        """멘션에서 명령어 추출"""
        cleaned = re.sub(r"<@[A-Za-z0-9_]+>", "", text).strip()
        return cleaned.lower()

    def _strip_mention(self, text: str) -> str:
        """멘션 태그를 제거하고 순수 텍스트만 반환"""
        if self.bot_user_id:
            text = re.sub(rf"<@{re.escape(self.bot_user_id)}>", "", text)
        text = re.sub(r"<@\w+>", "", text)
        return text.strip()

    def _contains_bot_mention(self, text: str) -> bool:
        """텍스트에 봇 멘션이 포함되어 있는지 확인"""
        if not self.bot_user_id:
            return "<@" in text
        return f"<@{self.bot_user_id}>" in text

    def _should_ignore_event(self, event: dict) -> bool:
        """무시해야 할 이벤트인지 판단"""
        if event.get("bot_id"):
            return True
        if event.get("subtype") == "bot_message":
            return True
        return False

    # === 슬랙 컨텍스트 ===

    def _build_slack_context(
        self,
        channel: str,
        user_id: str,
        thread_ts: str,
    ) -> str:
        """슬랙 컨텍스트 블록 생성"""
        lines = [
            "<slack-context>",
            f"channel_id: {channel}",
            f"user_id: {user_id}",
            f"thread_ts: {thread_ts}",
            "</slack-context>",
        ]
        return "\n".join(lines)

    # === 긴 메시지 전송 ===

    def _send_long_message(self, say, text: str, thread_ts: str) -> None:
        """긴 메시지를 3900자 단위로 분할하여 전송"""
        remaining = text
        while remaining:
            chunk = remaining[:3900]
            remaining = remaining[3900:]
            say(text=chunk, thread_ts=thread_ts)

    # === 인터벤션 ===

    def _pop_pending(self, thread_ts: str) -> Optional[PendingPrompt]:
        """pending 프롬프트를 꺼내고 제거"""
        with self._pending_lock:
            return self._pending_prompts.pop(thread_ts, None)

    def _handle_intervention(
        self,
        thread_ts: str,
        prompt: str,
        msg_ts: str,
        channel: str,
        say,
        client,
    ):
        """인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우"""
        logger.info(f"인터벤션 발생: thread={thread_ts}")

        # pending에 저장 (최신 것으로 덮어씀)
        pending = PendingPrompt(
            prompt=prompt,
            msg_ts=msg_ts,
            channel=channel,
            say=say,
            client=client,
        )
        with self._pending_lock:
            self._pending_prompts[thread_ts] = pending

        # interrupt fire-and-forget (동기)
        with self._runners_lock:
            active_runner = self._active_runners.get(thread_ts)
        if active_runner:
            try:
                interrupt(thread_ts)
                logger.info(f"인터럽트 전송 완료: thread={thread_ts}")
            except Exception as e:
                logger.warning(f"인터럽트 전송 실패 (무시): thread={thread_ts}, {e}")

    # === 메시지 처리 핵심 로직 ===

    @reflect.capability(
        name="emergency_execution",
        description=(
            "Claude Code SDK를 직접 호출하여 "
            "soulstream 장애 시에도 명령을 처리"
        ),
    )
    def _process_message(
        self,
        prompt: str,
        thread_ts: str,
        channel: str,
        user_id: str,
        say,
        client,
        is_thread_reply: bool = False,
    ):
        """공통 메시지 처리 로직 (인터벤션 지원)"""
        lock = self._get_thread_lock(thread_ts)
        if not lock.acquire(blocking=False):
            # 인터벤션: pending에 저장 후 interrupt
            self._handle_intervention(
                thread_ts, prompt, "", channel, say, client,
            )
            return

        try:
            self._run_with_lock(
                prompt, thread_ts, channel, user_id, say, client,
                is_thread_reply=is_thread_reply,
            )
        finally:
            lock.release()

    def _run_with_lock(
        self,
        prompt: str,
        thread_ts: str,
        channel: str,
        user_id: str,
        say,
        client,
        is_thread_reply: bool = False,
    ):
        """락을 보유한 상태에서 실행 (while 루프로 pending 처리)"""
        # 첫 번째 실행
        self._execute_once(
            prompt, thread_ts, channel, user_id, say, client,
            is_thread_reply=is_thread_reply,
        )

        # pending 확인 → while 루프
        while True:
            pending = self._pop_pending(thread_ts)
            if not pending:
                break

            logger.info(f"인터벤션 이어가기: thread={thread_ts}")
            self._execute_once(
                pending.prompt, thread_ts, channel, user_id,
                pending.say, pending.client,
                is_thread_reply=True,
            )

    def _execute_once(
        self,
        prompt: str,
        thread_ts: str,
        channel: str,
        user_id: str,
        say,
        client,
        is_thread_reply: bool = False,
    ):
        """단일 Claude 실행"""
        session = self._get_or_create_session(thread_ts, channel)

        # 초기 메시지: blockquote 형태로 생각 과정 표시
        initial_text = "> 소영이 생각합니다..."
        initial_msg = client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=initial_text,
            blocks=[{
                "type": "section",
                "text": {"type": "mrkdwn", "text": initial_text}
            }]
        )
        last_msg_ts = initial_msg["ts"]

        # on_compact 콜백
        async def on_compact(trigger: str, message: str):
            try:
                if trigger == "auto":
                    text = "🔄 컨텍스트가 자동 압축됩니다..."
                else:
                    text = "📦 컨텍스트를 압축하는 중입니다..."
                say(text=text, thread_ts=thread_ts)
            except Exception as e:
                logger.warning(f"컴팩션 알림 전송 실패: {e}")

        # 슬랙 컨텍스트 주입
        slack_ctx = self._build_slack_context(channel, user_id, thread_ts)
        full_prompt = f"{slack_ctx}\n\n사용자의 질문: {prompt}\n\n위 컨텍스트를 참고하여 질문에 답변해주세요."

        # runner 생성 및 추적 (인터벤션용)
        runner = create_runner(thread_ts)
        with self._runners_lock:
            self._active_runners[thread_ts] = runner

        try:
            result = runner.run_sync(runner.run(
                prompt=full_prompt,
                session_id=session.session_id,
                on_compact=on_compact,
            ))

            # 세션 ID 업데이트
            if result.session_id and result.session_id != session.session_id:
                self.sessions.update_session_id(thread_ts, result.session_id)

            # 메시지 카운트 증가
            self.sessions.increment_message_count(thread_ts)

            # 결과 처리
            if result.interrupted:
                self._handle_interrupted(last_msg_ts, channel, client)
            elif result.success:
                self._handle_success(
                    result, channel, thread_ts, last_msg_ts, say, client,
                    is_thread_reply=is_thread_reply,
                )
            else:
                self._handle_error(
                    result.error, channel, thread_ts, last_msg_ts, say, client,
                    is_thread_reply=is_thread_reply,
                )

        except Exception as e:
            logger.exception(f"Claude 실행 오류: {e}")
            try:
                error_text = f"❌ 오류가 발생했습니다: {e}"
                update_message(client, channel, last_msg_ts, error_text)
            except Exception:
                say(text=f"❌ 오류가 발생했습니다: {e}", thread_ts=thread_ts)
        finally:
            with self._runners_lock:
                self._active_runners.pop(thread_ts, None)

    # === 결과 처리 ===

    def _handle_interrupted(self, last_msg_ts: str, channel: str, client):
        """인터럽트로 중단된 실행의 사고 과정 메시지 정리"""
        try:
            interrupted_text = "> (중단됨)"
            update_message(client, channel, last_msg_ts, interrupted_text)
        except Exception as e:
            logger.warning(f"중단 메시지 업데이트 실패: {e}")

    def _handle_success(
        self,
        result: EngineResult,
        channel: str,
        thread_ts: str,
        last_msg_ts: str,
        say,
        client,
        is_thread_reply: bool = False,
    ):
        """성공 결과 처리"""
        response = result.output or ""

        if not response.strip():
            self._handle_interrupted(last_msg_ts, channel, client)
            return

        continuation_hint = "`자세한 내용을 확인하시거나 대화를 이어가려면 스레드를 확인해주세요.`"

        if not is_thread_reply:
            # 채널 최초 응답: P(사고 과정)를 미리보기로 교체, 전문은 스레드에
            try:
                # 3줄 이내 미리보기
                lines = response.strip().split("\n")
                preview_lines = []
                for line in lines:
                    preview_lines.append(line)
                    if len(preview_lines) >= 3:
                        break
                channel_text = "\n".join(preview_lines)
                if len(lines) > 3:
                    channel_text += "\n..."

                final_text = f"{channel_text}\n\n{continuation_hint}"
                final_blocks = [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": final_text}
                }]
                update_message(client, channel, last_msg_ts, final_text, blocks=final_blocks)

                # 전문을 스레드에 전송
                self._send_long_message(say, response, thread_ts)

            except Exception:
                self._send_long_message(say, response, thread_ts)
        else:
            # 스레드 내 후속 대화
            display_response = response

            try:
                if len(display_response) <= 3900:
                    update_message(client, channel, last_msg_ts, display_response)
                else:
                    truncated = display_response[:3900] + "..."
                    update_message(client, channel, last_msg_ts, truncated)
                    remaining = display_response[3900:]
                    self._send_long_message(say, remaining, thread_ts)
            except Exception:
                self._send_long_message(say, display_response, thread_ts)

    def _handle_error(
        self,
        error: Optional[str],
        channel: str,
        thread_ts: str,
        last_msg_ts: str,
        say,
        client,
        is_thread_reply: bool = False,
    ):
        """오류 결과 처리"""
        error_msg = f"오류가 발생했습니다: {error}"
        if is_thread_reply:
            error_text = f"❌ {error_msg}"
        else:
            continuation_hint = "`이 대화를 이어가려면 댓글을 달아주세요.`"
            error_text = f"❌ {error_msg}\n\n{continuation_hint}"

        try:
            update_message(client, channel, last_msg_ts, error_text)
        except Exception:
            say(text=f"❌ {error_msg}", thread_ts=thread_ts)

    # === 명령어 처리 ===

    def _handle_help(self, say, thread_ts: str):
        """help 명령어"""
        say(
            text=(
                "📖 *사용법 (rescue-bot)*\n"
                "• `@rescue-bot <질문>` - 질문하기\n"
                "• `@rescue-bot help` - 도움말\n"
                "• `@rescue-bot status` - 상태 확인\n"
                "• `@rescue-bot compact` - 스레드 세션 컴팩트"
            ),
            thread_ts=thread_ts,
        )

    def _handle_status(self, say, thread_ts: str):
        """status 명령어"""
        say(
            text=(
                f"📊 *상태 (rescue-bot)*\n"
                f"• 작업 폴더: `{Path.cwd()}`\n"
                f"• 활성 세션: {self.sessions.count()}개"
            ),
            thread_ts=thread_ts,
        )

    def _handle_compact(self, say, client, thread_ts: str, parent_thread_ts: Optional[str]):
        """compact 명령어"""
        target_ts = parent_thread_ts
        if not target_ts:
            say(text="스레드에서 사용해주세요.", thread_ts=thread_ts)
            return

        session = self.sessions.get(target_ts)
        if not session or not session.session_id:
            say(text="활성 세션이 없습니다.", thread_ts=target_ts)
            return

        say(text="컴팩트 중입니다...", thread_ts=target_ts)

        try:
            compact_result = compact_session_sync(session.session_id)

            if compact_result.success:
                if compact_result.session_id:
                    self.sessions.update_session_id(target_ts, compact_result.session_id)
                say(text="컴팩트가 완료됐습니다.", thread_ts=target_ts)
            else:
                say(text=f"컴팩트에 실패했습니다: {compact_result.error}", thread_ts=target_ts)
        except Exception as e:
            logger.exception(f"compact 명령어 오류: {e}")
            say(text=f"컴팩트 중 오류가 발생했습니다: {e}", thread_ts=target_ts)

    # === 슬랙 이벤트 핸들러 ===

    def handle_mention(self, event, say, client):
        """멘션 이벤트 핸들러"""
        if self._should_ignore_event(event):
            return

        user_id = event.get("user", "")
        text = event.get("text", "")
        channel = event["channel"]
        ts = event["ts"]
        thread_ts = event.get("thread_ts")

        command = self._extract_command(text)

        # 관리자 명령어
        if command == "help":
            self._handle_help(say, thread_ts or ts)
            return
        if command == "status":
            self._handle_status(say, thread_ts or ts)
            return
        if command == "compact":
            self._handle_compact(say, client, ts, thread_ts)
            return

        # 스레드에서 멘션 + 세션 있음 → 스레드 메시지로 처리
        if thread_ts:
            session = self.sessions.get(thread_ts)
            if session:
                prompt = self._strip_mention(text)
                if not prompt:
                    return
                logger.info(f"스레드 멘션: user={user_id}, thread={thread_ts}")
                self._process_message(
                    prompt, thread_ts, channel, user_id, say, client,
                    is_thread_reply=True,
                )
                return

        # 일반 멘션: 세션 생성 + Claude 실행
        session_thread_ts = thread_ts or ts
        is_existing_thread = thread_ts is not None

        prompt = self._strip_mention(text)
        if not prompt:
            say(text="말씀해 주세요.", thread_ts=session_thread_ts)
            return

        logger.info(f"멘션 수신: user={user_id}, channel={channel}, thread_ts={session_thread_ts}")

        self._process_message(
            prompt, session_thread_ts, channel, user_id, say, client,
            is_thread_reply=is_existing_thread,
        )

    def handle_message(self, event, say, client):
        """스레드 메시지 핸들러"""
        if self._should_ignore_event(event):
            return

        # subtype이 있는 메시지는 무시
        if event.get("subtype"):
            return

        text = event.get("text", "")

        # 봇 멘션이 포함된 경우 handle_mention에서 처리 (중복 방지)
        if self._contains_bot_mention(text):
            return

        # 스레드 메시지인 경우만 처리
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return

        # 세션이 있는 스레드만 처리
        session = self.sessions.get(thread_ts)
        if not session or not session.session_id:
            return

        channel = event.get("channel", "")
        user_id = event.get("user", "")

        prompt = self._strip_mention(text)
        if not prompt:
            return

        logger.info(f"스레드 메시지: user={user_id}, channel={channel}, thread_ts={thread_ts}")

        self._process_message(
            prompt, thread_ts, channel, user_id, say, client,
            is_thread_reply=True,
        )


# === 모듈 레벨 진입점 ===

@reflect.capability(
    name="standalone_operation",
    description=(
        "메인 봇과 독립된 Slack App으로 동작하여 "
        "메인 봇 장애와 무관하게 가용"
    ),
)
def main():
    """rescue-bot 진입점"""
    import os
    logger.info("rescue-bot을 시작합니다...")

    RescueConfig.validate()

    # Management 서버 시작 (cogito /reflect + supervisor graceful shutdown)
    from seosoyoung.rescue.shutdown import create_management_app, start_management_server

    _SHUTDOWN_PORT = int(os.environ["RESCUE_SHUTDOWN_PORT"])

    def _on_shutdown():
        logger.info("rescue-bot: graceful shutdown")
        os._exit(0)

    _app = create_management_app(reflect, _on_shutdown)
    start_management_server(_app, _SHUTDOWN_PORT)

    # Slack 앱 초기화
    slack_app = App(token=RescueConfig.SLACK_BOT_TOKEN, logger=logger)

    # RescueBotApp 초기화
    bot = RescueBotApp()

    # 봇 사용자 ID 초기화
    try:
        auth_result = slack_app.client.auth_test()
        bot.bot_user_id = auth_result["user_id"]
        RescueConfig.BOT_USER_ID = bot.bot_user_id
        logger.info(f"BOT_USER_ID: {bot.bot_user_id}")
    except Exception as e:
        logger.error(f"봇 ID 조회 실패: {e}")

    # 이벤트 핸들러 등록
    @slack_app.event("app_mention")
    def _mention(event, say, client):
        bot.handle_mention(event, say, client)

    @slack_app.event("message")
    def _message(event, say, client):
        bot.handle_message(event, say, client)

    handler = SocketModeHandler(slack_app, RescueConfig.SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
