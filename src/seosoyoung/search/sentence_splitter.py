"""한/영 텍스트 문장 분할기.

전처리 → 분할 → 후처리 파이프라인으로 텍스트를 문장 단위로 분리한다.
"""

import re


# 문장 종결 구두점 + 후행 공백/끝을 매치하여 분할 지점을 찾는다.
_SENTENCE_PATTERN = re.compile(
    r"(.*?(?:\.{3}|[?!。.]))"  # 구두점까지 포함한 문장
    r"(?=\s|$)"                 # 뒤에 공백 또는 끝
)


def split_sentences(text: str, min_length: int = 2) -> list[str]:
    """텍스트를 문장 단위로 분할.

    Args:
        text: 분할할 텍스트
        min_length: 최소 문장 길이 (이보다 짧은 문장은 제거)

    Returns:
        분할된 문장 리스트
    """
    if not text or not text.strip():
        return []

    # 전처리: linebreak → space, whitespace 중복 제거
    normalized = re.sub(r"\s+", " ", text).strip()

    # 전처리: 。 뒤에 공백 삽입 (공백 없이 바로 다음 문자가 오는 경우)
    normalized = re.sub(r"。(?=\S)", "。 ", normalized)

    # findall로 구두점이 포함된 문장 추출
    matches = _SENTENCE_PATTERN.findall(normalized)

    if matches:
        # 매치된 부분을 합쳐서 남은 꼬리(구두점 없는 텍스트) 확인
        matched_text = ""
        for m in matches:
            idx = normalized.find(m, len(matched_text))
            matched_text = normalized[:idx + len(m)]

        remainder = normalized[len(matched_text):].strip()
        sentences = [m.strip() for m in matches]
        if remainder:
            sentences.append(remainder)
    else:
        # 구두점이 없으면 전체를 하나의 문장으로
        sentences = [normalized]

    # 후처리: 빈 문장 제거, 최소 길이 필터
    return [s for s in sentences if s and len(s) >= min_length]
