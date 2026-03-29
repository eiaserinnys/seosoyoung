"""credential_ui.py 및 credential 액션 핸들러 단위 테스트

게이지 바 렌더링, Block Kit 메시지 구조, 알림 전송, 버튼 클릭 핸들러를 테스트합니다.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from seosoyoung.slackbot.handlers.credential_ui import (
    render_gauge,
    format_time_remaining,
    format_expiry_date,
    render_rate_limit_line,
    build_credential_alert_blocks,
    build_credential_alert_text,
    send_credential_alert,
)


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


# ── format_expiry_date ───────────────────────────────────────


class TestFormatExpiryDate:
    def test_none(self):
        result = format_expiry_date(None)
        assert "알 수 없음" in result

    def test_valid_ms_timestamp(self):
        """미래 밀리초 타임스탬프 → 유효 표시"""
        future_ms = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000)
        result = format_expiry_date(future_ms)
        assert ":white_check_mark:" in result
        assert "인증 유효 기간:" in result
        assert "년" in result
        assert "월" in result
        assert "일" in result

    def test_expired_ms_timestamp(self):
        """과거 밀리초 타임스탬프 → 무효 표시"""
        past_ms = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1000)
        result = format_expiry_date(past_ms)
        assert ":warning:" in result
        assert "(무효)" in result

    def test_valid_iso_string(self):
        """미래 ISO 문자열 → 유효 표시"""
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        result = format_expiry_date(future)
        assert ":white_check_mark:" in result

    def test_expired_iso_string(self):
        """과거 ISO 문자열 → 무효 표시"""
        past = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        result = format_expiry_date(past)
        assert ":warning:" in result
        assert "(무효)" in result

    def test_invalid_string(self):
        result = format_expiry_date("invalid")
        assert "알 수 없음" in result

    def test_zero_timestamp(self):
        """expires_at=0 은 Unix epoch(1970) 으로 만료 처리"""
        result = format_expiry_date(0)
        assert ":warning:" in result
        assert "(무효)" in result

    def test_negative_timestamp(self):
        """음수 타임스탬프는 과거 날짜로 만료 처리"""
        result = format_expiry_date(-1000)
        # epoch 이전이므로 만료, 또는 OSError 시 알 수 없음
        assert ":warning:" in result or "알 수 없음" in result

    def test_real_credential_timestamp(self):
        """실제 크레덴셜 형식의 밀리초 타임스탬프"""
        # 2026-02-05 경 (1770300031040ms)
        result = format_expiry_date(1770300031040)
        assert "인증 유효 기간:" in result
        assert "2026년" in result
        assert "2월" in result

    def test_float_timestamp(self):
        """float 타임스탬프도 정상 처리"""
        future_ms = (datetime.now(timezone.utc) + timedelta(days=5)).timestamp() * 1000
        result = format_expiry_date(future_ms)
        assert ":white_check_mark:" in result

    def test_kst_date_display(self):
        """KST 기준 날짜가 표시되는지 확인"""
        # UTC 2026-03-06 20:00:00 → KST 2026-03-07 05:00:00
        utc_dt = datetime(2026, 3, 6, 20, 0, 0, tzinfo=timezone.utc)
        ms = int(utc_dt.timestamp() * 1000)
        result = format_expiry_date(ms)
        # KST로는 3월 7일
        assert "3월 7일" in result


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


# ── build_credential_alert_blocks ────────────────────────────


class TestBuildCredentialAlertBlocks:
    def test_structure(self):
        blocks = build_credential_alert_blocks(0.95, "five_hour")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"

    def test_section_content_five_hour(self):
        blocks = build_credential_alert_blocks(0.95, "five_hour")
        text = blocks[0]["text"]["text"]
        assert "사용량 경고" in text
        assert "5시간" in text
        assert "95%" in text

    def test_section_content_seven_day(self):
        blocks = build_credential_alert_blocks(0.80, "seven_day")
        text = blocks[0]["text"]["text"]
        assert "7일" in text
        assert "80%" in text

    def test_unknown_rate_type_passthrough(self):
        blocks = build_credential_alert_blocks(0.70, "hourly")
        text = blocks[0]["text"]["text"]
        assert "hourly" in text
        assert "70%" in text


# ── build_credential_alert_text ──────────────────────────────


class TestBuildCredentialAlertText:
    def test_five_hour(self):
        text = build_credential_alert_text(0.80, "five_hour")
        assert "사용량 경고" in text
        assert "5시간" in text
        assert "80%" in text

    def test_seven_day(self):
        text = build_credential_alert_text(0.60, "seven_day")
        assert "7일" in text
        assert "60%" in text


# ── send_credential_alert ────────────────────────────────────


class TestSendCredentialAlert:
    def _reset_cooldown(self):
        import seosoyoung.slackbot.handlers.credential_ui as mod
        mod._last_alert_time = 0.0

    def test_sends_message(self):
        self._reset_cooldown()
        client = MagicMock()
        data = {"utilization": 0.95, "rate_limit_type": "five_hour"}

        send_credential_alert(client, "C123", data)
        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C123"
        assert "blocks" in call_kwargs
        assert "text" in call_kwargs

    def test_skips_missing_utilization(self):
        self._reset_cooldown()
        client = MagicMock()

        send_credential_alert(client, "C123", {"rate_limit_type": "five_hour"})
        client.chat_postMessage.assert_not_called()

    def test_cooldown(self):
        self._reset_cooldown()
        client = MagicMock()
        data = {"utilization": 0.95, "rate_limit_type": "five_hour"}

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
        data = {"utilization": 0.95, "rate_limit_type": "five_hour"}

        # 예외가 외부로 전파되지 않아야 함
        send_credential_alert(client, "C123", data)
