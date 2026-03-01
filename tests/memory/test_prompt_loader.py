"""prompt_loader 모듈 테스트

프롬프트 파일 로드 및 캐싱 기능을 테스트합니다.
"""

import pytest

from seosoyoung.slackbot.plugins.memory.prompt_loader import (
    DEFAULT_PROMPT_DIR,
    PROMPT_DIR,
    _resolve_prompt_path,
    load_prompt,
    load_prompt_cached,
)


class TestPromptDir:
    """프롬프트 디렉토리 테스트"""

    def test_prompt_dir_exists(self):
        """prompt_files 디렉토리가 존재"""
        assert PROMPT_DIR.exists()
        assert PROMPT_DIR.is_dir()


class TestLoadPrompt:
    """load_prompt 함수 테스트"""

    def test_load_existing_file(self):
        """존재하는 파일을 로드"""
        content = load_prompt("channel_observer_system.txt")
        assert len(content) > 0
        assert "서소영" in content

    def test_load_missing_file_raises(self):
        """존재하지 않는 파일은 FileNotFoundError"""
        with pytest.raises(FileNotFoundError, match="프롬프트 파일 없음"):
            load_prompt("nonexistent_file.txt")

    def test_loaded_content_is_stripped(self):
        """로드된 내용의 앞뒤 공백이 제거됨"""
        content = load_prompt("channel_observer_system.txt")
        assert content == content.strip()


class TestLoadPromptCached:
    """load_prompt_cached 함수 테스트"""

    def test_cached_returns_same_content(self):
        """캐시된 로드가 동일한 내용을 반환"""
        first = load_prompt_cached("channel_observer_system.txt")
        second = load_prompt_cached("channel_observer_system.txt")
        assert first == second

    def test_cached_file_not_found(self):
        """캐시에 없는 파일도 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            load_prompt_cached("does_not_exist.txt")


class TestAllPromptFilesExist:
    """모든 필수 프롬프트 파일이 존재하는지 확인"""

    REQUIRED_FILES = [
        # 채널 관찰 프롬프트
        "channel_observer_system.txt",
        "channel_observer_user.txt",
        "channel_intervene_system.txt",
        "channel_intervene_user.txt",
        "digest_compressor_system.txt",
        "digest_compressor_retry.txt",
        # OM 프롬프트
        "om_observer_system.txt",
        "om_observer_user.txt",
        "om_reflector_system.txt",
        "om_reflector_retry.txt",
        "om_promoter_system.txt",
        "om_compactor_system.txt",
    ]

    @pytest.mark.parametrize("filename", REQUIRED_FILES)
    def test_file_exists(self, filename):
        """각 프롬프트 파일이 존재하고 비어있지 않음"""
        content = load_prompt(filename)
        assert len(content) > 10, f"{filename}의 내용이 너무 짧습니다"


class TestPromptDirOverride:
    """환경변수로 프롬프트 디렉토리를 오버라이드하는 기능 테스트"""

    def test_default_prompt_dir_unchanged(self):
        """PROMPT_DIR 하위호환: 기본 경로가 유지됨"""
        assert PROMPT_DIR == DEFAULT_PROMPT_DIR

    def test_om_prompt_dir_override(self, tmp_path, monkeypatch):
        """OM_PROMPT_DIR 환경변수로 om_* 파일을 오버라이드"""
        custom = tmp_path / "custom_om"
        custom.mkdir()
        (custom / "om_observer_system.txt").write_text("custom om observer", encoding="utf-8")
        monkeypatch.setenv("OM_PROMPT_DIR", str(custom))

        path = _resolve_prompt_path("om_observer_system.txt")
        assert path == custom / "om_observer_system.txt"

        content = load_prompt("om_observer_system.txt")
        assert content == "custom om observer"

    def test_channel_prompt_dir_override(self, tmp_path, monkeypatch):
        """CHANNEL_PROMPT_DIR 환경변수로 channel_*/digest_*/intervention_* 파일을 오버라이드"""
        custom = tmp_path / "custom_channel"
        custom.mkdir()
        (custom / "channel_observer_system.txt").write_text("custom channel observer", encoding="utf-8")
        (custom / "digest_compressor_system.txt").write_text("custom digest", encoding="utf-8")
        (custom / "intervention_mode_system.txt").write_text("custom intervention", encoding="utf-8")
        monkeypatch.setenv("CHANNEL_PROMPT_DIR", str(custom))

        assert _resolve_prompt_path("channel_observer_system.txt") == custom / "channel_observer_system.txt"
        assert _resolve_prompt_path("digest_compressor_system.txt") == custom / "digest_compressor_system.txt"
        assert _resolve_prompt_path("intervention_mode_system.txt") == custom / "intervention_mode_system.txt"

        assert load_prompt("channel_observer_system.txt") == "custom channel observer"

    def test_common_prompt_files_dir_override(self, tmp_path, monkeypatch):
        """PROMPT_FILES_DIR 환경변수로 모든 프롬프트 파일을 오버라이드"""
        custom = tmp_path / "custom_all"
        custom.mkdir()
        (custom / "om_observer_system.txt").write_text("common override", encoding="utf-8")
        monkeypatch.setenv("PROMPT_FILES_DIR", str(custom))

        path = _resolve_prompt_path("om_observer_system.txt")
        assert path == custom / "om_observer_system.txt"

    def test_specific_dir_takes_priority_over_common(self, tmp_path, monkeypatch):
        """개별 디렉토리 환경변수가 공통 PROMPT_FILES_DIR보다 우선"""
        common_dir = tmp_path / "common"
        common_dir.mkdir()
        (common_dir / "om_observer_system.txt").write_text("from common", encoding="utf-8")

        specific_dir = tmp_path / "specific"
        specific_dir.mkdir()
        (specific_dir / "om_observer_system.txt").write_text("from specific", encoding="utf-8")

        monkeypatch.setenv("PROMPT_FILES_DIR", str(common_dir))
        monkeypatch.setenv("OM_PROMPT_DIR", str(specific_dir))

        content = load_prompt("om_observer_system.txt")
        assert content == "from specific"

    def test_fallback_to_default_when_env_empty(self, monkeypatch):
        """환경변수가 비어있으면 배포본 기본 경로로 폴백"""
        monkeypatch.setenv("OM_PROMPT_DIR", "")
        monkeypatch.setenv("PROMPT_FILES_DIR", "")

        path = _resolve_prompt_path("om_observer_system.txt")
        assert path == DEFAULT_PROMPT_DIR / "om_observer_system.txt"

    def test_fallback_to_default_when_file_missing_in_override(self, tmp_path, monkeypatch):
        """오버라이드 디렉토리에 파일이 없으면 기본 경로로 폴백"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setenv("OM_PROMPT_DIR", str(empty_dir))

        path = _resolve_prompt_path("om_observer_system.txt")
        assert path == DEFAULT_PROMPT_DIR / "om_observer_system.txt"

    def test_fallback_to_common_when_specific_missing(self, tmp_path, monkeypatch):
        """개별 디렉토리에 파일 없으면 공통 디렉토리로 폴백"""
        empty_specific = tmp_path / "specific"
        empty_specific.mkdir()

        common_dir = tmp_path / "common"
        common_dir.mkdir()
        (common_dir / "om_observer_system.txt").write_text("from common fallback", encoding="utf-8")

        monkeypatch.setenv("OM_PROMPT_DIR", str(empty_specific))
        monkeypatch.setenv("PROMPT_FILES_DIR", str(common_dir))

        content = load_prompt("om_observer_system.txt")
        assert content == "from common fallback"

    def test_unrecognized_prefix_uses_common_then_default(self, tmp_path, monkeypatch):
        """접두사가 매핑에 없는 파일은 공통 → 기본 순서로 검색"""
        custom = tmp_path / "common"
        custom.mkdir()
        (custom / "unknown_prefix_file.txt").write_text("from common", encoding="utf-8")
        monkeypatch.setenv("PROMPT_FILES_DIR", str(custom))

        path = _resolve_prompt_path("unknown_prefix_file.txt")
        assert path == custom / "unknown_prefix_file.txt"

    def test_env_not_set_uses_default(self):
        """환경변수 미설정 시 기본 경로 사용"""
        path = _resolve_prompt_path("om_observer_system.txt")
        assert path == DEFAULT_PROMPT_DIR / "om_observer_system.txt"


class TestChannelPromptsFromFiles:
    """외부 파일 기반 channel_prompts 빌더 테스트"""

    def test_channel_observer_system_prompt_has_reactions(self):
        """채널 관찰 시스템 프롬프트에 AVAILABLE REACTIONS 섹션이 포함"""
        from seosoyoung.slackbot.plugins.channel_observer.prompts import build_channel_observer_system_prompt

        prompt = build_channel_observer_system_prompt()
        assert "AVAILABLE REACTIONS" in prompt
        assert "eyes" in prompt
        assert "laughing" in prompt
        assert "fire" in prompt

    def test_channel_intervene_system_prompt(self):
        """채널 개입 응답 시스템 프롬프트가 정상 로드"""
        from seosoyoung.slackbot.plugins.channel_observer.prompts import get_channel_intervene_system_prompt

        prompt = get_channel_intervene_system_prompt()
        assert "서소영" in prompt
        assert "개입" in prompt or "응답" in prompt or "대화" in prompt

    def test_channel_intervene_user_prompt(self):
        """채널 개입 응답 사용자 프롬프트가 정상 구성"""
        from seosoyoung.slackbot.plugins.channel_observer.prompts import build_channel_intervene_user_prompt

        prompt = build_channel_intervene_user_prompt(
            digest="테스트 다이제스트",
            recent_messages=[{"ts": "1.0", "user": "U1", "text": "최근 메시지"}],
            trigger_message={"ts": "2.0", "user": "U2", "text": "트리거"},
            target="channel",
            observer_reason="관찰자 초안",
        )
        assert "테스트 다이제스트" in prompt
        assert "최근 메시지" in prompt
        assert "트리거" in prompt
        assert "관찰자 초안" in prompt


class TestOMPromptsFromFiles:
    """외부 파일 기반 OM prompts 빌더 테스트"""

    def test_observer_system_prompt(self):
        """Observer 시스템 프롬프트가 정상 로드"""
        from seosoyoung.slackbot.plugins.memory.prompts import build_observer_system_prompt

        prompt = build_observer_system_prompt()
        assert "서소영" in prompt
        assert "LONG-TERM MEMORY CANDIDATES" in prompt

    def test_reflector_system_prompt(self):
        """Reflector 시스템 프롬프트가 정상 로드"""
        from seosoyoung.slackbot.plugins.memory.prompts import build_reflector_system_prompt

        prompt = build_reflector_system_prompt()
        assert "서소영" in prompt
        assert "COMPRESSION" in prompt

    def test_promoter_prompt(self):
        """Promoter 프롬프트가 정상 로드 및 포매팅"""
        from seosoyoung.slackbot.plugins.memory.prompts import build_promoter_prompt

        prompt = build_promoter_prompt(
            existing_persistent="기존 기억",
            candidate_entries="후보 항목",
        )
        assert "기존 기억" in prompt
        assert "후보 항목" in prompt

    def test_compactor_prompt(self):
        """Compactor 프롬프트가 정상 로드 및 포매팅"""
        from seosoyoung.slackbot.plugins.memory.prompts import build_compactor_prompt

        prompt = build_compactor_prompt(
            persistent_memory="장기 기억 내용",
            target_tokens=3000,
        )
        assert "장기 기억 내용" in prompt
        assert "3000" in prompt
