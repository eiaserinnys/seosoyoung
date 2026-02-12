"""prompt_loader 모듈 테스트

프롬프트 파일 로드 및 캐싱 기능을 테스트합니다.
"""

import pytest

from seosoyoung.memory.prompt_loader import (
    PROMPT_DIR,
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
        "digest_compressor_system.txt",
        "digest_compressor_retry.txt",
        "intervention_mode_system.txt",
        "intervention_mode_user.txt",
        "intervention_mode_last_turn.txt",
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


class TestChannelPromptsFromFiles:
    """외부 파일 기반 channel_prompts 빌더 테스트"""

    def test_channel_observer_system_prompt_has_reactions(self):
        """채널 관찰 시스템 프롬프트에 AVAILABLE REACTIONS 섹션이 포함"""
        from seosoyoung.memory.channel_prompts import build_channel_observer_system_prompt

        prompt = build_channel_observer_system_prompt()
        assert "AVAILABLE REACTIONS" in prompt
        assert "eyes" in prompt
        assert "laughing" in prompt
        assert "fire" in prompt

    def test_intervention_mode_system_prompt(self):
        """개입 모드 시스템 프롬프트가 정상 로드"""
        from seosoyoung.memory.channel_prompts import get_intervention_mode_system_prompt

        prompt = get_intervention_mode_system_prompt()
        assert "서소영" in prompt
        assert "intervention" in prompt.lower() or "개입" in prompt or "CHARACTER VOICE" in prompt


class TestOMPromptsFromFiles:
    """외부 파일 기반 OM prompts 빌더 테스트"""

    def test_observer_system_prompt(self):
        """Observer 시스템 프롬프트가 정상 로드"""
        from seosoyoung.memory.prompts import build_observer_system_prompt

        prompt = build_observer_system_prompt()
        assert "서소영" in prompt
        assert "LONG-TERM MEMORY CANDIDATES" in prompt

    def test_reflector_system_prompt(self):
        """Reflector 시스템 프롬프트가 정상 로드"""
        from seosoyoung.memory.prompts import build_reflector_system_prompt

        prompt = build_reflector_system_prompt()
        assert "서소영" in prompt
        assert "COMPRESSION" in prompt

    def test_promoter_prompt(self):
        """Promoter 프롬프트가 정상 로드 및 포매팅"""
        from seosoyoung.memory.prompts import build_promoter_prompt

        prompt = build_promoter_prompt(
            existing_persistent="기존 기억",
            candidate_entries="후보 항목",
        )
        assert "기존 기억" in prompt
        assert "후보 항목" in prompt

    def test_compactor_prompt(self):
        """Compactor 프롬프트가 정상 로드 및 포매팅"""
        from seosoyoung.memory.prompts import build_compactor_prompt

        prompt = build_compactor_prompt(
            persistent_memory="장기 기억 내용",
            target_tokens=3000,
        )
        assert "장기 기억 내용" in prompt
        assert "3000" in prompt
