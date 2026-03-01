"""토큰 카운터

tiktoken o200k_base 인코딩 기반으로 텍스트와 메시지의 토큰 수를 계산합니다.
"""

import tiktoken


class TokenCounter:
    """o200k_base 인코딩 기반 토큰 카운터"""

    TOKENS_PER_MESSAGE = 4  # role + framing overhead

    def __init__(self):
        self.encoder = tiktoken.get_encoding("o200k_base")

    def count_string(self, text: str) -> int:
        """텍스트의 토큰 수를 반환합니다."""
        if not text:
            return 0
        return len(self.encoder.encode(text))

    def count_messages(self, messages: list[dict]) -> int:
        """메시지 목록의 총 토큰 수를 반환합니다.

        각 메시지에 TOKENS_PER_MESSAGE 만큼의 오버헤드를 추가합니다.
        """
        total = 0
        for msg in messages:
            total += self.TOKENS_PER_MESSAGE
            total += self.count_string(msg.get("role", ""))
            total += self.count_string(msg.get("content", ""))
        return total
