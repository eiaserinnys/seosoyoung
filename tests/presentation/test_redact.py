"""redact_sensitive() 유닛 테스트

민감 정보 REDACT 유틸리티의 각 패턴을 독립적으로 검증합니다.
"""

import pytest
from seosoyoung.slackbot.presentation.redact import redact_sensitive, REDACTED


class TestKnownPrefixPatterns:
    """잘 알려진 토큰 프리픽스 패턴 테스트"""

    def test_openai_api_key(self):
        """OpenAI/Anthropic sk- 형태 API 키를 가린다"""
        text = "API 키: sk-abcdefghijklmnopqrstu1234567890"
        result = redact_sensitive(text)
        assert REDACTED in result
        assert "sk-abcdefghijklmnopqrstu1234567890" not in result

    def test_slack_bot_token(self):
        """Slack xoxb- 형태 토큰을 가린다"""
        # 실제 토큰 형식과 유사하지만 테스트용 더미 데이터
        token_prefix = "xoxb"
        token_body = "-test-dummy-abcdefghijklmno"
        text = f"Slack 토큰: {token_prefix}{token_body}"
        result = redact_sensitive(text)
        assert REDACTED in result
        assert token_prefix not in result

    def test_slack_user_token(self):
        """Slack xoxp- 형태 토큰을 가린다"""
        # 실제 토큰 형식과 유사하지만 테스트용 더미 데이터
        token = "xoxp" + "-test-dummy-abcdefghijklmno"
        text = token
        result = redact_sensitive(text)
        assert REDACTED in result

    def test_github_pat_token(self):
        """GitHub ghp_ 형태 PAT 토큰을 가린다"""
        text = "GitHub PAT: ghp_abcdefghijklmnopqrstuvwxyz123456"
        result = redact_sensitive(text)
        assert REDACTED in result
        assert "ghp_" not in result

    def test_github_fine_grained_pat(self):
        """GitHub github_pat_ 형태 PAT를 가린다"""
        text = "token: github_pat_abcdefghijklmnopqrstuvwxyz1234567890"
        result = redact_sensitive(text)
        assert REDACTED in result
        assert "github_pat_" not in result

    def test_gitlab_pat(self):
        """GitLab glpat- 형태 PAT를 가린다"""
        text = "glpat-abcdefghijklmno1234567890"
        result = redact_sensitive(text)
        assert REDACTED in result

    def test_jwt_token(self):
        """JWT (eyJ...) 형태 토큰을 가린다"""
        text = "JWT: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        result = redact_sensitive(text)
        assert REDACTED in result

    def test_short_token_not_redacted(self):
        """짧은 토큰 형태는 가리지 않는다 (오탐 방지)"""
        text = "sk-short"
        result = redact_sensitive(text)
        # 20자 미만이므로 가리지 않음
        assert "sk-short" in result

    def test_multiple_tokens_in_text(self):
        """여러 토큰이 있으면 모두 가린다"""
        sk_token = "sk-" + "abcdefghijklmnopqrstu"
        xoxb_token = "xoxb" + "-test-dummy-abcdefghijklmno"
        text = f"key1={sk_token}, key2={xoxb_token}"
        result = redact_sensitive(text)
        assert "sk-" not in result
        assert "xoxb" not in result


class TestAuthHeaderPatterns:
    """Authorization 헤더 값 패턴 테스트"""

    def test_bearer_token(self):
        """Bearer 토큰 값을 가린다"""
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9abcdefghijk"
        result = redact_sensitive(text)
        assert REDACTED in result
        assert "eyJhbGciOiJSUzI1NiJ9abcdefghijk" not in result

    def test_bearer_scheme_preserved(self):
        """Bearer 스킴 단어는 유지된다"""
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9abcdefghijk"
        result = redact_sensitive(text)
        assert "Bearer" in result

    def test_token_scheme(self):
        """Token 스킴 값을 가린다"""
        text = "Authorization: Token abcdefghijklmnopqrstuvwxyz123456"
        result = redact_sensitive(text)
        assert REDACTED in result

    def test_basic_auth(self):
        """Basic 인증 값을 가린다"""
        text = "Authorization: Basic dXNlcjpwYXNzd29yZA=="
        result = redact_sensitive(text)
        assert REDACTED in result

    def test_auth_key_case_insensitive(self):
        """대소문자를 구분하지 않고 가린다"""
        text = "authorization: bearer secrettoken123456789012"
        result = redact_sensitive(text)
        assert "secrettoken123456789012" not in result


class TestEnvVarPatterns:
    """환경변수 스타일 KEY=value 패턴 테스트"""

    def test_api_key_assignment(self):
        """API_KEY=... 패턴의 값을 가린다"""
        text = "API_KEY=supersecretkey123456789"
        result = redact_sensitive(text)
        assert REDACTED in result
        assert "supersecretkey123456789" not in result

    def test_key_name_preserved(self):
        """API_KEY 키 이름은 유지된다"""
        text = "API_KEY=supersecretkey123456789"
        result = redact_sensitive(text)
        assert "API_KEY=" in result

    def test_token_assignment(self):
        """TOKEN=... 패턴의 값을 가린다"""
        text = "TOKEN=verylongsecrettoken12345678"
        result = redact_sensitive(text)
        assert REDACTED in result
        assert "verylongsecrettoken12345678" not in result

    def test_secret_assignment(self):
        """SECRET=... 패턴의 값을 가린다"""
        text = "MY_SECRET=anothersecretvalue9876"
        result = redact_sensitive(text)
        assert REDACTED in result

    def test_password_assignment(self):
        """PASSWORD=... 패턴의 값을 가린다"""
        text = "PASSWORD=correcthorsebatterystaple"
        result = redact_sensitive(text)
        assert REDACTED in result

    def test_access_key_assignment(self):
        """ACCESS_KEY=... 패턴의 값을 가린다"""
        text = "ACCESS_KEY=longaccesskeyvalue123456789"
        result = redact_sensitive(text)
        assert REDACTED in result

    def test_short_value_not_redacted(self):
        """7자 이하 짧은 값은 가리지 않는다 (오탐 방지)"""
        text = "API_KEY=short"
        result = redact_sensitive(text)
        # 7자이므로 가리지 않음
        assert "short" in result

    def test_quoted_value(self):
        """따옴표로 감싼 값도 가린다"""
        text = 'API_KEY="supersecretkey123456789"'
        result = redact_sensitive(text)
        assert "supersecretkey123456789" not in result

    def test_recall_api_key_pattern(self):
        """RECALL_API_KEY=... 같은 변형 패턴도 가린다"""
        text = "RECALL_API_KEY=sk-ant-abcdefghijklmnopqrstuvwxyz"
        result = redact_sensitive(text)
        assert "sk-ant-abcdefghijklmnopqrstuvwxyz" not in result


class TestAwsKeyPatterns:
    """AWS 스타일 키 패턴 테스트"""

    def test_akia_access_key(self):
        """AKIA 형태 AWS 액세스 키를 가린다"""
        text = "AWS_ACCESS_KEY_ID: AKIAIOSFODNN7EXAMPLE"
        result = redact_sensitive(text)
        assert REDACTED in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_asia_access_key(self):
        """ASIA 형태 AWS 임시 액세스 키를 가린다"""
        text = "access_key = ASIAIOSFODNN7EXAMPLE1"
        result = redact_sensitive(text)
        assert REDACTED in result


class TestEdgeCases:
    """경계 케이스 및 안전성 테스트"""

    def test_empty_string(self):
        """빈 문자열은 그대로 반환한다"""
        result = redact_sensitive("")
        assert result == ""

    def test_none_input(self):
        """None 입력은 None을 반환한다"""
        result = redact_sensitive(None)
        assert result is None

    def test_plain_text_unchanged(self):
        """민감 정보가 없는 텍스트는 변경되지 않는다"""
        text = "파일을 읽는 중입니다. 진행률: 50%"
        result = redact_sensitive(text)
        assert result == text

    def test_url_not_redacted(self):
        """일반 URL은 가리지 않는다"""
        text = "https://api.example.com/v1/endpoint?foo=bar"
        result = redact_sensitive(text)
        assert "https://api.example.com/v1/endpoint" in result

    def test_normal_assignment_not_redacted(self):
        """민감 키워드가 없는 일반 변수 할당은 가리지 않는다"""
        text = "DEBUG=true\nLOG_LEVEL=info\nPORT=8080"
        result = redact_sensitive(text)
        assert "true" in result
        assert "info" in result
        assert "8080" in result

    def test_multiline_text(self):
        """여러 줄에 걸친 텍스트에서도 민감 정보를 가린다"""
        text = (
            "설정 파일 내용:\n"
            "HOST=localhost\n"
            "API_KEY=supersecretapikey12345678\n"
            "PORT=3000\n"
        )
        result = redact_sensitive(text)
        assert "supersecretapikey12345678" not in result
        assert "localhost" in result
        assert "3000" in result

    def test_result_type_preserved(self):
        """반환 타입은 입력 타입과 동일하다"""
        text = "API_KEY=supersecretkey123456789"
        result = redact_sensitive(text)
        assert isinstance(result, str)

    def test_idempotent(self):
        """두 번 호출해도 결과가 같다 (멱등성)"""
        text = "API_KEY=supersecretkey123456789"
        once = redact_sensitive(text)
        twice = redact_sensitive(once)
        assert once == twice


class TestProgressIntegration:
    """on_tool_result에서 redact_sensitive가 호출되는지 통합 테스트"""

    @pytest.mark.asyncio
    async def test_tool_result_redacts_api_key(self):
        """on_tool_result가 API 키를 포함한 결과를 REDACT 처리하여 슬랙에 표시한다"""
        from unittest.mock import MagicMock
        from seosoyoung.slackbot.presentation.types import PresentationContext
        from seosoyoung.slackbot.presentation.node_map import SlackNodeMap
        from seosoyoung.slackbot.presentation.progress import build_event_callbacks

        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "tool_msg_ts"}

        pctx = PresentationContext(
            channel="C123",
            thread_ts="1234.5678",
            msg_ts="1234.9999",
            say=MagicMock(),
            client=client,
            effective_role="admin",
            session_id="sess-001",
            last_msg_ts="1234.6000",
        )
        node_map = SlackNodeMap()
        cbs = build_event_callbacks(pctx, node_map, mode="keep")

        # tool 시작
        await cbs["on_tool_start"]("Bash", {"command": "cat .env"}, "tu_001", "evt_t1", None)

        # API 키가 포함된 tool 결과
        secret_result = "ANTHROPIC_API_KEY=sk-ant-abcdefghijklmnopqrstu1234567890\nPORT=3000"
        await cbs["on_tool_result"](secret_result, "tu_001", False, "evt_result", "evt_t1")

        # chat_update 호출 확인
        update_calls = [
            c for c in client.chat_update.call_args_list
            if c[1].get("ts") == "tool_msg_ts"
        ]
        assert len(update_calls) >= 1
        displayed_text = update_calls[-1][1]["text"]

        # API 키 값이 노출되지 않아야 함
        assert "sk-ant-abcdefghijklmnopqrstu1234567890" not in displayed_text
        assert REDACTED in displayed_text

        # 민감하지 않은 값은 유지됨
        assert "PORT" in displayed_text or "3000" in displayed_text

    @pytest.mark.asyncio
    async def test_tool_result_non_string_passthrough(self):
        """on_tool_result가 비문자열 결과를 그대로 전달한다"""
        from unittest.mock import MagicMock
        from seosoyoung.slackbot.presentation.types import PresentationContext
        from seosoyoung.slackbot.presentation.node_map import SlackNodeMap
        from seosoyoung.slackbot.presentation.progress import build_event_callbacks

        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "tool_msg_ts2"}

        pctx = PresentationContext(
            channel="C123",
            thread_ts="1234.5678",
            msg_ts="1234.9999",
            say=MagicMock(),
            client=client,
            effective_role="admin",
            session_id="sess-001",
            last_msg_ts="1234.6000",
        )
        node_map = SlackNodeMap()
        cbs = build_event_callbacks(pctx, node_map, mode="keep")

        # tool 시작
        await cbs["on_tool_start"]("Read", {"file_path": "/a/b.py"}, "tu_002", "evt_t2", None)

        # 비문자열 결과 (리스트, 딕셔너리 등)
        non_string_result = [{"type": "text", "text": "content here"}]
        # 예외 없이 처리돼야 함
        await cbs["on_tool_result"](non_string_result, "tu_002", False, "evt_result2", "evt_t2")

        update_calls = [
            c for c in client.chat_update.call_args_list
            if c[1].get("ts") == "tool_msg_ts2"
        ]
        assert len(update_calls) >= 1
