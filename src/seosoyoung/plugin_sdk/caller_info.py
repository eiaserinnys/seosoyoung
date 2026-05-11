"""Caller info API for plugins.

Plugins use this to build `caller_info` v1 dicts for `soulstream.run(caller_info=...)`
calls. The host (soul-server) interprets the dict against
`soul_common.auth.caller_info` (same v1 schema, atom `ed3a216d`).

R-4 fix(2026-05-11, atom G-12): plugin이 자기 source 정체성을 박을 때 dict 복제 패턴
(`{"source": ..., "display_name": ..., ...}`)을 helper로 통합. soul_common.auth.caller_info
정본과 *동등 구현* — plugin_sdk는 soul_common을 직접 import하지 않는다 (§1 plugin이 host
내부 모듈 모름). 시그니처·반환 dict 정합은 cross-import 회귀 테스트로 보장한다.

Usage:
    from seosoyoung.plugin_sdk import caller_info

    info = caller_info.build_bot_caller_info(
        source="channel_observer",
        display_name="채널 관찰자",
        agent_node=host_config.preferred_node or None,
    )
    result = await soulstream.run(prompt=..., caller_info=info)

정본 (host 측):
- `soul_common.auth.caller_info.build_bot_caller_info` (시그니처 정합 정본)
- caller_info v1 스키마: atom `ed3a216d`
"""

from __future__ import annotations

from typing import Any, Optional


# soul_common.auth.caller_info.SYSTEM_PORTRAIT_BASE와 동일 값. cross-import 회귀 테스트가
# 두 정본의 값이 정합한지 보장.
SYSTEM_PORTRAIT_BASE = "/api/system/portraits"


def build_bot_caller_info(
    *,
    source: str,
    display_name: str,
    agent_node: Optional[str] = None,
) -> dict[str, Any]:
    """자동 봇(channel_observer / trello_watcher) source의 caller_info 조립 (통합 v1).

    soul_common.auth.caller_info.build_bot_caller_info의 plugin-side 동등 구현.
    plugin_sdk가 soul_common을 직접 import하지 않도록 *복제 구현* — cross-import
    회귀 테스트(`tests/test_plugin_sdk_caller_info_signature.py`)가 두 정본의
    시그니처·반환 dict 정합을 보장한다.

    호출 정본:
    - `seosoyoung-plugins/.../channel_observer/pipeline.py` — channel_observer
    - `seosoyoung-plugins/.../trello/watcher.py` — trello_watcher

    Args:
        source: 봇 source 토큰. host(soul-server)의 ALLOWED_SOURCES + _PORTRAIT_FILE_MAP
            (`orch-server/.../api/system_portraits.py`)에 등록되어야 함.
        display_name: 사용자 표시명 (예: '채널 관찰자', '트렐로 워처').
        agent_node: (옵션, R-4 atom G-14) 봇이 실행되는 노드 ID. plugin 호출자(host)가
            `Config.orchestrator.preferred_node or None`을 전달. truthy일 때만
            caller_info에 키 포함 — graceful (자동 라우팅 시 None 유지).

    Returns:
        v1 caller_info dict — source/display_name/avatar_url 채움, user_id None.
        agent_node는 옵션 인자 truthy일 때만 포함.
    """
    info: dict[str, Any] = {
        "source": source,
        "display_name": display_name,
        "user_id": None,
        "avatar_url": f"{SYSTEM_PORTRAIT_BASE}/{source}",
    }
    if agent_node:
        info["agent_node"] = agent_node
    return info


def get_host_preferred_node() -> Optional[str]:
    """Host(seosoyoung 슬랙봇)의 preferred_node를 동적으로 조회 (R-4, atom G-14).

    Plugin이 자기 `caller_info.agent_node`에 박을 노드 ID를 host config에서 *자연 조회*한다.
    plugin이 `Config` singleton 또는 환경변수를 직접 import하지 않도록 plugin_sdk가 wrapping
    — plugin은 plugin_sdk만 import (§1 지식 경계 추상화 보존).

    `handlers/node.py:_update_preferred_node`로 *런타임에 dynamic 변경*되는 값이므로 매 호출
    시점에 최신 값을 반환 (plugins.yaml의 *snapshot* config 패턴 대비 정합).

    Returns:
        Host의 `Config.orchestrator.preferred_node` — truthy면 노드 ID, None이면:
        - 자동 라우팅 모드 (`SOULSTREAM_PREFERRED_NODE` 미설정)
        - Config 모듈 import 실패 (test 환경 등 plugin_sdk가 호스트 외부에서 로드된 경우)

    호출 정본:
    - `seosoyoung-plugins/.../channel_observer/pipeline.py` — caller_info.agent_node 채움
    - `seosoyoung-plugins/.../trello/watcher.py` — 동
    """
    try:
        from seosoyoung.slackbot.config import Config

        return Config.orchestrator.preferred_node or None
    except (ImportError, AttributeError):
        # plugin_sdk가 host 외부에서 로드되는 환경(unit test 등) — graceful None.
        return None
