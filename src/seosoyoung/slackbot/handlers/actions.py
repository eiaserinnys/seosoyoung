"""재시작 버튼, AskUserQuestion 응답, 크레덴셜 프로필 관리 액션 핸들러"""

import json
import logging
import re
import urllib.request
import urllib.error

from seosoyoung.slackbot.config import Config
from seosoyoung.slackbot.restart import RestartType, RestartRequest

logger = logging.getLogger(__name__)


def send_restart_confirmation(
    client,
    channel: str,
    restart_type: RestartType,
    running_count: int,
    user_id: str,
    original_thread_ts: str | None = None
) -> None:
    """재시작 확인 메시지를 인터랙티브 버튼과 함께 전송

    Args:
        client: Slack client
        channel: 알림 채널 ID
        restart_type: 재시작 유형
        running_count: 실행 중인 대화 수
        user_id: 요청한 사용자 ID
        original_thread_ts: 원래 요청 메시지의 스레드 ts (있으면)
    """
    type_name = "업데이트" if restart_type == RestartType.UPDATE else "재시작"

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"현재 *{running_count}개*의 대화가 진행 중입니다. {Config.emoji.text_restart_trouble}\n"
                        f"지금 다시 시작하면 진행 중이던 대화가 끊깁니다.\n"
                        f"그래도 {type_name}할까요?"
            }
        },
        {
            "type": "actions",
            "block_id": "restart_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "예"},
                    "style": "danger",
                    "action_id": "restart_yes",
                    "value": f"{restart_type.value}|{user_id}|{original_thread_ts or ''}"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "아니오"},
                    "action_id": "restart_no",
                    "value": f"{restart_type.value}|{user_id}|{original_thread_ts or ''}"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "모든 대화 종료 후 재시작"},
                    "action_id": "restart_wait_all",
                    "value": f"{restart_type.value}|{user_id}|{original_thread_ts or ''}"
                }
            ]
        }
    ]

    try:
        client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=f"재시작 확인 필요: {running_count}개 대화 진행 중"
        )
        logger.info(f"재시작 확인 메시지 전송: channel={channel}, count={running_count}")
    except Exception as e:
        logger.error(f"재시작 확인 메시지 전송 실패: {e}")


def send_deploy_shutdown_popup(
    client,
    channel: str,
    running_count: int,
    restart_type: RestartType,
) -> None:
    """배포/재시작 시 활성 세션이 있을 때 사용자 확인 팝업을 전송

    graceful shutdown 요청이 왔을 때 활성 세션이 있으면
    사용자에게 즉시 종료 또는 세션 완료 후 종료를 선택하도록 한다.

    Args:
        client: Slack client
        channel: 알림 채널 ID
        running_count: 실행 중인 세션 수
        restart_type: 재시작 유형
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":warning: 진행 중인 세션이 *{running_count}개* 있습니다.\n"
                    f"종료 방식을 선택해주세요."
                ),
            },
        },
        {
            "type": "actions",
            "block_id": "deploy_shutdown_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "지금 종료"},
                    "style": "danger",
                    "action_id": "deploy_shutdown_yes",
                    "value": str(restart_type.value),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "세션 완료 후 종료"},
                    "action_id": "deploy_shutdown_wait",
                    "value": str(restart_type.value),
                },
            ],
        },
    ]

    try:
        client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=f"종료 확인 필요: {running_count}개 세션 진행 중",
        )
        logger.info(
            "배포 종료 확인 팝업 전송: channel=%s, sessions=%d",
            channel, running_count,
        )
    except Exception as e:
        logger.error(f"배포 종료 확인 팝업 전송 실패: {e}")


def register_action_handlers(app, dependencies: dict):
    """액션 핸들러 등록

    Args:
        app: Slack Bolt App 인스턴스
        dependencies: 의존성 딕셔너리
    """
    restart_manager = dependencies["restart_manager"]
    get_running_session_count = dependencies["get_running_session_count"]
    trello_watcher_ref = dependencies["trello_watcher_ref"]

    @app.action("restart_yes")
    def handle_restart_yes(ack, body, client):
        """예 버튼 클릭 - 즉시 재시작"""
        ack()

        value = body["actions"][0]["value"]
        restart_type_val, user_id, original_thread_ts = value.split("|")
        restart_type = RestartType(int(restart_type_val))

        channel = body["channel"]["id"]
        message_ts = body["message"]["ts"]

        type_name = "업데이트" if restart_type == RestartType.UPDATE else "재시작"

        try:
            client.chat_update(
                channel=channel,
                ts=message_ts,
                blocks=[],
                text=f"알겠습니다. {type_name}합니다."
            )
        except Exception as e:
            logger.error(f"메시지 업데이트 실패: {e}")

        logger.info(f"재시작 승인: type={restart_type.name}, user={user_id}")
        restart_manager.force_restart(restart_type)

    @app.action("restart_no")
    def handle_restart_no(ack, body, client):
        """아니오 버튼 클릭 - 취소"""
        ack()

        value = body["actions"][0]["value"]
        restart_type_val, user_id, original_thread_ts = value.split("|")

        channel = body["channel"]["id"]
        message_ts = body["message"]["ts"]

        try:
            client.chat_update(
                channel=channel,
                ts=message_ts,
                blocks=[],
                text="알겠습니다. 이후에 재시작을 시도하려면\n"
                     f"`{Config.bot.mention_name} update` 또는 `{Config.bot.mention_name} restart`라고 입력해주세요."
            )
        except Exception as e:
            logger.error(f"메시지 업데이트 실패: {e}")

        # 신규: pending 취소 (사용자가 "아니오"를 클릭했으므로 자동 등록된 pending 취소)
        restart_manager.cancel_restart()
        # 신규: trello watcher 재개 (handle_update_restart에서 자동 pause된 상태 복구)
        trello_watcher = trello_watcher_ref()
        if trello_watcher:
            trello_watcher.resume()
        logger.info(f"재시작 취소: user={user_id}")

    @app.action("restart_wait_all")
    def handle_restart_wait_all(ack, body, client):
        """모든 대화 종료 후 재시작 버튼 클릭"""
        ack()

        value = body["actions"][0]["value"]
        restart_type_val, user_id, original_thread_ts = value.split("|")
        restart_type = RestartType(int(restart_type_val))

        channel = body["channel"]["id"]
        message_ts = body["message"]["ts"]

        try:
            client.chat_update(
                channel=channel,
                ts=message_ts,
                blocks=[],
                text="알겠습니다, 모든 대화가 종료되면 재시작합니다.\n"
                     "재시작을 대기하는 동안은 새로운 대화를 시작하지 않습니다."
            )
        except Exception as e:
            logger.error(f"메시지 업데이트 실패: {e}")

        # 재시작 대기 요청 등록
        request = RestartRequest(
            restart_type=restart_type,
            requester_user_id=user_id,
            channel_id=channel,
            thread_ts=original_thread_ts if original_thread_ts else message_ts
        )
        restart_manager.request_restart(request)

        # 사용자가 버튼을 클릭하여 직접 대기를 선택했으므로 이 시점부터 신규 대화 차단
        restart_manager.confirm_shutdown()

        # Trello 워처 일시 중단
        trello_watcher = trello_watcher_ref()
        if trello_watcher:
            trello_watcher.pause()

        logger.info(f"재시작 대기 시작: type={restart_type.name}, user={user_id}")

        # 현재 실행 중인 세션이 없으면 즉시 재시작
        if get_running_session_count() == 0:
            restart_manager.check_and_restart_if_ready()

    @app.action("deploy_shutdown_yes")
    def handle_deploy_shutdown_yes(ack, body, client):
        """배포 시 '지금 종료' 버튼 클릭 - 즉시 종료"""
        ack()

        value = body["actions"][0]["value"]
        restart_type = RestartType(int(value))

        channel = body["channel"]["id"]
        message_ts = body["message"]["ts"]

        try:
            client.chat_update(
                channel=channel,
                ts=message_ts,
                blocks=[],
                text="알겠습니다, 지금 종료합니다.",
            )
        except Exception as e:
            logger.error(f"메시지 업데이트 실패: {e}")

        logger.info("배포 종료 승인 (즉시): type=%s", restart_type.name)
        restart_manager.force_restart(restart_type)

    @app.action("deploy_shutdown_wait")
    def handle_deploy_shutdown_wait(ack, body, client):
        """배포 시 '세션 완료 후 종료' 버튼 클릭 - 세션 종료 대기"""
        ack()

        value = body["actions"][0]["value"]
        restart_type = RestartType(int(value))

        channel = body["channel"]["id"]
        message_ts = body["message"]["ts"]

        try:
            client.chat_update(
                channel=channel,
                ts=message_ts,
                blocks=[],
                text="알겠습니다, 세션이 완료되면 종료합니다.",
            )
        except Exception as e:
            logger.error(f"메시지 업데이트 실패: {e}")

        logger.info("배포 종료 대기: type=%s", restart_type.name)

        # 시스템 종료 요청 등록 (세션 0 도달 시 자동 종료)
        result = restart_manager.request_system_shutdown(restart_type)
        if result:
            # 이미 세션이 없어서 즉시 종료됨
            return

        # 사용자가 '세션 완료 후 종료'를 선택했으므로 이 시점부터 신규 대화 차단
        restart_manager.confirm_shutdown()

        # Trello 워처 일시 중단
        trello_watcher = trello_watcher_ref()
        if trello_watcher:
            trello_watcher.pause()

    # --- AskUserQuestion 버튼 클릭 핸들러 ---

    @app.action(re.compile(r"input_request_.+"))
    def handle_input_request_response(ack, body, client):
        """AskUserQuestion 버튼 클릭 → 사용자 응답을 soul-server에 전달"""
        ack()

        action = body["actions"][0]
        value_str = action.get("value", "")
        channel = body["channel"]["id"]
        message_ts = body["message"]["ts"]

        # value 파싱: JSON 형식 {"rid", "q", "a", "sid"}
        try:
            value_data = json.loads(value_str)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"input_request: 잘못된 value JSON: {value_str!r}")
            return

        request_id = value_data.get("rid", "")
        question_text = value_data.get("q", "")
        selected_label = value_data.get("a", "")
        agent_session_id = value_data.get("sid", "")

        if not request_id or not agent_session_id:
            logger.warning(
                f"input_request: 필수 정보 누락: "
                f"request_id={request_id!r}, session_id={agent_session_id!r}"
            )
            return

        # 즉시 UI 갱신: 버튼을 응답 결과 텍스트로 교체
        try:
            from seosoyoung.slackbot.formatting import format_input_request_answered
            answers = {question_text: selected_label}
            display = format_input_request_answered(
                [{"question": question_text}],
                answers,
            )
            client.chat_update(
                channel=channel,
                ts=message_ts,
                blocks=[],
                text=display or f":white_check_mark: {selected_label}",
            )
        except Exception as e:
            logger.warning(f"input_request UI 갱신 실패: {e}")
            try:
                client.chat_update(
                    channel=channel,
                    ts=message_ts,
                    blocks=[],
                    text=f":white_check_mark: {selected_label}",
                )
            except Exception:
                pass

        # soul-server에 응답 전달
        _deliver_input_response_to_soul(
            agent_session_id=agent_session_id,
            request_id=request_id,
            question_text=question_text,
            selected_label=selected_label,
        )

    @app.action("oauth_profile_switch")
    def handle_oauth_profile_switch(ack, body, client):
        """OAuth 프로필 버튼 클릭 → 프로필 전환 후 메시지 갱신"""
        ack()

        action = body["actions"][0]
        profile_name = action["value"]
        channel = body["channel"]["id"]
        message_ts = body["message"]["ts"]

        soul_url = Config.claude.soul_url
        soul_token = Config.claude.soul_token

        def _http_get_json(url):
            req = urllib.request.Request(url, method="GET")
            req.add_header("Authorization", f"Bearer {soul_token}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())

        def _http_post_json(url, payload):
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Authorization", f"Bearer {soul_token}")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())

        try:
            # 1. 프로필 전환
            activate_result = _http_post_json(
                f"{soul_url}/auth/claude/profiles/activate",
                {"profile": profile_name},
            )
            if not activate_result.get("success"):
                error = activate_result.get("error", "알 수 없는 오류")
                client.chat_update(
                    channel=channel,
                    ts=message_ts,
                    blocks=[],
                    text=f"❌ 프로필 전환 실패: {error}",
                )
                return

            # 2. 갱신된 프로필 목록 조회
            profiles_result = _http_get_json(f"{soul_url}/auth/claude/profiles")
            node_id = profiles_result.get("node_id", "unknown")
            profiles = profiles_result.get("profiles", [])
            current = profiles_result.get("current_profile")

            # 3. 메시지 업데이트
            from seosoyoung.slackbot.handlers.commands import _build_profile_blocks
            blocks = _build_profile_blocks(node_id, profiles, current)
            client.chat_update(
                channel=channel,
                ts=message_ts,
                blocks=blocks,
                text=f"OAuth 프로필 전환 완료: {current or profile_name}",
            )
            logger.info(f"OAuth 프로필 전환: '{profile_name}' → 성공")

        except Exception as e:
            logger.error(f"OAuth 프로필 전환 오류: profile={profile_name!r}, error={e}")
            try:
                client.chat_update(
                    channel=channel,
                    ts=message_ts,
                    blocks=[],
                    text=f"❌ 프로필 전환 중 오류 발생: {e}",
                )
            except Exception:
                pass


def _deliver_input_response_to_soul(
    agent_session_id: str,
    request_id: str,
    question_text: str,
    selected_label: str,
) -> None:
    """soul-server에 AskUserQuestion 응답을 HTTP로 전달

    POST /sessions/{agent_session_id}/respond
    Body: {"request_id": "...", "answers": {"question_text": "selected_label"}}
    """
    soul_url = Config.claude.soul_url
    soul_token = Config.claude.soul_token

    url = f"{soul_url}/api/sessions/{agent_session_id}/respond"
    data = json.dumps({
        "request_id": request_id,
        "answers": {question_text: selected_label},
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {soul_token}")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())

        logger.info(
            f"input_request 응답 전달 성공: request_id={request_id}, "
            f"session={agent_session_id}, result={result}"
        )
    except Exception as e:
        logger.error(
            f"input_request 응답 전달 실패: request_id={request_id}, "
            f"session={agent_session_id}, error={e}"
        )

