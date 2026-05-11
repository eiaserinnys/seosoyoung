"""plugin_sdk/caller_info 단위 테스트 (R-4, atom G-12 + G-14).

R-4 fix(2026-05-11): plugin_sdk가 build_bot_caller_info를 noemus_common 정본과 *동등
구현*으로 노출. plugin이 host 내부 모듈을 직접 import하지 않도록 plugin_sdk가 wrapping
(§1 지식 경계 추상화).

cross-import 정합(soul_common helper와 시그니처·반환 dict 일치)은 *seosoyoung-plugins*
tests의 test_caller_info_signature_regression.py가 검증한다.

본 파일은 plugin_sdk *단독* 정합 — build_bot_caller_info의 입출력 단위·get_host_preferred_node의
graceful import 동작.
"""

import sys
from unittest.mock import patch

import pytest

from seosoyoung.plugin_sdk.caller_info import (
    SYSTEM_PORTRAIT_BASE,
    build_bot_caller_info,
    build_slack_caller_info,  # R-5 G-15
    get_host_preferred_node,
)


class TestBuildBotCallerInfoUnit:
    """plugin_sdk build_bot_caller_info 단위 — soul_common 의존성 없이 단독 검증."""

    def test_channel_observer_minimal_dict(self):
        """source + display_name만 → v1 dict 4키, agent_node 키 부재."""
        result = build_bot_caller_info(
            source="channel_observer",
            display_name="채널 관찰자",
        )
        assert result == {
            "source": "channel_observer",
            "display_name": "채널 관찰자",
            "user_id": None,
            "avatar_url": "/api/system/portraits/channel_observer",
        }

    def test_trello_watcher_minimal_dict(self):
        """trello_watcher source 동일 패턴."""
        result = build_bot_caller_info(
            source="trello_watcher",
            display_name="트렐로 워처",
        )
        assert result == {
            "source": "trello_watcher",
            "display_name": "트렐로 워처",
            "user_id": None,
            "avatar_url": "/api/system/portraits/trello_watcher",
        }

    def test_agent_node_truthy_included(self):
        """agent_node truthy → caller_info에 키 포함 (R-4 G-14)."""
        result = build_bot_caller_info(
            source="channel_observer",
            display_name="채널 관찰자",
            agent_node="eias-linegames",
        )
        assert result["agent_node"] == "eias-linegames"

    @pytest.mark.parametrize("falsy", [None, ""])
    def test_agent_node_falsy_omitted(self, falsy):
        """agent_node falsy(None/빈 문자열) → 키 부재 (graceful)."""
        result = build_bot_caller_info(
            source="channel_observer",
            display_name="채널 관찰자",
            agent_node=falsy,
        )
        assert "agent_node" not in result

    def test_avatar_url_pattern(self):
        """avatar_url = SYSTEM_PORTRAIT_BASE + source — 라우트 정합."""
        result = build_bot_caller_info(
            source="custom_bot",
            display_name="Custom Bot",
        )
        assert result["avatar_url"] == f"{SYSTEM_PORTRAIT_BASE}/custom_bot"

    def test_keyword_only_args(self):
        """source/display_name keyword-only → positional 호출 TypeError."""
        try:
            build_bot_caller_info("channel_observer", "채널 관찰자")  # type: ignore[misc]
        except TypeError:
            return
        raise AssertionError("positional 호출이 TypeError를 일으켜야 한다")


class TestSystemPortraitBaseConstant:
    """SYSTEM_PORTRAIT_BASE 상수 — orch 라우트 prefix와 정합."""

    def test_value(self):
        """`/api/system/portraits` — orch-server `create_system_portraits_router` prefix."""
        assert SYSTEM_PORTRAIT_BASE == "/api/system/portraits"


class TestBuildSlackCallerInfoReExportR5:
    """T-G15-E: plugin_sdk.build_slack_caller_info **identity** = 정본 (옵션 A §3 회귀 안전망).

    R-5 atom G-15: plugin_sdk가 `seosoyoung.slackbot.soulstream.caller_info`의 정본을
    *re-export*. 두 import 경로가 *같은 함수 객체*를 가리켜야 §3 정본 단일.
    후행 세션이 plugin_sdk/caller_info.py에 build_slack_caller_info를 *복제 구현*으로
    잘못 추가하면 본 회귀 테스트가 명시적으로 실패한다.
    """

    def test_function_identity_same_as_canonical(self):
        """plugin_sdk.build_slack_caller_info **is** slackbot.soulstream.caller_info.build_slack_caller_info."""
        from seosoyoung.slackbot.soulstream.caller_info import (
            build_slack_caller_info as canonical,
        )
        # function identity check — 같은 객체여야 함 (옵션 A re-export 정합)
        assert build_slack_caller_info is canonical, (
            "plugin_sdk.build_slack_caller_info와 slackbot.soulstream.caller_info.build_slack_caller_info"
            "가 같은 함수 객체여야 합니다 (옵션 A re-export §3 정본 단일). "
            "후행 세션이 *복제 구현*으로 잘못 추가했으면 본 테스트가 실패합니다."
        )

    def test_callable_via_reexport(self):
        """re-export된 helper가 정상 호출 가능 (sanity check)."""
        result = build_slack_caller_info(
            channel_id="C12345",
            user_id="U67890",
            thread_ts="1234567890.123456",
            display_name="앨리스",
            avatar_url="https://avatars.slack-edge.com/alice_192.jpg",
            email="alice@example.com",
        )
        # 정본의 동작과 동일
        assert result["source"] == "slack"
        assert result["user_id"] == "U67890"
        assert result["display_name"] == "앨리스"
        assert result["avatar_url"] == "https://avatars.slack-edge.com/alice_192.jpg"
        assert result["email"] == "alice@example.com"
        assert result["slack"]["channel_id"] == "C12345"
        assert result["slack"]["thread_ts"] == "1234567890.123456"

    def test_reexport_in_init_namespace(self):
        """`seosoyoung.plugin_sdk`에서 직접 import 가능 (`build_slack_caller_info`)."""
        from seosoyoung.plugin_sdk import build_slack_caller_info as via_init
        # __init__.py L61-64 export + L93-95 __all__와 정본 정합
        assert via_init is build_slack_caller_info


class TestGetHostPreferredNode:
    """R-4 (atom G-14): get_host_preferred_node — host config 동적 조회 helper."""

    def test_returns_config_value_when_truthy(self):
        """Config.orchestrator.preferred_node truthy → 그 값 반환."""
        # Config 모듈을 mock으로 패치 — preferred_node 값 주입
        from seosoyoung.slackbot.config import Config

        with patch.object(Config.orchestrator, "preferred_node", "eias-shopping"):
            result = get_host_preferred_node()
            assert result == "eias-shopping"

    def test_returns_none_when_empty_string(self):
        """Config.orchestrator.preferred_node = "" (default) → None (graceful, 자동 라우팅)."""
        from seosoyoung.slackbot.config import Config

        with patch.object(Config.orchestrator, "preferred_node", ""):
            result = get_host_preferred_node()
            assert result is None

    def test_returns_none_when_config_import_fails(self):
        """Config 모듈 import 실패(test 환경 등) → graceful None."""
        # Config 모듈을 sys.modules에서 임시 제거하여 ImportError 시뮬레이션
        original_modules = {
            k: v for k, v in sys.modules.items()
            if k.startswith("seosoyoung.slackbot.config")
        }
        # block import by registering None — Python ImportError on re-import
        with patch.dict(sys.modules, {"seosoyoung.slackbot.config": None}):
            # get_host_preferred_node 내부의 import 시 ImportError 또는 AttributeError
            result = get_host_preferred_node()
            assert result is None
        # cleanup — 원상복구
        for k, v in original_modules.items():
            sys.modules[k] = v
