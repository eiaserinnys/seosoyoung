"""cogito source 데코레이터 전환 테스트.

각 서비스의 Reflector에서 get_sources()를 호출하여
@reflect.capability 데코레이터가 올바르게 소스 위치를 추적하는지 검증한다.

NOTE: 데코레이터는 모듈 임포트 시 등록되므로, 데코레이터가 적용된 모듈을
먼저 임포트한 후 get_sources()를 호출해야 한다.
"""

import pytest


class TestBotCogitoSources:
    """bot 서비스의 cogito source 검증."""

    @pytest.fixture(autouse=True)
    def _import_decorated_modules(self):
        """데코레이터가 적용된 모듈을 임포트하여 capability를 등록한다."""
        import seosoyoung.slackbot.handlers  # event_handling
        import seosoyoung.slackbot.handlers.mention  # mention_response
        import seosoyoung.slackbot.main  # plugin_system
        import seosoyoung.slackbot.soulstream.executor  # soulstream_integration

    def test_sources_count(self):
        from seosoyoung.slackbot.reflect import reflect

        sources = reflect.get_sources()
        assert len(sources) == 4

    def test_source_capability_names(self):
        from seosoyoung.slackbot.reflect import reflect

        sources = reflect.get_sources()
        names = {s.capability for s in sources}
        assert names == {
            "event_handling",
            "mention_response",
            "plugin_system",
            "soulstream_integration",
        }

    def test_sources_have_paths(self):
        from seosoyoung.slackbot.reflect import reflect

        sources = reflect.get_sources()
        for source in sources:
            assert source.path, f"{source.capability}: path가 비어있음"
            assert source.entry_point, f"{source.capability}: entry_point가 비어있음"
            assert source.start_line > 0, f"{source.capability}: start_line이 0"


class TestRescueCogitoSources:
    """rescue-bot 서비스의 cogito source 검증."""

    @pytest.fixture(autouse=True)
    def _import_decorated_modules(self):
        """데코레이터가 적용된 모듈을 임포트하여 capability를 등록한다."""
        import seosoyoung.rescue.main  # emergency_execution, standalone_operation

    def test_sources_count(self):
        from seosoyoung.rescue.reflect import reflect

        sources = reflect.get_sources()
        assert len(sources) == 2

    def test_source_capability_names(self):
        from seosoyoung.rescue.reflect import reflect

        sources = reflect.get_sources()
        names = {s.capability for s in sources}
        assert names == {
            "emergency_execution",
            "standalone_operation",
        }

    def test_sources_have_paths(self):
        from seosoyoung.rescue.reflect import reflect

        sources = reflect.get_sources()
        for source in sources:
            assert source.path, f"{source.capability}: path가 비어있음"
            assert source.entry_point, f"{source.capability}: entry_point가 비어있음"
            assert source.start_line > 0, f"{source.capability}: start_line이 0"
