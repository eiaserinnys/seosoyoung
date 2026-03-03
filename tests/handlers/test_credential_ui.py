"""credential_ui.py 및 credential 액션 핸들러 단위 테스트

게이지 바 렌더링, Block Kit 메시지 구조, 알림 전송, 버튼 클릭 핸들러를 테스트합니다.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from seosoyoung.slackbot.handlers.credential_ui import (
    render_gauge,
    format_time_remaining,
    render_rate_limit_line,
    render_profile_section,
    build_credential_alert_blocks,
    build_credential_alert_text,
    send_credential_alert,
)
from seosoyoung.slackbot.handlers.actions import activate_credential_profile


# ── render_gauge ──────────────────────────────────────────────


class TestRenderGauge:
    def test_zero(self):
        assert render_gauge(0.0) == "🟦🟦🟦🟦🟦🟦🟦🟦🟦🟦"

    def test_full(self):
        assert render_gauge(1.0) == "🟧🟧🟧🟧🟧🟧🟧🟧🟧🟧"

    def test_half(self):
        assert render_gauge(0.5) == "🟧🟧🟧🟧🟧🟦🟦🟦🟦🟦"

    def test_95_percent(self):
        result = render_gauge(0.95)
        assert result.count("🟧") == 9
        assert result.count("🟦") == 1

    def test_10_percent(self):
        result = render_gauge(0.1)
        assert result.count("🟧") == 1
        assert result.count("🟦") == 9

    def test_unknown(self):
        assert render_gauge("unknown") == "❓❓❓❓❓❓❓❓❓❓"

    def test_custom_length(self):
        assert render_gauge(0.5, bar_length=4) == "🟧🟧🟦🟦"

    def test_clamps_negative(self):
        assert render_gauge(-0.1) == "🟦🟦🟦🟦🟦🟦🟦🟦🟦🟦"

    def test_clamps_over_one(self):
        result = render_gauge(1.5)
        assert result.count("🟧") == 10


# ── format_time_remaining ────────────────────────────────────


class TestFormatTimeRemaining:
    def test_none(self):
        assert format_time_remaining(None) == ""

    def test_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert format_time_remaining(past) == "초기화 완료"

    def test_hours_and_minutes(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=1, minutes=30)).isoformat()
        result = format_time_remaining(future)
        assert "초기화까지" in result
        assert "1시간" in result

    def test_days_and_hours(self):
        future = (datetime.now(timezone.utc) + timedelta(days=3, hours=2, minutes=30)).isoformat()
        result = format_time_remaining(future)
        assert "3일" in result
        assert "시간" in result
        # 일 단위에서는 분 생략
        assert "분" not in result

    def test_minutes_only(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        result = format_time_remaining(future)
        assert "초기화까지" in result

    def test_less_than_one_minute(self):
        future = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
        result = format_time_remaining(future)
        assert "1분 미만" in result

    def test_invalid_string(self):
        assert format_time_remaining("invalid") == ""

    def test_timezone_naive_input(self):
        """timezone 정보 없는 ISO 문자열도 정상 처리"""
        naive_future = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        result = format_time_remaining(naive_future)
        assert "초기화까지" in result


# ── render_rate_limit_line ───────────────────────────────────


class TestRenderRateLimitLine:
    def test_normal(self):
        line = render_rate_limit_line("five_hour", 0.5, None)
        assert "5시간" in line
        assert "50%" in line

    def test_with_reset_time(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        line = render_rate_limit_line("seven_day", 0.3, future)
        assert "주간" in line
        assert "30%" in line
        assert "초기화까지" in line

    def test_unknown(self):
        line = render_rate_limit_line("five_hour", "unknown", None)
        assert "❓" in line
        assert "unknown" in line

    def test_zero_no_reset(self):
        line = render_rate_limit_line("five_hour", 0.0, None)
        assert "0%" in line

    def test_expired_reset(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        line = render_rate_limit_line("five_hour", 0.0, past)
        assert "초기화 완료" in line


# ── render_profile_section ───────────────────────────────────


class TestRenderProfileSection:
    def test_active_profile(self):
        profile = {
            "name": "linegames",
            "five_hour": {"utilization": 0.95, "resets_at": None},
            "seven_day": {"utilization": 0.51, "resets_at": None},
        }
        result = render_profile_section(profile, is_active=True)
        assert "*linegames*" in result
        assert "(활성)" in result
        assert "5시간" in result
        assert "주간" in result

    def test_inactive_profile(self):
        profile = {
            "name": "personal",
            "five_hour": {"utilization": 0.0, "resets_at": None},
            "seven_day": {"utilization": "unknown", "resets_at": None},
        }
        result = render_profile_section(profile, is_active=False)
        assert "*personal*" in result
        assert "(활성)" not in result

    def test_missing_state_defaults_to_unknown(self):
        profile = {"name": "empty"}
        result = render_profile_section(profile, is_active=False)
        assert "unknown" in result


# ── build_credential_alert_blocks ────────────────────────────


class TestBuildCredentialAlertBlocks:
    def _make_profiles(self):
        return [
            {
                "name": "linegames",
                "five_hour": {"utilization": 0.95, "resets_at": None},
                "seven_day": {"utilization": 0.51, "resets_at": None},
            },
            {
                "name": "personal",
                "five_hour": {"utilization": 0.0, "resets_at": None},
                "seven_day": {"utilization": "unknown", "resets_at": None},
            },
        ]

    def test_structure(self):
        blocks = build_credential_alert_blocks("linegames", self._make_profiles())

        # section block + actions block
        assert len(blocks) == 2
        assert blocks[0]["type"] == "section"
        assert blocks[1]["type"] == "actions"

    def test_section_content(self):
        blocks = build_credential_alert_blocks("linegames", self._make_profiles())
        text = blocks[0]["text"]["text"]
        assert "크레덴셜 사용량 알림" in text
        assert "linegames" in text
        assert "personal" in text

    def test_buttons(self):
        blocks = build_credential_alert_blocks("linegames", self._make_profiles())
        buttons = blocks[1]["elements"]
        # 프로필 전환 버튼 2개 + 프로필 관리 버튼 1개
        assert len(buttons) == 3

        # 활성 프로필 버튼: (현재) 표시, style 없음
        assert "(현재)" in buttons[0]["text"]["text"]
        assert "style" not in buttons[0]

        # 비활성 프로필 버튼: style=primary
        assert "(현재)" not in buttons[1]["text"]["text"]
        assert buttons[1]["style"] == "primary"

        # 프로필 관리 버튼
        assert buttons[2]["action_id"] == "credential_list_profiles"

    def test_action_ids(self):
        blocks = build_credential_alert_blocks("linegames", self._make_profiles())
        buttons = blocks[1]["elements"]
        assert buttons[0]["action_id"] == "credential_switch_linegames"
        assert buttons[0]["value"] == "linegames"
        assert buttons[1]["action_id"] == "credential_switch_personal"
        assert buttons[1]["value"] == "personal"

    def test_single_profile(self):
        profiles = [
            {
                "name": "only",
                "five_hour": {"utilization": 0.5, "resets_at": None},
                "seven_day": {"utilization": 0.0, "resets_at": None},
            },
        ]
        blocks = build_credential_alert_blocks("only", profiles)
        assert len(blocks) == 2
        buttons = blocks[1]["elements"]
        # 프로필 전환 버튼 1개 + 프로필 관리 버튼 1개
        assert len(buttons) == 2
        assert "(현재)" in buttons[0]["text"]["text"]
        assert buttons[1]["action_id"] == "credential_list_profiles"


# ── build_credential_alert_text ──────────────────────────────


class TestBuildCredentialAlertText:
    def test_fallback_text(self):
        profiles = [
            {
                "name": "work",
                "five_hour": {"utilization": 0.8, "resets_at": None},
                "seven_day": {"utilization": 0.0, "resets_at": None},
            },
        ]
        text = build_credential_alert_text("work", profiles)
        assert "크레덴셜 사용량 알림" in text
        assert "work" in text


# ── send_credential_alert ────────────────────────────────────


class TestSendCredentialAlert:
    def _reset_cooldown(self):
        import seosoyoung.slackbot.handlers.credential_ui as mod
        mod._last_alert_time = 0.0

    def test_sends_message(self):
        self._reset_cooldown()
        client = MagicMock()
        data = {
            "active_profile": "linegames",
            "profiles": [
                {
                    "name": "linegames",
                    "five_hour": {"utilization": 0.95, "resets_at": None},
                    "seven_day": {"utilization": 0.5, "resets_at": None},
                },
            ],
        }

        send_credential_alert(client, "C123", data)
        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C123"
        assert "blocks" in call_kwargs
        assert "text" in call_kwargs

    def test_skips_empty_profiles(self):
        self._reset_cooldown()
        client = MagicMock()

        send_credential_alert(client, "C123", {"active_profile": "x", "profiles": []})
        client.chat_postMessage.assert_not_called()

    def test_cooldown(self):
        self._reset_cooldown()
        client = MagicMock()
        data = {
            "active_profile": "test",
            "profiles": [
                {
                    "name": "test",
                    "five_hour": {"utilization": 0.95, "resets_at": None},
                    "seven_day": {"utilization": 0.0, "resets_at": None},
                },
            ],
        }

        # 첫 번째: 전송됨
        send_credential_alert(client, "C123", data)
        assert client.chat_postMessage.call_count == 1

        # 두 번째: 쿨다운 중이라 무시됨
        send_credential_alert(client, "C123", data)
        assert client.chat_postMessage.call_count == 1

    def test_handles_send_error(self):
        self._reset_cooldown()
        client = MagicMock()
        client.chat_postMessage.side_effect = Exception("Slack error")
        data = {
            "active_profile": "test",
            "profiles": [
                {
                    "name": "test",
                    "five_hour": {"utilization": 0.95, "resets_at": None},
                    "seven_day": {"utilization": 0.0, "resets_at": None},
                },
            ],
        }

        # 예외가 외부로 전파되지 않아야 함
        send_credential_alert(client, "C123", data)


# ── activate_credential_profile (버튼 클릭 핸들러) ───────────


class TestActivateCredentialProfile:
    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_successful_switch(self, mock_urlopen):
        """프로필 전환 성공 시 메시지 업데이트"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = MagicMock()
        activate_credential_profile("personal", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        call_kwargs = client.chat_update.call_args[1]
        assert "✅" in call_kwargs["text"]
        assert "personal" in call_kwargs["text"]

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_failed_switch(self, mock_urlopen):
        """프로필 전환 실패 시 에러 메시지"""
        mock_urlopen.side_effect = Exception("Connection refused")

        client = MagicMock()
        activate_credential_profile("broken", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        call_kwargs = client.chat_update.call_args[1]
        assert "❌" in call_kwargs["text"]
        assert "broken" in call_kwargs["text"]

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_api_call_format(self, mock_urlopen):
        """Soul API 호출 형식 확인 (URL, 메서드, 인증 헤더)"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = MagicMock()
        activate_credential_profile("work", "C123", "ts123", client)

        # urlopen 호출 확인
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert "/profiles/work/activate" in req.full_url
        assert req.method == "POST"
        assert req.get_header("Authorization").startswith("Bearer ")

    def test_invalid_profile_name_rejected(self):
        """유효하지 않은 프로필 이름은 API 호출 없이 거부"""
        client = MagicMock()
        activate_credential_profile("../etc/passwd", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        call_kwargs = client.chat_update.call_args[1]
        assert "유효하지 않은" in call_kwargs["text"]

    def test_empty_profile_name_rejected(self):
        """빈 프로필 이름 거부"""
        client = MagicMock()
        activate_credential_profile("", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        assert "유효하지 않은" in client.chat_update.call_args[1]["text"]
