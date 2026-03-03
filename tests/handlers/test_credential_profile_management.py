"""크레덴셜 프로필 관리 UI 및 액션 핸들러 테스트

프로필 저장/삭제/목록 조회를 위한 슬랙 UI 블록 빌더와
액션 핸들러를 테스트합니다.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, call

from seosoyoung.slackbot.handlers.credential_ui import (
    build_profile_management_blocks,
    build_save_prompt_blocks,
    build_delete_confirm_blocks,
)
from seosoyoung.slackbot.handlers.actions import (
    save_credential_profile,
    delete_credential_profile,
    list_credential_profiles,
    register_credential_action_handlers,
)


# ── build_profile_management_blocks ─────────────────────────


class TestBuildProfileManagementBlocks:
    """프로필 관리 블록 (목록 + 저장/삭제 버튼)"""

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

    def test_structure_has_section_and_actions(self):
        blocks = build_profile_management_blocks("linegames", self._make_profiles())
        types = [b["type"] for b in blocks]
        assert "section" in types
        assert "actions" in types

    def test_header_text(self):
        blocks = build_profile_management_blocks("linegames", self._make_profiles())
        section = blocks[0]
        assert "프로필 관리" in section["text"]["text"]

    def test_profile_info_displayed(self):
        blocks = build_profile_management_blocks("linegames", self._make_profiles())
        text = blocks[0]["text"]["text"]
        assert "linegames" in text
        assert "personal" in text
        assert "(활성)" in text

    def test_switch_buttons_present(self):
        """비활성 프로필에 전환 버튼이 있어야 함"""
        blocks = build_profile_management_blocks("linegames", self._make_profiles())
        actions_block = next(b for b in blocks if b["type"] == "actions")
        action_ids = [e["action_id"] for e in actions_block["elements"]]
        # personal은 비활성이므로 전환 버튼 있음
        assert any("credential_switch_" in aid for aid in action_ids)

    def test_delete_buttons_present(self):
        """비활성 프로필에 삭제 버튼이 있어야 함"""
        blocks = build_profile_management_blocks("linegames", self._make_profiles())
        actions_block = next(b for b in blocks if b["type"] == "actions")
        action_ids = [e["action_id"] for e in actions_block["elements"]]
        assert any("credential_delete_" in aid for aid in action_ids)

    def test_active_profile_no_delete_button(self):
        """활성 프로필에는 삭제 버튼이 없어야 함"""
        blocks = build_profile_management_blocks("linegames", self._make_profiles())
        actions_block = next(b for b in blocks if b["type"] == "actions")
        action_ids = [e["action_id"] for e in actions_block["elements"]]
        assert "credential_delete_linegames" not in action_ids

    def test_save_button_present(self):
        """프로필 저장 버튼이 있어야 함"""
        blocks = build_profile_management_blocks("linegames", self._make_profiles())
        # 마지막 actions 블록에 저장 버튼
        all_actions = [b for b in blocks if b["type"] == "actions"]
        all_elements = []
        for a in all_actions:
            all_elements.extend(a["elements"])
        action_ids = [e["action_id"] for e in all_elements]
        assert "credential_save_profile" in action_ids

    def test_list_button_absent_in_management_view(self):
        """관리 뷰에서는 목록 버튼이 없어야 함 (이미 목록을 표시하고 있으므로)"""
        blocks = build_profile_management_blocks("linegames", self._make_profiles())
        all_actions = [b for b in blocks if b["type"] == "actions"]
        all_elements = []
        for a in all_actions:
            all_elements.extend(a["elements"])
        action_ids = [e["action_id"] for e in all_elements]
        assert "credential_list_profiles" not in action_ids

    def test_empty_profiles(self):
        """프로필이 없을 때도 저장 버튼은 있어야 함"""
        blocks = build_profile_management_blocks("", [])
        all_actions = [b for b in blocks if b["type"] == "actions"]
        all_elements = []
        for a in all_actions:
            all_elements.extend(a["elements"])
        action_ids = [e["action_id"] for e in all_elements]
        assert "credential_save_profile" in action_ids

    def test_single_active_profile(self):
        """활성 프로필이 하나뿐이면 전환/삭제 버튼 없음, 저장 버튼만"""
        profiles = [
            {
                "name": "only",
                "five_hour": {"utilization": 0.5, "resets_at": None},
                "seven_day": {"utilization": 0.0, "resets_at": None},
            },
        ]
        blocks = build_profile_management_blocks("only", profiles)
        all_actions = [b for b in blocks if b["type"] == "actions"]
        all_elements = []
        for a in all_actions:
            all_elements.extend(a["elements"])
        action_ids = [e["action_id"] for e in all_elements]
        assert "credential_delete_only" not in action_ids
        assert "credential_save_profile" in action_ids


# ── build_save_prompt_blocks ────────────────────────────────


class TestBuildSavePromptBlocks:
    """프로필 저장 이름 입력 안내 블록"""

    def test_structure(self):
        blocks = build_save_prompt_blocks()
        assert len(blocks) >= 1
        types = [b["type"] for b in blocks]
        assert "input" in types or "section" in types

    def test_contains_instruction_text(self):
        blocks = build_save_prompt_blocks()
        # 전체 텍스트에 저장 관련 안내가 있어야 함
        all_text = json.dumps(blocks, ensure_ascii=False)
        assert "저장" in all_text or "이름" in all_text


# ── build_delete_confirm_blocks ─────────────────────────────


class TestBuildDeleteConfirmBlocks:
    """프로필 삭제 확인 블록"""

    def test_structure(self):
        blocks = build_delete_confirm_blocks("work")
        types = [b["type"] for b in blocks]
        assert "section" in types
        assert "actions" in types

    def test_profile_name_in_text(self):
        blocks = build_delete_confirm_blocks("my_profile")
        text = json.dumps(blocks)
        assert "my_profile" in text

    def test_confirm_and_cancel_buttons(self):
        blocks = build_delete_confirm_blocks("work")
        actions_block = next(b for b in blocks if b["type"] == "actions")
        elements = actions_block["elements"]
        action_ids = [e["action_id"] for e in elements]
        assert any("confirm" in aid for aid in action_ids)
        assert any("cancel" in aid for aid in action_ids)

    def test_confirm_button_has_profile_name(self):
        blocks = build_delete_confirm_blocks("work")
        actions_block = next(b for b in blocks if b["type"] == "actions")
        confirm_btn = next(
            e for e in actions_block["elements"] if "confirm" in e["action_id"]
        )
        assert confirm_btn["value"] == "work"


# ── save_credential_profile ─────────────────────────────────


class TestSaveCredentialProfile:
    """프로필 저장 액션 핸들러"""

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_successful_save(self, mock_urlopen):
        """저장 성공 시 성공 메시지"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"name": "work", "saved": true}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = MagicMock()
        save_credential_profile("work", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        text = client.chat_update.call_args[1]["text"]
        assert "work" in text

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_api_call_format(self, mock_urlopen):
        """Soul API POST /profiles/{name} 호출 확인"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"name": "work", "saved": true}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = MagicMock()
        save_credential_profile("work", "C123", "ts123", client)

        req = mock_urlopen.call_args[0][0]
        assert "/profiles/work" in req.full_url
        assert req.method == "POST"
        assert req.get_header("Authorization").startswith("Bearer ")

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_failed_save(self, mock_urlopen):
        """저장 실패 시 에러 메시지"""
        mock_urlopen.side_effect = Exception("Connection refused")

        client = MagicMock()
        save_credential_profile("broken", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        text = client.chat_update.call_args[1]["text"]
        assert "broken" in text

    def test_invalid_name_rejected(self):
        """유효하지 않은 이름 거부"""
        client = MagicMock()
        save_credential_profile("../bad", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        assert "유효하지 않은" in client.chat_update.call_args[1]["text"]

    def test_empty_name_rejected(self):
        """빈 이름 거부"""
        client = MagicMock()
        save_credential_profile("", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        assert "유효하지 않은" in client.chat_update.call_args[1]["text"]


# ── delete_credential_profile ───────────────────────────────


class TestDeleteCredentialProfile:
    """프로필 삭제 액션 핸들러"""

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_successful_delete(self, mock_urlopen):
        """삭제 성공 시 성공 메시지"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"deleted": true, "name": "old"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = MagicMock()
        delete_credential_profile("old", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        text = client.chat_update.call_args[1]["text"]
        assert "old" in text

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_api_call_format(self, mock_urlopen):
        """Soul API DELETE /profiles/{name} 호출 확인"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"deleted": true, "name": "old"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = MagicMock()
        delete_credential_profile("old", "C123", "ts123", client)

        req = mock_urlopen.call_args[0][0]
        assert "/profiles/old" in req.full_url
        assert req.method == "DELETE"
        assert req.get_header("Authorization").startswith("Bearer ")

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_failed_delete(self, mock_urlopen):
        """삭제 실패 시 에러 메시지"""
        mock_urlopen.side_effect = Exception("Not found")

        client = MagicMock()
        delete_credential_profile("gone", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        text = client.chat_update.call_args[1]["text"]
        assert "gone" in text

    def test_invalid_name_rejected(self):
        """유효하지 않은 이름 거부"""
        client = MagicMock()
        delete_credential_profile("rm -rf /", "C123", "ts123", client)

        client.chat_update.assert_called_once()
        assert "유효하지 않은" in client.chat_update.call_args[1]["text"]


# ── list_credential_profiles ────────────────────────────────


class TestListCredentialProfiles:
    """프로필 목록 조회 액션 핸들러"""

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_successful_list(self, mock_urlopen):
        """목록 조회 성공 시 관리 블록 메시지 전송"""
        profiles_resp = MagicMock()
        profiles_resp.read.return_value = json.dumps({
            "profiles": [{"name": "work"}, {"name": "personal"}],
            "active": "work",
        }).encode()
        profiles_resp.__enter__ = MagicMock(return_value=profiles_resp)
        profiles_resp.__exit__ = MagicMock(return_value=False)

        rate_resp = MagicMock()
        rate_resp.read.return_value = json.dumps({
            "active_profile": "work",
            "profiles": [
                {
                    "name": "work",
                    "five_hour": {"utilization": 0.5, "resets_at": None},
                    "seven_day": {"utilization": 0.1, "resets_at": None},
                },
                {
                    "name": "personal",
                    "five_hour": {"utilization": 0.0, "resets_at": None},
                    "seven_day": {"utilization": 0.0, "resets_at": None},
                },
            ],
        }).encode()
        rate_resp.__enter__ = MagicMock(return_value=rate_resp)
        rate_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [profiles_resp, rate_resp]

        client = MagicMock()
        list_credential_profiles("C123", "ts123", client)

        client.chat_update.assert_called_once()
        kwargs = client.chat_update.call_args[1]
        assert "blocks" in kwargs
        assert kwargs["channel"] == "C123"

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_failed_list(self, mock_urlopen):
        """목록 조회 실패 시 에러 메시지"""
        mock_urlopen.side_effect = Exception("Connection refused")

        client = MagicMock()
        list_credential_profiles("C123", "ts123", client)

        client.chat_update.assert_called_once()
        text = client.chat_update.call_args[1]["text"]
        assert "오류" in text or "실패" in text

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_empty_profiles(self, mock_urlopen):
        """프로필이 없을 때도 저장 버튼은 표시"""
        profiles_resp = MagicMock()
        profiles_resp.read.return_value = json.dumps({
            "profiles": [],
            "active": None,
        }).encode()
        profiles_resp.__enter__ = MagicMock(return_value=profiles_resp)
        profiles_resp.__exit__ = MagicMock(return_value=False)

        rate_resp = MagicMock()
        rate_resp.read.return_value = json.dumps({
            "active_profile": None,
            "profiles": [],
        }).encode()
        rate_resp.__enter__ = MagicMock(return_value=rate_resp)
        rate_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [profiles_resp, rate_resp]

        client = MagicMock()
        list_credential_profiles("C123", "ts123", client)

        client.chat_update.assert_called_once()
        kwargs = client.chat_update.call_args[1]
        assert "blocks" in kwargs


# ── register_credential_action_handlers ─────────────────────


class TestRegisterCredentialActionHandlers:
    """핸들러 등록 확인"""

    def test_registers_all_patterns(self):
        """모든 필요한 액션 패턴이 등록되어야 함"""
        app = MagicMock()
        register_credential_action_handlers(app, {})

        registered_patterns = []
        for c in app.action.call_args_list:
            pattern = c[0][0]
            registered_patterns.append(
                pattern.pattern if hasattr(pattern, "pattern") else str(pattern)
            )

        # 기존: credential_switch_*
        assert any("credential_switch" in p for p in registered_patterns)
        # 신규: save, delete, list, confirm/cancel
        assert any("credential_save_profile" in p for p in registered_patterns)
        assert any("credential_list_profiles" in p for p in registered_patterns)
        assert any("credential_delete_" in p for p in registered_patterns)
        assert any("credential_delete_confirm_" in p for p in registered_patterns)
        assert any("credential_delete_cancel" in p for p in registered_patterns)
