"""sdk_compat 모듈 테스트

rate_limit_event 각 status별 동작, unknown type skip, 진짜 파싱 에러 검증.
"""

import pytest

from seosoyoung.slackbot.claude.sdk_compat import ParseAction, classify_parse_error


class TestClassifyParseError:
    """classify_parse_error 함수 테스트"""

    # --- rate_limit_event ---

    def test_rate_limit_allowed(self):
        data = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}}
        action, msg_type = classify_parse_error(data)
        assert action is ParseAction.CONTINUE
        assert msg_type == "rate_limit_event"

    def test_rate_limit_allowed_warning(self):
        data = {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "allowed_warning",
                "rateLimitType": "seven_day",
                "utilization": 0.51,
            },
        }
        action, msg_type = classify_parse_error(data)
        assert action is ParseAction.CONTINUE
        assert msg_type == "rate_limit_event"

    def test_rate_limit_rejected(self):
        """rejected도 CONTINUE (Agent SDK 동작 일치)"""
        data = {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "rejected",
                "rateLimitType": "five_hour",
                "resetsAt": 1700000000,
            },
        }
        action, msg_type = classify_parse_error(data)
        assert action is ParseAction.CONTINUE
        assert msg_type == "rate_limit_event"

    def test_rate_limit_rate_limited(self):
        """rate_limited도 CONTINUE"""
        data = {
            "type": "rate_limit_event",
            "rate_limit_info": {"status": "rate_limited"},
        }
        action, msg_type = classify_parse_error(data)
        assert action is ParseAction.CONTINUE
        assert msg_type == "rate_limit_event"

    def test_rate_limit_unknown_status(self):
        """미래의 알 수 없는 status도 CONTINUE"""
        data = {
            "type": "rate_limit_event",
            "rate_limit_info": {"status": "some_future_status"},
        }
        action, msg_type = classify_parse_error(data)
        assert action is ParseAction.CONTINUE
        assert msg_type == "rate_limit_event"

    def test_rate_limit_empty_info(self):
        """rate_limit_info가 비어있어도 CONTINUE"""
        data = {"type": "rate_limit_event"}
        action, msg_type = classify_parse_error(data)
        assert action is ParseAction.CONTINUE
        assert msg_type == "rate_limit_event"

    # --- unknown type (forward-compatible) ---

    def test_unknown_type_skipped(self):
        """미래의 알 수 없는 메시지 타입은 CONTINUE"""
        data = {"type": "new_feature_event", "payload": {"key": "value"}}
        action, msg_type = classify_parse_error(data)
        assert action is ParseAction.CONTINUE
        assert msg_type == "new_feature_event"

    def test_unknown_type_another(self):
        data = {"type": "debug_info_event"}
        action, msg_type = classify_parse_error(data)
        assert action is ParseAction.CONTINUE
        assert msg_type == "debug_info_event"

    # --- 진짜 파싱 에러 (RAISE) ---

    def test_no_type_field_raises(self):
        """type 필드가 없는 딕셔너리 → RAISE"""
        data = {"message": "some broken data"}
        action, msg_type = classify_parse_error(data)
        assert action is ParseAction.RAISE
        assert msg_type is None

    def test_none_data_raises(self):
        """data가 None → RAISE"""
        action, msg_type = classify_parse_error(None)
        assert action is ParseAction.RAISE
        assert msg_type is None

    def test_non_dict_data_raises(self):
        """data가 dict가 아닌 경우 → RAISE"""
        action, msg_type = classify_parse_error("not a dict")
        assert action is ParseAction.RAISE
        assert msg_type is None

    def test_empty_dict_raises(self):
        """빈 딕셔너리 → type이 None이므로 RAISE"""
        action, msg_type = classify_parse_error({})
        assert action is ParseAction.RAISE
        assert msg_type is None
