from __future__ import annotations

import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from seosoyoung.slackbot.handlers.lore_search import (
    _answer_language,
    build_search_blocks,
    judge_answer_language,
    judge_lore_search,
    log_lore_search_routing_status,
    missing_lore_search_settings,
    search_lore,
    try_handle_lore_search,
)
from seosoyoung.slackbot.handlers import mention
from seosoyoung.slackbot.config import Config


def _config(**overrides):
    values = {
        "jev_api_key": "jev-test-key",
        "lore_search_url": "https://lore-search.example/",
        "lore_search_api_key": "lore-test-key",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _response(body, *, content_type="application/json", lines=()):
    response = MagicMock()
    response.json.return_value = body
    response.headers = {"content-type": content_type}
    response.iter_lines.return_value = list(lines)
    response.raise_for_status.return_value = None
    return response


def _search_body(results=None):
    return {
        "query": "아리엘라 설정",
        "search_url": "https://lore-search.example/search",
        "results": results or [],
    }


class TestJevIntentRequest:
    def test_sends_lore_search_question_and_reads_noul_score(self):
        with patch(
            "seosoyoung.slackbot.handlers.lore_search.requests.post",
            return_value=_response({"answers": {"lore_search": {"type": "noul", "noul": 0.71}}}),
        ) as post:
            score = judge_lore_search("루카가 왜 떠났는지 찾아줘", "jev-test-key")

        assert score == 0.71
        args, kwargs = post.call_args
        assert args[0] == "https://api.typesafe.ai/v1/systemone"
        assert kwargs["headers"]["Authorization"] == "Bearer jev-test-key"
        assert kwargs["json"]["model"] == "jev-latest"
        state = json.loads(kwargs["json"]["state"])
        assert state == {
            "context": "엠버 앤 블레이드 게임의 로어(인물, 사건, 세계관, 설정, 대사)를 다루는 슬랙 봇에게 온 발화",
            "user_prompt": "루카가 왜 떠났는지 찾아줘",
        }
        assert kwargs["json"]["questions"]["lore_search"] == {
            "type": "noul",
            "instructions": "이 발화가 로어 정보나 기존 대사를 찾아 달라는 질의인가?",
            "criteria": {"true": "요청함", "false": "요청하지 않음"},
        }

    def test_rejects_missing_or_out_of_range_score(self):
        with patch(
            "seosoyoung.slackbot.handlers.lore_search.requests.post",
            return_value=_response({"answers": {"lore_search": {"type": "noul", "noul": 1.2}}}),
        ):
            with pytest.raises(ValueError):
                judge_lore_search("질의", "jev-test-key")


class TestJevAnswerLanguageRequest:
    def test_sends_exact_two_questions_and_reads_noul_and_choice(self):
        response = _response({"answers": {
            "answer_language_requested": {"type": "noul", "noul": 0.88},
            "answer_language": {"type": "choice", "choice": "ja", "probabilities": {"ja": 0.86}, "confidence": 0.86},
        }})
        with patch("seosoyoung.slackbot.handlers.lore_search.requests.post", return_value=response) as post:
            score, choice = judge_answer_language("일본어로 찾아줘", "jev-test-key")

        assert (score, choice) == (0.88, "ja")
        payload = post.call_args.kwargs["json"]
        assert payload["model"] == "jev-latest"
        assert json.loads(payload["state"]) == {
            "context": "엠버 앤 블레이드 게임의 로어(인물, 사건, 세계관, 설정, 대사)를 다루는 슬랙 봇에게 온 발화. 기본 답변 언어는 한국어",
            "user_prompt": "일본어로 찾아줘",
        }
        assert payload["questions"] == {
            "answer_language_requested": {
                "type": "noul",
                "instructions": "이 발화가 다른 언어로 답변할 것을 요구하고 있는가?",
                "criteria": {"true": "요구함", "false": "요구하지 않음"},
            },
            "answer_language": {
                "type": "choice",
                "instructions": "이 발화가 답변을 받고자 하는 언어",
                "criteria": {
                    "ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어", "fr": "프랑스어",
                    "de": "독일어", "pt": "포르투갈어", "es": "스페인어", "ru": "러시아어",
                    "other": "그 밖의 언어",
                },
            },
        }

    @pytest.mark.parametrize(
        ("score", "choice", "expected"),
        [(0.69, "ja", "ko"), (0.7, "ko", "ko"), (0.7, "ja", "ja"), (0.9, "other", "other")],
    )
    def test_applies_requested_language_threshold(self, score, choice, expected):
        assert _answer_language(score, choice) == expected


class TestLoreSearchApiRequest:
    def test_posts_ndjson_request_and_returns_streamed_result(self):
        result = _search_body([{"title": "아리엘라", "text": "전체 본문"}])
        lines = [
            '{"type":"progress","stage":"strategy","message":"검색 방법을 고르는 중"}'.encode("utf-8"),
            b'{"type":"jev_request","payload":{"private":"hidden"}}',
            (json.dumps({"type": "result", **result}, ensure_ascii=False)).encode("utf-8"),
        ]
        progress = []
        with patch(
            "seosoyoung.slackbot.handlers.lore_search.requests.post",
            return_value=_response({}, content_type="application/x-ndjson", lines=lines),
        ) as post:
            actual = search_lore("루카의 과거", "https://lore-search.example/", "lore-test-key", progress.append)

        assert actual == result
        assert progress == ["검색 방법을 고르는 중"]
        args, kwargs = post.call_args
        assert args[0] == "https://lore-search.example/api/search"
        assert kwargs["headers"] == {
            "Authorization": "Bearer lore-test-key", "Accept": "application/x-ndjson",
        }
        assert kwargs["json"] == {"query": "루카의 과거"}
        assert kwargs["stream"] is True

    def test_accepts_older_json_response_without_progress(self):
        body = _search_body([{"title": "아리엘라", "excerpt": "이전 서버"}])
        progress = MagicMock()
        with patch(
            "seosoyoung.slackbot.handlers.lore_search.requests.post",
            return_value=_response(body),
        ):
            actual = search_lore("아리엘라", "https://lore-search.example", "key", progress)
        assert actual == body
        progress.assert_not_called()


class TestLoreSearchRouting:
    @pytest.mark.parametrize(
        ("config", "status", "missing"),
        [(_config(), "enabled", "none"), (_config(lore_search_url=""), "disabled", "LORE_SEARCH_URL")],
    )
    def test_startup_status_logs_enabled_state_and_setting_names_only(self, config, status, missing):
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", config, create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.logger") as logger:
            log_lore_search_routing_status()
        logger.info.assert_called_once_with("Lore-search routing status=%s missing_settings=%s", status, missing)

    def test_missing_settings_names_match_disabled_routing_values(self):
        config = _config(jev_api_key=" ", lore_search_api_key=None)
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", config, create=True):
            assert missing_lore_search_settings() == ["JEV_API_KEY", "LORE_SEARCH_API_KEY"]

    @pytest.mark.parametrize("missing", ["jev_api_key", "lore_search_url", "lore_search_api_key"])
    def test_missing_setting_disables_search_routing(self, missing):
        with patch(
            "seosoyoung.slackbot.handlers.lore_search.Config.lore_search",
            _config(**{missing: ""}),
            create=True,
        ), patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search") as judge:
            handled = try_handle_lore_search(
                "로어를 찾아줘", MagicMock(), client=MagicMock(), channel="C123", thread_ts="thread-1",
            )
        assert handled is False
        judge.assert_not_called()

    def test_threshold_searches_updates_progress_and_posts_blocks(self):
        say = MagicMock(return_value={"ts": "placeholder-1"})
        client = MagicMock()
        query = "그림자가 펜릭스를 유혹하는 대사를 찾아줘"
        result = _search_body([{
            "title": "scene_ending · ending · dialogue",
            "source_type": "shay",
            "id": "shay:scene:dialogue",
            "text": "펜릭스 헤이븐: 불장난은 끝이야, 그림자.\n성채수를 태워서 대악마를\n펜릭스 헤이븐 [en]: Playtime's over.",
            "translations": {},
            "path": "act3/ending.json",
            "relevance": 0.86,
            "participants": ["펜릭스 헤이븐", "아리엘라의 그림자"],
        }])

        def stream(_query, _url, _key, *, on_progress):
            on_progress("질의에 맞는 검색 방법을 고르는 중")
            return result

        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", return_value=0.7), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_answer_language", return_value=(0.05, "ko")), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore", side_effect=stream) as search, \
             patch("seosoyoung.slackbot.handlers.lore_search.logger") as logger:
            handled = try_handle_lore_search(query, say, client=client, channel="C123", thread_ts="thread-1")

        assert handled is True
        logger.info.assert_any_call(
            "Jev lore-search intent score=%s threshold=%.1f decision=%s", 0.7, 0.7, "search",
        )
        logger.info.assert_any_call(
            "Jev lore-search answer language requested_score=%s choice=%s decision=%s", 0.05, "ko", "ko",
        )
        search.assert_called_once()
        assert search.call_args.kwargs["on_progress"]
        say.assert_called_once_with(text="🔎 로어를 찾고 있습니다", thread_ts="thread-1")
        client.chat_update.assert_any_call(
            channel="C123", ts="placeholder-1",
            text="🔎 로어를 찾고 있습니다 · 질의에 맞는 검색 방법을 고르는 중",
        )
        final_update = client.chat_update.call_args.kwargs
        assert final_update["blocks"][-1]["elements"][0]["url"] == result["search_url"]
        assert len(final_update["blocks"]) <= 50

    def test_search_starts_while_language_judgement_is_still_running(self):
        language_started = Event()
        language_release = Event()
        result = _search_body([{"title": "아리엘라", "source_type": "lore", "text": "설정"}])

        def slow_language(*_args):
            language_started.set()
            assert language_release.wait(2)
            return 0.9, "ja"

        def search(*_args, **_kwargs):
            assert language_started.wait(1)
            assert not language_release.is_set()
            language_release.set()
            return result

        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", return_value=0.9), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_answer_language", side_effect=slow_language), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore", side_effect=search):
            handled = try_handle_lore_search(
                "日本語で設定を探して", MagicMock(return_value={"ts": "placeholder"}),
                client=MagicMock(), channel="C123", thread_ts="thread-1",
            )
        assert handled is True

    def test_language_judgement_failure_falls_back_to_korean(self):
        client = MagicMock()
        result = _search_body([{
            "title": "아리엘라", "source_type": "lore", "text": "한국어 본문",
            "translations": {"ja": "日本語の本文"},
        }])
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", return_value=0.9), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_answer_language", side_effect=RuntimeError("secret")), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore", return_value=result), \
             patch("seosoyoung.slackbot.handlers.lore_search.logger") as logger:
            handled = try_handle_lore_search(
                "질의", MagicMock(return_value={"ts": "placeholder"}),
                client=client, channel="C123", thread_ts="thread-1",
            )
        assert handled is True
        assert "한국어 본문" in json.dumps(client.chat_update.call_args.kwargs["blocks"], ensure_ascii=False)
        logger.warning.assert_called_once()

    def test_search_failure_deletes_the_placeholder(self):
        client = MagicMock()
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", return_value=0.9), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_answer_language", return_value=(0.05, "ko")), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore", side_effect=RuntimeError("private")), \
             patch("seosoyoung.slackbot.handlers.lore_search.logger") as logger:
            handled = try_handle_lore_search(
                "질의", MagicMock(return_value={"ts": "placeholder"}),
                client=client, channel="C123", thread_ts="thread-1",
            )
        assert handled is False
        client.chat_delete.assert_called_once_with(channel="C123", ts="placeholder")
        client.chat_update.assert_not_called()
        logger.warning.assert_called_once()

    def test_progress_updates_every_new_message_and_suppresses_duplicates(self):
        result = _search_body([{"title": "아리엘라", "source_type": "lore", "text": "설정"}])
        client = MagicMock()

        def stream(_query, _url, _key, *, on_progress):
            on_progress("첫 단계")
            on_progress("너무 빠른 단계")
            on_progress("다음 단계")
            on_progress("다음 단계")
            on_progress("마지막 단계")
            on_progress("마지막 단계")
            return result

        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", return_value=0.9), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_answer_language", return_value=(0.05, "ko")), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore", side_effect=stream):
            try_handle_lore_search(
                "질의", MagicMock(return_value={"ts": "placeholder"}),
                client=client, channel="C123", thread_ts="thread-1",
            )

        progress_texts = [
            call.kwargs["text"] for call in client.chat_update.call_args_list if "blocks" not in call.kwargs
        ]
        assert progress_texts == [
            "🔎 로어를 찾고 있습니다 · 첫 단계",
            "🔎 로어를 찾고 있습니다 · 너무 빠른 단계",
            "🔎 로어를 찾고 있습니다 · 다음 단계",
            "🔎 로어를 찾고 있습니다 · 마지막 단계",
        ]

    def test_score_below_threshold_skips_search(self):
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", return_value=0.69), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore") as search:
            say = MagicMock()
            handled = try_handle_lore_search("대사 고쳐줘", say, client=MagicMock(), channel="C123", thread_ts="thread-1")
        assert handled is False
        search.assert_not_called()
        say.assert_not_called()


class TestResultBlocks:
    def test_near_miss_result_is_labeled_and_counted(self):
        blocks = build_search_blocks(_search_body([{
            "title": "장면 · 구간",
            "source_type": "shay",
            "text": "화자: 대사",
            "path": "act0_c_1_core.yaml",
            "relevance": 0.46,
            "near_miss": True,
            "participants": ["화자"],
        }]))

        assert blocks[1]["elements"][0]["text"] == (
            "질의 「아리엘라 설정」 · 적중 1건 · 합격선에 조금 못 미친 근접 결과 1건 포함"
        )
        assert blocks[4]["elements"][0]["text"] == (
            "근접 결과 · 대사 · act0_c_1_core (구간) · 관련도 0.46"
        )

    @pytest.mark.parametrize("include_near_miss", [False, True])
    def test_false_or_missing_near_miss_keeps_existing_text(self, include_near_miss):
        item = {
            "title": "아리엘라 설정",
            "source_type": "lore",
            "text": "설정",
            "path": "characters/ar.yaml",
            "relevance": 0.72,
        }
        if include_near_miss:
            item["near_miss"] = False

        blocks = build_search_blocks(_search_body([item]))

        assert blocks[1]["elements"][0]["text"] == "질의 「아리엘라 설정」 · 적중 1건"
        assert blocks[4]["elements"][0]["text"] == "설정 문서 · characters/ar.yaml · 관련도 0.72"

    def test_dialogue_uses_rich_text_quote_and_removes_english_source_lines(self):
        body = _search_body([{
            "title": "act3_z1_8_ending · r2_act3_ending · dialogue",
            "id": "shay:act3_z1_8_ending:dialogue",
            "source_type": "shay",
            "text": "펜릭스 헤이븐: 불장난은 끝이야, 그림자.\n성채수를 태워서 대악마를\n펜릭스 헤이븐 [en]: Playtime's over, Shadow.\nYou're burning the Arbor to free\nthe Archdemon, aren't you?\n아리엘라의 그림자: 하! 한심하긴.",
            "translations": {
                "ja": "フェンリクス: 遊びは終わりだ、影よ。\n樹木を燃やして悪魔を解放するつもりだね？\nアリエラ: なんて愚かなんだ。",
            },
            "path": "narrative/_rev2/_core/_act3/z1_boss/act3_z1_8_ending.yaml",
            "relevance": 0.86,
            "participants": ["펜릭스 헤이븐", "아리엘라의 그림자"],
        }])
        blocks = build_search_blocks(body)
        serialized = json.dumps(blocks, ensure_ascii=False)
        assert blocks[0]["text"]["text"] == "📜 로어 검색 결과"
        assert blocks[2]["type"] == "divider"
        assert blocks[3]["text"]["text"] == "*1. 펜릭스 헤이븐 ↔ 아리엘라의 그림자*"
        assert blocks[4]["elements"][0]["text"] == "대사 · act3_z1_8_ending (dialogue) · 관련도 0.86"
        assert blocks[5]["elements"][0]["type"] == "rich_text_quote"
        quote_elements = blocks[5]["elements"][0]["elements"]
        quote_text = "".join(element["text"] for element in quote_elements)
        assert quote_elements[0] == {"type": "text", "text": "펜릭스 헤이븐", "style": {"bold": True}}
        assert quote_text == (
            "펜릭스 헤이븐: 불장난은 끝이야, 그림자. 성채수를 태워서 대악마를\n"
            "아리엘라의 그림자: 하! 한심하긴."
        )
        assert "Playtime's over" not in serialized
        assert "You're burning the Arbor to free" not in serialized
        assert "the Archdemon, aren't you?" not in serialized
        assert blocks[-1]["type"] == "actions"

        japanese_blocks = build_search_blocks(body, language="ja")
        japanese_quote = "".join(
            element["text"] for element in japanese_blocks[5]["elements"][0]["elements"]
        )
        assert japanese_quote == (
            "フェンリクス: 遊びは終わりだ、影よ。 樹木を燃やして悪魔を解放するつもりだね？\n"
            "アリエラ: なんて愚かなんだ。"
        )

    def test_lore_section_displays_headings_and_full_body_over_3000_characters(self):
        long_body = "### 기본 정보\n" + ("아리엘라의 설정입니다. " * 260)
        blocks = build_search_blocks(_search_body([{
            "title": "아리엘라 애시우드 · 배경과 숨은 설정",
            "source_type": "lore",
            "text": long_body,
            "translations": {"ko": long_body},
            "path": "characters/ar.yaml",
            "relevance": 0.94,
        }]))
        assert blocks[4]["elements"][0]["text"] == "설정 문서 · characters/ar.yaml · 관련도 0.94"
        body_blocks = [block for block in blocks if block["type"] == "section" and block is not blocks[3]]
        rendered = "".join(block["text"]["text"] for block in body_blocks)
        assert len(long_body) > 3000
        assert "*기본 정보*" in rendered
        assert "아리엘라의 설정입니다." in rendered
        assert len(blocks) <= 50
        assert all(len(block["text"]["text"]) <= 3000 for block in blocks if block["type"] == "section")

    def test_markdown_links_show_only_their_labels_in_lore_and_dialogue_bodies(self):
        linked_text = "[芬利克斯](fx.yaml), [망각의 성채](sanctuary.yaml)"
        blocks = build_search_blocks(_search_body([
            {"title": "펜릭스 설정", "source_type": "lore", "text": linked_text},
            {
                "title": "ending · dialogue",
                "source_type": "shay",
                "text": f"펜릭스 헤이븐: {linked_text}",
                "path": "act3_z1_8_ending.yaml",
                "participants": ["펜릭스 헤이븐"],
            },
        ]))

        lore_body = next(
            block["text"]["text"] for block in blocks
            if block["type"] == "section" and "芬利克斯" in block["text"]["text"]
        )
        dialogue_body = "".join(
            element["text"] for block in blocks if block["type"] == "rich_text"
            for element in block["elements"][0]["elements"]
        )

        assert lore_body == "芬利克斯, 망각의 성채"
        assert dialogue_body == "펜릭스 헤이븐: 芬利克斯, 망각의 성채"
        assert "fx.yaml" not in lore_body + dialogue_body
        assert "sanctuary.yaml" not in lore_body + dialogue_body

    def test_blocks_cap_long_body_with_search_site_suffix(self):
        huge = "내용 " * 50000
        blocks = build_search_blocks(_search_body([{
            "title": "아리엘라 설정", "source_type": "lore", "text": huge,
        }]))
        assert len(blocks) <= 50
        assert blocks[-2]["text"]["text"].endswith("… 전체는 검색 사이트에서")
        assert len(blocks[-2]["text"]["text"]) <= 3000

    def test_requested_translation_and_all_missing_fallback_notice(self):
        translated = {
            "title": "대화", "source_type": "shay", "text": "한국어",
            "translations": {"ja": "日本語"}, "participants": ["화자"],
        }
        missing = {
            "title": "설정", "source_type": "lore", "text": "한국어 설정\nEnglish",
            "translations": {"ko": "한국어 설정", "en": "English"},
        }
        full = build_search_blocks(_search_body([translated]), "ja")
        assert "日本語 본문" not in json.dumps(full, ensure_ascii=False)
        assert "日本語" in json.dumps(full, ensure_ascii=False)
        assert "요청하신" not in full[1]["elements"][0]["text"]
        assert "日本語" in full[4]["elements"][0]["text"]

        partial = build_search_blocks(_search_body([translated, missing]), "ja")
        assert "일부 결과는 일본어 번역이 없어 한국어로 보여 드립니다" in partial[1]["elements"][0]["text"]
        assert "한국어 설정" in json.dumps(partial, ensure_ascii=False)
        assert "English" not in json.dumps(partial, ensure_ascii=False)

        none = build_search_blocks(_search_body([missing]), "ja")
        assert "요청하신 일본어 번역이 없어 한국어로 보여 드립니다" in none[1]["elements"][0]["text"]

    def test_other_language_always_uses_generic_fallback_notice(self):
        blocks = build_search_blocks(_search_body([{
            "title": "설정", "source_type": "lore", "text": "한국어 설정", "translations": {"en": "English"},
        }]), "other")
        assert "요청하신 언어의 번역이 없어 한국어로 보여 드립니다" in blocks[1]["elements"][0]["text"]
        assert "한국어 설정" in json.dumps(blocks, ensure_ascii=False)

    def test_english_translation_is_selected_with_korean_static_labels(self):
        blocks = build_search_blocks(_search_body([{
            "title": "대화", "source_type": "shay", "text": "펜릭스: 한국어",
            "translations": {"en": "Fenrix Haven: I will find it."}, "participants": ["펜릭스"],
        }]), "en")
        serialized = json.dumps(blocks, ensure_ascii=False)
        assert "Fenrix Haven" in serialized
        assert "한국어" not in serialized
        assert "📜 로어 검색 결과" in serialized
        assert "검색 사이트에서 보기" in serialized


def _register_mention_handler(session_manager):
    dependencies = {
        "session_manager": session_manager,
        "restart_manager": SimpleNamespace(is_pending=False),
        "get_running_session_count": MagicMock(return_value=0),
        "run_claude_in_session": MagicMock(),
        "check_permission": MagicMock(return_value=True),
        "get_user_role": MagicMock(return_value={"username": "tester", "role": "user"}),
        "send_restart_confirmation": MagicMock(),
    }
    registered = {}
    app = MagicMock()

    def capture(event_type):
        def decorator(function):
            registered[event_type] = function
            return function
        return decorator

    app.event = capture
    mention.register_mention_handlers(app, dependencies)
    return registered["app_mention"], dependencies


class TestMentionHandlerIntegration:
    def test_new_thread_mention_can_be_routed_to_lore_search(self):
        session_manager = MagicMock()
        session_manager.get.return_value = None
        handler, _dependencies = _register_mention_handler(session_manager)
        event = {
            "user": "U123", "text": "<@BOT> 루카 설정 찾아줘", "channel": "C123",
            "ts": "1234567890.000002", "thread_ts": "1234567890.000001",
        }
        say = MagicMock()
        client = MagicMock()
        with patch("seosoyoung.slackbot.handlers.mention.try_handle_lore_search", return_value=True) as route, \
             patch("seosoyoung.slackbot.handlers.mention.create_session_and_run_claude") as general:
            handler(event, say, client)
        route.assert_called_once_with(
            "루카 설정 찾아줘", say=say, client=client, channel="C123", thread_ts="1234567890.000001",
        )
        general.assert_not_called()

    def test_existing_session_thread_skips_lore_search(self):
        session_manager = MagicMock()
        session_manager.get.return_value = SimpleNamespace(user_id="U123")
        handler, _dependencies = _register_mention_handler(session_manager)
        event = {
            "user": "U123", "text": "<@BOT> 루카 설정 찾아줘", "channel": "C123",
            "ts": "1234567890.000002", "thread_ts": "1234567890.000001",
        }
        with patch("seosoyoung.slackbot.handlers.mention.try_handle_lore_search") as route, \
             patch("seosoyoung.slackbot.handlers.mention.process_thread_message"):
            handler(event, MagicMock(), MagicMock())
        route.assert_not_called()
