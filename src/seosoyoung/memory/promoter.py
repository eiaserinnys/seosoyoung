"""Promoter / Compactor 모듈

장기 기억 후보를 검토하여 승격(Promoter)하고,
장기 기억이 임계치를 넘으면 압축(Compactor)합니다.
"""

import logging
import re
from dataclasses import dataclass

import openai

from seosoyoung.memory.prompts import build_compactor_prompt, build_promoter_prompt
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


@dataclass
class PromoterResult:
    """Promoter 출력 결과"""

    promoted: str = ""
    rejected: str = ""
    promoted_count: int = 0
    rejected_count: int = 0
    priority_counts: dict = None

    def __post_init__(self):
        if self.priority_counts is None:
            self.priority_counts = {}


@dataclass
class CompactorResult:
    """Compactor 출력 결과"""

    compacted: str = ""
    token_count: int = 0


def _extract_tag(text: str, tag_name: str) -> str:
    """XML 태그 내용을 추출합니다. 없으면 빈 문자열."""
    pattern = rf"<{tag_name}>(.*?)</{tag_name}>"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _count_entries(text: str) -> int:
    """이모지 프리픽스(🔴🟡🟢) 또는 '-' 로 시작하는 비어있지 않은 줄 수를 카운트."""
    if not text or not text.strip():
        return 0
    count = 0
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line[0] in ("🔴", "🟡", "🟢", "-", "•"):
            count += 1
        elif len(line) > 1:
            count += 1
    return count


def _count_priority(text: str) -> dict:
    """승격 텍스트에서 우선순위별 카운트를 추출."""
    counts = {}
    if not text:
        return counts
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        for emoji in ("🔴", "🟡", "🟢"):
            if line.startswith(emoji):
                counts[emoji] = counts.get(emoji, 0) + 1
                break
    return counts


def parse_promoter_output(text: str) -> PromoterResult:
    """Promoter 응답에서 <promoted>와 <rejected> 태그를 파싱합니다."""
    promoted = _extract_tag(text, "promoted")
    rejected = _extract_tag(text, "rejected")

    return PromoterResult(
        promoted=promoted,
        rejected=rejected,
        promoted_count=_count_entries(promoted),
        rejected_count=_count_entries(rejected),
        priority_counts=_count_priority(promoted),
    )


def parse_compactor_output(text: str) -> str:
    """Compactor 응답에서 <compacted> 태그를 파싱합니다."""
    compacted = _extract_tag(text, "compacted")
    return compacted if compacted else text.strip()


class Promoter:
    """장기 기억 후보를 검토하여 승격"""

    def __init__(self, api_key: str, model: str = "gpt-5.2"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    async def promote(
        self,
        candidates: list[dict],
        existing_persistent: str,
    ) -> PromoterResult:
        """후보 항목들을 검토하여 장기 기억 승격 여부를 판단합니다.

        Args:
            candidates: 후보 항목 리스트 [{"ts": ..., "priority": ..., "content": ...}]
            existing_persistent: 기존 장기 기억 텍스트

        Returns:
            PromoterResult
        """
        candidate_text = self._format_candidates(candidates)
        prompt = build_promoter_prompt(existing_persistent, candidate_text)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=8_000,
        )

        result_text = response.choices[0].message.content or ""
        return parse_promoter_output(result_text)

    @staticmethod
    def _format_candidates(candidates: list[dict]) -> str:
        """후보 항목을 프롬프트용 텍스트로 포매팅."""
        lines = []
        for entry in candidates:
            priority = entry.get("priority", "🟢")
            content = entry.get("content", "")
            ts = entry.get("ts", "")
            lines.append(f"{priority} [{ts}] {content}")
        return "\n".join(lines)

    @staticmethod
    def merge_promoted(existing: str, promoted: str) -> str:
        """승격된 항목을 기존 장기 기억에 머지합니다."""
        if not existing or not existing.strip():
            return promoted
        if not promoted or not promoted.strip():
            return existing
        return f"{existing}\n\n{promoted}"


class Compactor:
    """장기 기억을 압축"""

    def __init__(self, api_key: str, model: str = "gpt-5.2"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
        self.token_counter = TokenCounter()

    async def compact(
        self,
        persistent: str,
        target_tokens: int,
    ) -> CompactorResult:
        """장기 기억을 압축합니다.

        Args:
            persistent: 현재 장기 기억 텍스트
            target_tokens: 목표 토큰 수

        Returns:
            CompactorResult
        """
        prompt = build_compactor_prompt(persistent, target_tokens)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=16_000,
        )

        result_text = response.choices[0].message.content or ""
        compacted = parse_compactor_output(result_text)
        token_count = self.token_counter.count_string(compacted)

        return CompactorResult(compacted=compacted, token_count=token_count)
