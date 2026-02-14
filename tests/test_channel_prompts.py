"""채널 프롬프트 포맷 함수 테스트

reactions 필드가 있는 메시지의 포맷팅을 검증합니다.
DisplayNameResolver와 resolver 적용 포맷을 검증합니다.
"""

from seosoyoung.memory.channel_prompts import (
    DisplayNameResolver,
    build_channel_intervene_user_prompt,
    _format_channel_messages,
    _format_pending_messages,
    _format_thread_messages,
)


class TestFormatPendingMessagesReactions:
    """pending 메시지 포맷에 reactions 표시"""

    def test_message_without_reactions(self):
        """reactions가 없는 메시지는 기존 포맷 유지"""
        msgs = [{"ts": "1.1", "user": "U001", "text": "hello"}]
        result = _format_pending_messages(msgs)
        assert result == "[1.1] U001: hello"

    def test_message_with_single_reaction(self):
        """reactions가 하나인 메시지"""
        msgs = [{
            "ts": "1.1", "user": "U001", "text": "hello",
            "reactions": [{"name": "thumbsup", "users": ["U002"], "count": 1}],
        }]
        result = _format_pending_messages(msgs)
        assert ":thumbsup:×1" in result

    def test_message_with_multiple_reactions(self):
        """reactions가 여러 개인 메시지"""
        msgs = [{
            "ts": "1.1", "user": "U001", "text": "hello",
            "reactions": [
                {"name": "thumbsup", "users": ["U002", "U003"], "count": 2},
                {"name": "heart", "users": ["U004"], "count": 1},
            ],
        }]
        result = _format_pending_messages(msgs)
        assert ":thumbsup:×2" in result
        assert ":heart:×1" in result

    def test_empty_reactions_list(self):
        """reactions가 빈 리스트인 경우"""
        msgs = [{
            "ts": "1.1", "user": "U001", "text": "hello",
            "reactions": [],
        }]
        result = _format_pending_messages(msgs)
        # 빈 리스트면 reactions 표시 없음
        assert "×" not in result


class TestFormatChannelMessagesReactions:
    """채널 메시지 포맷에 reactions 표시"""

    def test_message_with_reactions(self):
        """채널 메시지에도 reactions 표시"""
        msgs = [{
            "ts": "1.1", "user": "U001", "text": "hello",
            "reactions": [{"name": "fire", "users": ["U002", "U003"], "count": 2}],
        }]
        result = _format_channel_messages(msgs)
        assert ":fire:×2" in result


class TestFormatThreadMessagesReactions:
    """스레드 메시지 포맷에 reactions 표시"""

    def test_thread_message_with_reactions(self):
        """스레드 메시지에도 reactions 표시"""
        buffers = {
            "parent.ts": [{
                "ts": "2.1", "user": "U001", "text": "reply",
                "reactions": [{"name": "eyes", "users": ["U002"], "count": 1}],
            }],
        }
        result = _format_thread_messages(buffers)
        assert ":eyes:×1" in result


class TestDisplayNameResolver:
    """DisplayNameResolver 단위 테스트"""

    def test_no_client_returns_raw_id(self):
        """slack_client 없으면 user_id를 그대로 반환"""
        resolver = DisplayNameResolver(slack_client=None)
        assert resolver.resolve("U001") == "U001"

    def test_resolve_with_display_name(self):
        """users_info 성공 시 '디스플레이네임 (UID)' 형식 반환"""
        class MockSlackClient:
            def users_info(self, user):
                return {
                    "ok": True,
                    "user": {
                        "name": "jdoe",
                        "profile": {
                            "display_name": "John",
                            "real_name": "John Doe",
                        },
                    },
                }

        resolver = DisplayNameResolver(slack_client=MockSlackClient())
        result = resolver.resolve("U001")
        assert result == "John (U001)"

    def test_resolve_fallback_to_real_name(self):
        """display_name이 없으면 real_name 사용"""
        class MockSlackClient:
            def users_info(self, user):
                return {
                    "ok": True,
                    "user": {
                        "name": "jdoe",
                        "profile": {
                            "display_name": "",
                            "real_name": "John Doe",
                        },
                    },
                }

        resolver = DisplayNameResolver(slack_client=MockSlackClient())
        result = resolver.resolve("U002")
        assert result == "John Doe (U002)"

    def test_resolve_caches_result(self):
        """같은 ID는 1회만 API 호출"""
        call_count = 0

        class MockSlackClient:
            def users_info(self, user):
                nonlocal call_count
                call_count += 1
                return {
                    "ok": True,
                    "user": {
                        "name": "jdoe",
                        "profile": {"display_name": "John", "real_name": "John Doe"},
                    },
                }

        resolver = DisplayNameResolver(slack_client=MockSlackClient())
        resolver.resolve("U001")
        resolver.resolve("U001")
        resolver.resolve("U001")
        assert call_count == 1

    def test_resolve_api_error_returns_raw_id(self):
        """API 에러 시 원래 user_id 반환"""
        class MockSlackClient:
            def users_info(self, user):
                raise Exception("API error")

        resolver = DisplayNameResolver(slack_client=MockSlackClient())
        assert resolver.resolve("U001") == "U001"


class TestFormatWithResolver:
    """resolver 적용 시 포맷 변환 테스트"""

    def _make_resolver(self):
        class MockSlackClient:
            def users_info(self, user):
                names = {
                    "U001": "Alice",
                    "U002": "Bob",
                }
                name = names.get(user, user)
                return {
                    "ok": True,
                    "user": {"name": user, "profile": {"display_name": name, "real_name": name}},
                }
        return DisplayNameResolver(slack_client=MockSlackClient())

    def test_channel_messages_with_resolver(self):
        """resolver 적용 시 디스플레이네임으로 변환"""
        msgs = [{"ts": "1.1", "user": "U001", "text": "hello"}]
        resolver = self._make_resolver()
        result = _format_channel_messages(msgs, resolver=resolver)
        assert "Alice (U001)" in result
        assert "[1.1] Alice (U001): hello" == result

    def test_pending_messages_with_resolver(self):
        """pending 포맷도 resolver 적용"""
        msgs = [{"ts": "2.1", "user": "U002", "text": "world"}]
        resolver = self._make_resolver()
        result = _format_pending_messages(msgs, resolver=resolver)
        assert "Bob (U002)" in result

    def test_thread_messages_with_resolver(self):
        """스레드 포맷도 resolver 적용"""
        buffers = {
            "parent.ts": [{"ts": "3.1", "user": "U001", "text": "thread msg"}],
        }
        resolver = self._make_resolver()
        result = _format_thread_messages(buffers, resolver=resolver)
        assert "Alice (U001)" in result


class TestIntervenePromptWithThreadBuffers:
    """개입 프롬프트에 thread_buffers 포함 테스트"""

    def test_thread_buffers_included_in_prompt(self):
        """thread_buffers가 있으면 프롬프트에 스레드 메시지 포함"""
        thread_buffers = {
            "100.0": [
                {"ts": "100.1", "user": "U001", "text": "스레드 메시지 1"},
                {"ts": "100.2", "user": "U002", "text": "스레드 메시지 2"},
            ],
        }
        result = build_channel_intervene_user_prompt(
            digest="기존 다이제스트",
            recent_messages=[{"ts": "1.0", "user": "U001", "text": "최근"}],
            trigger_message={"ts": "2.0", "user": "U001", "text": "트리거"},
            target="2.0",
            thread_buffers=thread_buffers,
        )
        assert "스레드 메시지 1" in result
        assert "스레드 메시지 2" in result

    def test_no_thread_buffers_still_works(self):
        """thread_buffers 없어도 정상 동작 (하위호환)"""
        result = build_channel_intervene_user_prompt(
            digest="다이제스트",
            recent_messages=[{"ts": "1.0", "user": "U001", "text": "최근"}],
            trigger_message={"ts": "2.0", "user": "U001", "text": "트리거"},
            target="2.0",
        )
        assert "다이제스트" in result
        assert "트리거" in result
