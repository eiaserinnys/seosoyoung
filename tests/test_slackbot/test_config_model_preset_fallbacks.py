from seosoyoung.slackbot.config import ClaudeConfig


def test_model_preset_fallbacks_are_trimmed_and_empty_entries_removed(monkeypatch):
    monkeypatch.setenv(
        "SEOSOYOUNG_MODEL_PRESET_FALLBACKS",
        "claude-opus, codex-6.1-sol,",
    )

    assert ClaudeConfig().model_preset_fallbacks == ["claude-opus", "codex-6.1-sol"]


def test_model_preset_fallbacks_default_to_empty(monkeypatch):
    monkeypatch.delenv("SEOSOYOUNG_MODEL_PRESET_FALLBACKS", raising=False)

    assert ClaudeConfig().model_preset_fallbacks == []
