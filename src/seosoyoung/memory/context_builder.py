"""컨텍스트 빌더

장기 기억과 세션 관찰 로그를 시스템 프롬프트로 변환하여 Claude 세션에 주입합니다.
OM의 processInputStep에 해당하는 부분입니다.

주입 계층:
- 장기 기억 (persistent/recent.md): 매 세션 시작 시 항상 주입
- 세션 관찰 (observations/{thread_ts}.md): inject 플래그 있을 때만 주입
- 채널 관찰 (channel/{channel_id}/): 관찰 대상 채널에서 멘션될 때 주입
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from seosoyoung.memory.store import MemoryStore
from seosoyoung.memory.token_counter import TokenCounter

if TYPE_CHECKING:
    from seosoyoung.memory.channel_store import ChannelStore

logger = logging.getLogger(__name__)


@dataclass
class InjectionResult:
    """주입 결과 — 디버그 로그용 정보를 포함"""

    prompt: str | None
    persistent_tokens: int = 0
    session_tokens: int = 0
    persistent_content: str = ""
    session_content: str = ""
    channel_digest_tokens: int = 0
    channel_buffer_tokens: int = 0
    new_observation_tokens: int = 0
    new_observation_content: str = ""


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
    """장기 기억 + 세션 관찰 로그 + 채널 관찰을 시스템 프롬프트로 변환"""

    def __init__(
        self,
        store: MemoryStore,
        channel_store: Optional["ChannelStore"] = None,
    ):
        self.store = store
        self.channel_store = channel_store
        self._counter = TokenCounter()

    def _build_channel_observation(
        self,
        channel_id: str,
        thread_ts: Optional[str] = None,
    ) -> tuple[str, int, int]:
        """채널 관찰 컨텍스트를 XML 문자열로 빌드합니다.

        Returns:
            (xml_string, digest_tokens, buffer_tokens)
        """
        if not self.channel_store or not channel_id:
            return "", 0, 0

        digest_tokens = 0
        buffer_tokens = 0
        sections = []

        # digest
        digest_data = self.channel_store.get_digest(channel_id)
        if digest_data and digest_data["content"].strip():
            digest_content = digest_data["content"]
            digest_tokens = self._counter.count_string(digest_content)
            sections.append(f"<digest>\n{digest_content}\n</digest>")

        # channel buffer (미소화 채널 루트 메시지)
        channel_messages = self.channel_store.load_channel_buffer(channel_id)
        if channel_messages:
            lines = [json.dumps(m, ensure_ascii=False) for m in channel_messages]
            buf_text = "\n".join(lines)
            buffer_tokens += self._counter.count_string(buf_text)
            sections.append(f"<recent-channel>\n{buf_text}\n</recent-channel>")

        # thread buffer (현재 스레드만)
        if thread_ts:
            thread_messages = self.channel_store.load_thread_buffer(channel_id, thread_ts)
            if thread_messages:
                lines = [json.dumps(m, ensure_ascii=False) for m in thread_messages]
                buf_text = "\n".join(lines)
                buffer_tokens += self._counter.count_string(buf_text)
                sections.append(
                    f'<recent-thread thread="{thread_ts}">\n{buf_text}\n</recent-thread>'
                )

        if not sections:
            return "", 0, 0

        inner = "\n\n".join(sections)
        xml = f'<channel-observation channel="{channel_id}">\n{inner}\n</channel-observation>'
        return xml, digest_tokens, buffer_tokens

    def build_memory_prompt(
        self,
        thread_ts: str,
        max_tokens: int = 30000,
        include_persistent: bool = False,
        include_session: bool = True,
        include_channel_observation: bool = False,
        channel_id: Optional[str] = None,
        include_new_observations: bool = False,
    ) -> InjectionResult:
        """장기 기억, 세션 관찰, 채널 관찰, 새 관찰을 합쳐서 시스템 프롬프트로 변환합니다.

        주입 순서: 장기 기억 → 새 관찰 → 세션 관찰 → 채널 관찰

        Args:
            thread_ts: 세션(스레드) 타임스탬프
            max_tokens: 세션 관찰 최대 토큰 수
            include_persistent: 장기 기억을 포함할지 여부
            include_session: 세션 관찰을 포함할지 여부
            include_channel_observation: 채널 관찰 컨텍스트를 포함할지 여부
            channel_id: 채널 ID (채널 관찰 시 필요)
            include_new_observations: 이전 세션의 미전달 관찰을 포함할지 여부

        Returns:
            InjectionResult
        """
        parts = []
        persistent_tokens = 0
        session_tokens = 0
        persistent_content = ""
        session_content = ""
        channel_digest_tokens = 0
        channel_buffer_tokens = 0
        new_observation_tokens = 0
        new_observation_content = ""

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

        # 2. 새 관찰 (이전 세션에서 새롭게 관찰된 미전달 사항)
        if include_new_observations:
            record = self.store.get_latest_undelivered_observation(
                exclude_thread_ts=thread_ts,
            )
            if record and record.observations.strip():
                observations = add_relative_time(record.observations)
                new_observation_tokens = self._counter.count_string(observations)
                new_observation_content = observations
                parts.append(
                    "<new-observations>\n"
                    "지난 사용자와 에이전트 간의 대화에서 새롭게 관찰된 사실입니다.\n\n"
                    f"{observations}\n"
                    "</new-observations>"
                )

        # 3. 세션 관찰 (observations/{thread_ts}.md)
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

        # 4. 채널 관찰 (channel/{channel_id}/)
        if include_channel_observation and channel_id:
            ch_xml, ch_digest_tok, ch_buf_tok = self._build_channel_observation(
                channel_id, thread_ts=thread_ts,
            )
            if ch_xml:
                channel_digest_tokens = ch_digest_tok
                channel_buffer_tokens = ch_buf_tok
                parts.append(ch_xml)

        prompt = "\n\n".join(parts) if parts else None

        return InjectionResult(
            prompt=prompt,
            persistent_tokens=persistent_tokens,
            session_tokens=session_tokens,
            persistent_content=persistent_content,
            session_content=session_content,
            channel_digest_tokens=channel_digest_tokens,
            channel_buffer_tokens=channel_buffer_tokens,
            new_observation_tokens=new_observation_tokens,
            new_observation_content=new_observation_content,
        )
