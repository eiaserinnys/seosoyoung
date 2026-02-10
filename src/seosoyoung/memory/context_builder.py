"""컨텍스트 빌더

장기 기억과 세션 관찰 로그를 시스템 프롬프트로 변환하여 Claude 세션에 주입합니다.
OM의 processInputStep에 해당하는 부분입니다.

주입 계층:
- 장기 기억 (persistent/recent.md): 매 세션 시작 시 항상 주입
- 세션 관찰 (observations/{thread_ts}.md): inject 플래그 있을 때만 주입
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from seosoyoung.memory.store import MemoryStore
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


@dataclass
class InjectionResult:
    """주입 결과 — 디버그 로그용 정보를 포함"""

    prompt: str | None
    persistent_tokens: int = 0
    session_tokens: int = 0
    persistent_content: str = ""
    session_content: str = ""


def add_relative_time(observations: str, now: datetime | None = None) -> str:
    """관찰 로그의 날짜 헤더에 상대 시간 주석을 추가합니다.

    ## [2026-02-10] → ## [2026-02-10] (3일 전)
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # timezone-aware로 통일
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    def replace_date_header(match: re.Match) -> str:
        date_str = match.group(1)
        try:
            obs_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            delta = now - obs_date
            days = delta.days

            if days == 0:
                relative = "오늘"
            elif days == 1:
                relative = "어제"
            elif days < 7:
                relative = f"{days}일 전"
            elif days < 30:
                weeks = days // 7
                relative = f"{weeks}주 전"
            elif days < 365:
                months = days // 30
                relative = f"{months}개월 전"
            else:
                relative = f"{days // 365}년 전"

            return f"## [{date_str}] ({relative})"
        except ValueError:
            return match.group(0)

    return re.sub(r"## \[(\d{4}-\d{2}-\d{2})\]", replace_date_header, observations)


def optimize_for_context(
    observations: str, max_tokens: int = 30000
) -> str:
    """관찰 로그를 컨텍스트 주입에 최적화합니다.

    - 토큰 수 초과 시 truncate (오래된 내용부터 제거)
    """
    counter = TokenCounter()
    token_count = counter.count_string(observations)

    if token_count <= max_tokens:
        return observations

    # 섹션 단위로 분리 (## [날짜] 기준)
    sections = re.split(r"(?=^## \[)", observations, flags=re.MULTILINE)
    sections = [s for s in sections if s.strip()]

    # 최신 섹션부터 역순으로 추가
    result_sections = []
    current_tokens = 0
    for section in reversed(sections):
        section_tokens = counter.count_string(section)
        if current_tokens + section_tokens > max_tokens:
            break
        result_sections.insert(0, section)
        current_tokens += section_tokens

    if not result_sections:
        # 단일 섹션도 너무 큰 경우: 이진 탐색으로 적정 길이를 찾아 자름
        low, high = 0, len(observations)
        while low < high:
            mid = (low + high + 1) // 2
            # 뒤에서 mid 글자를 잘라서 토큰 수 확인
            if counter.count_string(observations[-mid:]) <= max_tokens:
                low = mid
            else:
                high = mid - 1
        return observations[-low:] if low > 0 else observations[:1000]

    return "".join(result_sections)


class ContextBuilder:
    """장기 기억 + 세션 관찰 로그를 시스템 프롬프트로 변환"""

    def __init__(self, store: MemoryStore):
        self.store = store
        self._counter = TokenCounter()

    def build_memory_prompt(
        self,
        thread_ts: str,
        max_tokens: int = 30000,
        include_persistent: bool = False,
        include_session: bool = True,
    ) -> InjectionResult:
        """장기 기억과 세션 관찰 로그를 합쳐서 시스템 프롬프트로 변환합니다.

        Args:
            thread_ts: 세션(스레드) 타임스탬프
            max_tokens: 세션 관찰 최대 토큰 수
            include_persistent: 장기 기억을 포함할지 여부
            include_session: 세션 관찰을 포함할지 여부

        Returns:
            InjectionResult (prompt, persistent_tokens, session_tokens)
        """
        parts = []
        persistent_tokens = 0
        session_tokens = 0
        persistent_content = ""
        session_content = ""

        # 1. 장기 기억 (persistent/recent.md)
        if include_persistent:
            persistent_data = self.store.get_persistent()
            if persistent_data and persistent_data["content"].strip():
                content = persistent_data["content"]
                persistent_tokens = self._counter.count_string(content)
                persistent_content = content
                parts.append(
                    "<long-term-memory>\n"
                    "다음은 과거 대화들에서 축적한 장기 기억입니다.\n"
                    "응답할 때 이 기억을 자연스럽게 활용하세요.\n\n"
                    f"{content}\n"
                    "</long-term-memory>"
                )

        # 2. 세션 관찰 (observations/{thread_ts}.md)
        if include_session:
            record = self.store.get_record(thread_ts)
            if record and record.observations.strip():
                observations = add_relative_time(record.observations)
                optimized = optimize_for_context(observations, max_tokens)
                session_tokens = self._counter.count_string(optimized)
                session_content = optimized
                parts.append(
                    "<observational-memory>\n"
                    "다음은 이 세션의 최근 대화에서 관찰한 내용입니다.\n\n"
                    f"{optimized}\n"
                    "</observational-memory>"
                )

        prompt = "\n\n".join(parts) if parts else None

        return InjectionResult(
            prompt=prompt,
            persistent_tokens=persistent_tokens,
            session_tokens=session_tokens,
            persistent_content=persistent_content,
            session_content=session_content,
        )
