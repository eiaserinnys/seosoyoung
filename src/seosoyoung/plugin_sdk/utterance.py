"""`<utterance>...</utterance>` 짝 추출 pure 유틸 (사이클 260518.01).

본 모듈은 *블록 단위 utterance 게이트*의 정본 매처다. 호출자는 thinking 블록 /
text 블록 (text_start ~ text_end 트리오) / complete 블록 (final output) *각각의
텍스트만* 넘긴다. 그 결과 한 블록의 우발 ``<utterance>`` 토큰이 다른 블록의
닫힘 태그와 짝지어지지 않는다.

직전 사이클(260513.01)의 *누적 transcript 검색* 정책은 사고 사례 (세션
``c2a12c38-9ab3-4d78-ba1f-3f5fca94c418`` / 채널 ``C08KT1HDU5U``)에서 본체 Opus가
thinking에 ``"Output the utterance in <utterance> tags."`` 같은 메타 설명을 적어
우발 토큰이 등장 → text 묶음의 정상 ``</utterance>``와 인접 → 한 덩이 매치로
약 1.5 KB 분석 텍스트 전체를 슬랙에 누출했다 (R7 위임자 확인). 본 사이클은
누적 자체를 *애초에 만들지 않음*으로써 차단한다.

책임 분리:
- 본 유틸은 *strip된 매치 본문 list*만 반환한다 (dedupe 안 함).
- 빈 utterance(``<utterance></utterance>``)는 strip 후 빈 문자열로 list에 포함된다.
- 빈 문자열 필터 / dedupe / 등장 순서 / 게시 정책은 호출자가 결정한다.
"""

from __future__ import annotations

import re

_UTTERANCE_RE = re.compile(r"<utterance>(.*?)</utterance>", re.DOTALL)


def extract_utterance_matches(text: str | None) -> list[str]:
    """주어진 텍스트에서 ``<utterance>(.*?)</utterance>`` 매치를 strip된 list로 반환.

    Args:
        text: 한 블록의 텍스트 (thinking 이벤트 본문 / text 블록 buffer / final output).
            ``None`` 또는 빈 문자열이면 빈 list.

    Returns:
        매치된 본문들의 list. 각 본문은 ``str.strip()`` 적용 후 담긴다.
        매치가 없으면 빈 list. 빈 utterance 태그는 ``""`` 항목으로 list에 포함된다.
    """
    if not text:
        return []
    return [m.strip() for m in _UTTERANCE_RE.findall(text)]
