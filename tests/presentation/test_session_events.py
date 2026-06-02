"""외부 session event를 Slack 스레드에 표시하는 정책 테스트."""

from unittest.mock import MagicMock

from seosoyoung.slackbot.presentation.session_events import (
    format_external_user_message,
    get_caller_info,
    is_slack_origin_event,
    post_external_user_message,
    source_label,
)


def test_get_caller_info_accepts_snake_and_camel_case():
    assert get_caller_info({"caller_info": {"source": "browser"}}) == {"source": "browser"}
    assert get_caller_info({"callerInfo": {"source": "soul-app"}}) == {"source": "soul-app"}


def test_source_label_mapping_and_fallback():
    assert source_label({"source": "browser"}) == "[웹]"
    assert source_label({"source": "web"}) == "[웹]"
    assert source_label({"source": "soul-app"}) == "[모바일]"
    assert source_label({"source": "agent"}) == "[에이전트]"
    assert source_label({"source": "api"}) == "[API]"
    assert source_label({"source": "llm"}) == "[API]"
    assert source_label({"source": "system"}) == "[시스템]"
    assert source_label({"source": "unknown"}) == "[외부]"
    assert source_label(None) == "[외부]"


def test_format_external_user_message_uses_display_name_and_text():
    text = format_external_user_message(
        {
            "text": "다음 작업 진행해줘",
            "caller_info": {
                "source": "browser",
                "display_name": "Jubok Kim",
            },
        }
    )

    assert text == "[웹] Jubok Kim: 다음 작업 진행해줘"


def test_format_external_user_message_falls_back_to_user_id_and_content():
    text = format_external_user_message(
        {
            "content": "모바일 입력",
            "callerInfo": {
                "source": "soul-app",
                "user_id": "U123",
            },
        }
    )

    assert text == "[모바일] U123: 모바일 입력"


def test_slack_origin_same_thread_is_echo():
    event_data = {
        "text": "슬랙에서 이미 보낸 입력",
        "caller_info": {
            "source": "slack",
            "slack": {
                "channel_id": "C123",
                "thread_ts": "1000.0001",
                "user_id": "U123",
            },
        },
    }

    assert is_slack_origin_event(event_data, channel="C123", thread_ts="1000.0001")


def test_slack_origin_without_thread_metadata_is_still_echo():
    event_data = {
        "text": "슬랙 입력",
        "caller_info": {"source": "slack"},
    }

    assert is_slack_origin_event(event_data, channel="C123", thread_ts="1000.0001")


def test_browser_origin_is_not_echo():
    event_data = {
        "text": "웹 입력",
        "caller_info": {"source": "browser"},
    }

    assert not is_slack_origin_event(event_data, channel="C123", thread_ts="1000.0001")


def test_post_external_user_message_posts_thread_reply():
    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "1000.0002"}

    ts = post_external_user_message(
        client,
        channel="C123",
        thread_ts="1000.0001",
        event_data={
            "text": "외부 입력",
            "caller_info": {"source": "browser", "display_name": "Jubok Kim"},
        },
    )

    assert ts == "1000.0002"
    client.chat_postMessage.assert_called_once_with(
        channel="C123",
        thread_ts="1000.0001",
        text="[웹] Jubok Kim: 외부 입력",
    )

