"""Pure utility: extract_utterance_matches.

`<utterance>...</utterance>` 짝을 *주어진 텍스트 안에서* non-greedy 매치한다.
매치 결과는 strip된 본문 list로 반환되며, 빈 list는 매치 없음을 뜻한다.
빈 utterance(`<utterance></utterance>`)는 strip 후 빈 문자열로 포함되며, 호출자가
빈 문자열 필터·dedupe·게시 정책을 결정한다 (책임 분리).

본 모듈은 *블록 단위 게이트*의 토대다 — 호출자가 thinking 블록 / text 블록 /
complete 블록 각각의 텍스트만 넘기므로, 한 블록의 우발 `<utterance>` 토큰이
다른 블록의 닫힘 태그와 짝지어지는 일이 없다 (사이클 260518.01).
"""

from seosoyoung.plugin_sdk.utterance import extract_utterance_matches


class TestExtractUtteranceMatches:
    def test_single_utterance(self):
        assert extract_utterance_matches(
            "분석 내용\n<utterance>안녕하세요</utterance>"
        ) == ["안녕하세요"]

    def test_multiple_utterances_preserve_order(self):
        text = (
            "<utterance>첫 번째</utterance>\n"
            "중간 텍스트\n"
            "<utterance>두 번째</utterance>"
        )
        assert extract_utterance_matches(text) == ["첫 번째", "두 번째"]

    def test_no_utterance_returns_empty_list(self):
        assert extract_utterance_matches("그냥 일반 텍스트입니다.") == []

    def test_empty_utterance_tag(self):
        assert extract_utterance_matches("<utterance></utterance>") == [""]

    def test_whitespace_only_utterance(self):
        assert extract_utterance_matches("<utterance>   \n  \n   </utterance>") == [""]

    def test_strip_inner_whitespace(self):
        assert extract_utterance_matches(
            "<utterance>  안녕  </utterance>"
        ) == ["안녕"]

    def test_multiline_content(self):
        assert extract_utterance_matches(
            "<utterance>\n첫째 줄\n둘째 줄\n</utterance>"
        ) == ["첫째 줄\n둘째 줄"]

    def test_no_dedupe_in_pure_layer(self):
        """순수 유틸은 dedupe하지 않는다 — 책임 분리.

        호출자가 블록별 매치 list를 받아 직접 dedupe + 게시 정책을 결정한다.
        """
        text = "<utterance>안녕</utterance>\n<utterance>안녕</utterance>"
        assert extract_utterance_matches(text) == ["안녕", "안녕"]

    def test_ignores_outside_text(self):
        assert extract_utterance_matches(
            "이것은 분석입니다.\n판단: 긍정적\n"
            "<utterance>실제 발화 내용</utterance>\n끝."
        ) == ["실제 발화 내용"]


class TestUtteranceTokenIsolationBetweenBlocks:
    """260518.01 회귀 보호: thinking 블록과 text 블록에 우발 토큰이 분산돼도
    각 블록을 *독립적으로* 호출하면 매치가 잘못 결합되지 않는다.

    사고 사례 (세션 c2a12c38-9ab3-4d78-ba1f-3f5fca94c418, 채널 C08KT1HDU5U):
    본체 Opus의 thinking 텍스트 끝부분에 "Now Phase 6: Output the utterance in
    `<utterance>` tags." 같은 *메타 설명*이 등장하여 닫힘 없는 `<utterance>` 토큰
    1개가 thinking 묶음 끝에 자리했다. 직후 text 묶음 마지막에 정상
    `<utterance>아까 도행님.../</utterance>` 1쌍이 있었다. 직전 사이클의
    *누적 transcript* 정책은 두 묶음을 평탄화해 한 문자열로 합쳤고, non-greedy
    `re.findall`이 한 덩이 매치로 18 KB 분석 텍스트 전체를 추출하여 슬랙에 누출.

    본 사이클은 블록을 *독립 호출*로 끊어 우발 매치를 원천 차단한다.
    """

    THINKING_BLOCK = (
        "ff8c9ff2-... no compression\n\n"
        "Now Phase 6: Output the utterance in <utterance> tags."
    )
    TEXT_BLOCK_NORMAL = (
        "Phase 5 완료. 멤버 갱신 2건, 발화 카드 기록 완료.\n\n"
        "**Phase 6: 최종 출력**\n\n"
        "<utterance>\n"
        "아까 도행님의 맥북 링크에 :beautiful: 를 눌렀는데,\n"
        "가만 생각하니 저는 그걸 *살* 쪽이 아니라\n"
        "그 안에 *들어갈* 쪽이었습니다.\n"
        "</utterance>"
    )

    EXPECTED_NORMAL_BODY = (
        "아까 도행님의 맥북 링크에 :beautiful: 를 눌렀는데,\n"
        "가만 생각하니 저는 그걸 *살* 쪽이 아니라\n"
        "그 안에 *들어갈* 쪽이었습니다."
    )

    def test_thinking_block_has_no_closing_tag_returns_empty(self):
        """우발 `<utterance>` 토큰만 있고 닫힘이 없으면 매치 0건."""
        assert extract_utterance_matches(self.THINKING_BLOCK) == []

    def test_text_block_extracts_normal_pair(self):
        """text 블록 안에서 정상 1짝만 추출."""
        assert extract_utterance_matches(self.TEXT_BLOCK_NORMAL) == [
            self.EXPECTED_NORMAL_BODY
        ]

    def test_blocks_called_independently_no_cross_block_match(self):
        """블록을 *독립적으로* 호출하면 우발 토큰이 다른 블록의 닫힘과 짝지어지지 않는다.

        본 사이클의 핵심 회귀 보호 — 누적 transcript 정책이라면 한 덩이로 18 KB를
        추출했을 입력이지만, 블록 단위 호출은 정상 1짝만 결과로 남긴다.
        """
        thinking_matches = extract_utterance_matches(self.THINKING_BLOCK)
        text_matches = extract_utterance_matches(self.TEXT_BLOCK_NORMAL)

        # 우발 토큰 블록: 0 매치
        assert thinking_matches == []
        # 정상 짝 블록: 1 매치 (본문만)
        assert text_matches == [self.EXPECTED_NORMAL_BODY]

        # 통합 결과 list (호출자가 누적): 정상 본문 1건만
        all_matches = thinking_matches + text_matches
        assert all_matches == [self.EXPECTED_NORMAL_BODY]

    def test_concatenated_input_demonstrates_legacy_leak(self):
        """직전 정책 시뮬레이션 — 누적 transcript에 평탄화하면 우발 매치가 발생한다.

        본 케이스는 *반례*로서 존재한다. 누적 입력에 정규식을 직접 돌리면
        우발 토큰 ~ 다음 블록의 닫힘 태그까지 한 덩이로 잡혀 *분석 텍스트가
        매치 캡처에 끼어든다*. 본 사이클은 그 누적을 *하지 않음*으로써 차단한다.
        """
        concatenated = self.THINKING_BLOCK + self.TEXT_BLOCK_NORMAL
        leaked = extract_utterance_matches(concatenated)

        # 누적 입력 — 한 덩이 매치 1건
        assert len(leaked) == 1
        leaked_body = leaked[0]

        # 매치 캡처 시작이 ` tags.` 잔해 (사고 메시지가 "tags."로 깨져 시작한 단서)
        assert leaked_body.startswith("tags.")
        # 매치 캡처 안에 Phase 6 분석 텍스트가 끼어듦
        assert "Phase 5 완료" in leaked_body
        assert "**Phase 6: 최종 출력**" in leaked_body
        # 매치 캡처 안에 정상 발화 본문도 통째로 포함됨 (분석과 함께 누출)
        assert "아까 도행님" in leaked_body

        # 결론: 본 케이스가 통과하면 직전 정책의 누출 메커니즘이 재현됨을 확인한다.
        # 본 사이클은 ``concatenated``를 *애초에 만들지 않음*으로써 이 매치가 일어날
        # 입력이 형성되지 않게 한다.
