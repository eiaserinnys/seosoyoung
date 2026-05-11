"""plugin_sdk/soulstream.py docstring 회귀 안전망 (R-5 atom G-18).

R-5 fix(2026-05-11): `caller_info` 파라미터 docstring을 *단일 키 dict* 예시에서
plugin_sdk helper 호출 예시로 교체. plugin 신규 개발자가 docstring 보고
*단일 키 dict 패턴 차용* (R-4 G-12 fix 무력화 회귀)을 차단.

본 회귀 테스트가 docstring raw text 텍스트를 grep하여:
- T-G18-A: `caller_info={"source":` 단일 키 패턴 잔존 0건
- T-G18-B: 공백 변형(`caller_info = {"source":` 등) 잔존 0건
- T-G18-C: docstring에 `build_bot_caller_info` + `build_slack_caller_info` 둘 다 명시
"""

import re
from pathlib import Path

import seosoyoung.plugin_sdk.soulstream as soulstream_module


SOULSTREAM_PY_PATH = Path(soulstream_module.__file__)
SOULSTREAM_PY_TEXT = SOULSTREAM_PY_PATH.read_text(encoding="utf-8")


class TestSoulstreamDocstringR5G18:
    """T-G18: 단일 키 dict 패턴 잔존 0건 + helper 패턴 명시."""

    def test_no_single_key_caller_info_pattern_compact(self):
        """T-G18-A: `caller_info={"source": "..."` 단일 키 패턴 잔존 0건.

        탐지 패턴: caller_info 뒤 = 또는 콜론 + 중괄호 안에 source 키만 있는 경우.
        단일 키 dict 예시가 docstring에 잔존하면 plugin 신규 개발자가 R-4 G-12
        fix를 무력화하는 dict 복제 패턴을 차용할 수 있다.
        """
        # caller_info=\{"source": "...채널 내용..."\} — 닫는 중괄호까지 안에 다른 키 없는 경우
        # display_name, agent_node 등 다른 키와 함께 있으면 단일 키가 아니므로 OK
        pattern = re.compile(
            r'caller_info\s*=\s*\{\s*"source"\s*:\s*"[^"]+"\s*\}',
        )
        matches = pattern.findall(SOULSTREAM_PY_TEXT)
        assert matches == [], (
            f"plugin_sdk/soulstream.py에 단일 키 caller_info dict 패턴 잔존: {matches}. "
            f"R-4 G-12 fix 무력화 회귀. plugin_sdk helper 호출 예시로 교체 필요."
        )

    def test_no_single_key_caller_info_pattern_with_spaces(self):
        """T-G18-B: 공백 변형(다양한 띄어쓰기 + bare dict 예시) 잔존 0건.

        예: `예: {"source": "channel_observer"}` 같은 *bare dict 예시*도 차단.
        """
        # bare dict 예시: `{"source": "channel_observer"}` 같은 패턴 (caller_info=  prefix 없음)
        # 단일 키 dict (다른 키 없음) 만 차단
        pattern = re.compile(
            r'(?<!\w)\{\s*"source"\s*:\s*"[^"]+"\s*\}',
        )
        matches = pattern.findall(SOULSTREAM_PY_TEXT)
        # docstring에서 helper 호출 예시는 dict 리터럴 사용 안 함 → 0건이 정상
        assert matches == [], (
            f"plugin_sdk/soulstream.py에 bare 단일 키 dict 예시 잔존: {matches}. "
            f"docstring을 helper 호출 패턴(build_bot_caller_info/build_slack_caller_info)으로 갱신 필요."
        )

    def test_helper_patterns_referenced(self):
        """T-G18-C: docstring 본문에 helper 호출 패턴 둘 다 명시.

        plugin 신규 개발자가 docstring 보고 *올바른 패턴*을 차용하도록.
        """
        assert "build_bot_caller_info" in SOULSTREAM_PY_TEXT, (
            "plugin_sdk/soulstream.py docstring에 build_bot_caller_info 패턴 명시 필요 "
            "(R-4 G-12 권장 패턴 인용)"
        )
        assert "build_slack_caller_info" in SOULSTREAM_PY_TEXT, (
            "plugin_sdk/soulstream.py docstring에 build_slack_caller_info 패턴 명시 필요 "
            "(R-5 G-15 권장 패턴 인용)"
        )
