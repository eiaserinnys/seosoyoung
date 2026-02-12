"""재시작 버튼 액션 핸들러"""

import logging

from seosoyoung.config import Config
from seosoyoung.restart import RestartType, RestartRequest

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
                "text": f"현재 *{running_count}개*의 대화가 진행 중입니다. {Config.EMOJI_TEXT_RESTART_TROUBLE}\n"
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
                     "`@서소영 update` 또는 `@서소영 restart`라고 입력해주세요."
            )
        except Exception as e:
            logger.error(f"메시지 업데이트 실패: {e}")

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

        # Trello 워처 일시 중단
        trello_watcher = trello_watcher_ref()
        if trello_watcher:
            trello_watcher.pause()

        logger.info(f"재시작 대기 시작: type={restart_type.name}, user={user_id}")

        # 현재 실행 중인 세션이 없으면 즉시 재시작
        if get_running_session_count() == 0:
            restart_manager.check_and_restart_if_ready()
