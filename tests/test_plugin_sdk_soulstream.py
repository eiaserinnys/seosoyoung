"""Plugin SDK soulstream module-level wrapper 테스트

caller_info 1급 파라미터가 backend.run으로 정확히 forward되는지 검증한다.
"""

import pytest

from seosoyoung.plugin_sdk import soulstream
from seosoyoung.plugin_sdk.soulstream import RunResult, RunStatus


class _RecordingBackend:
    """backend.run 호출 인자를 기록하는 fake backend."""

    def __init__(self):
        self.last_call: dict | None = None

    async def run(self, **kwargs):
        self.last_call = kwargs
        return RunResult(ok=True, status=RunStatus.COMPLETED)

    async def compact(self, session_id):
        raise NotImplementedError

    def get_session_id(self, thread_ts):
        return None

    def is_restart_pending(self):
        return False

    def get_data_dir(self):
        from pathlib import Path
        return Path("/tmp")


@pytest.fixture
def recording_backend():
    """SoulstreamBackend을 RecordingBackend로 교체하고 테스트 후 복구."""
    prev = soulstream.get_backend()
    backend = _RecordingBackend()
    soulstream.set_backend(backend)
    try:
        yield backend
    finally:
        # 원래 상태로 복구 (None이면 모듈 전역을 None으로)
        soulstream._backend = prev


class TestRunForwardsCallerInfo:
    """module-level run()이 caller_info를 backend.run으로 forward한다."""

    @pytest.mark.asyncio
    async def test_caller_info_forwarded_when_provided(self, recording_backend):
        """caller_info dict가 명시되면 backend.run의 동일 키로 전달된다."""
        await soulstream.run(
            prompt="test",
            channel="C1",
            thread_ts="ts1",
            caller_info={"source": "channel_observer"},
        )
        assert recording_backend.last_call is not None
        assert recording_backend.last_call.get("caller_info") == {
            "source": "channel_observer"
        }

    @pytest.mark.asyncio
    async def test_caller_info_default_none(self, recording_backend):
        """caller_info를 생략하면 backend.run에 명시적 None으로 전달된다."""
        await soulstream.run(
            prompt="test",
            channel="C1",
            thread_ts="ts1",
        )
        assert recording_backend.last_call is not None
        # 1급 파라미터로 키 자체가 존재하고 값은 None이어야 함
        assert "caller_info" in recording_backend.last_call
        assert recording_backend.last_call["caller_info"] is None

    @pytest.mark.asyncio
    async def test_caller_info_does_not_collide_with_kwargs(self, recording_backend):
        """caller_info와 다른 kwargs를 함께 전달해도 별개로 forward된다."""
        await soulstream.run(
            prompt="test",
            channel="C1",
            thread_ts="ts1",
            caller_info={"source": "trello_watcher"},
            text_only=True,
            model="claude-sonnet-4",
        )
        assert recording_backend.last_call is not None
        assert recording_backend.last_call.get("caller_info") == {
            "source": "trello_watcher"
        }
        assert recording_backend.last_call.get("text_only") is True
        assert recording_backend.last_call.get("model") == "claude-sonnet-4"
