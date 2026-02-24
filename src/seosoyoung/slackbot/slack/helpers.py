"""Slack 메시지 유틸리티

파일 업로드, 긴 메시지 분할 전송 등의 헬퍼 함수들입니다.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def upload_file_to_slack(client, channel: str, thread_ts: str, file_path: str) -> tuple[bool, str]:
    """파일을 슬랙에 첨부

    Args:
        client: Slack client
        channel: 채널 ID
        thread_ts: 스레드 타임스탬프
        file_path: 첨부할 파일 경로

    Returns:
        (success, message): 성공 여부와 메시지
    """
    try:
        file_path_obj = Path(file_path).resolve()

        if not file_path_obj.exists():
            return False, f"파일이 존재하지 않음: {file_path}"

        if not file_path_obj.is_file():
            return False, f"파일이 아님: {file_path}"

        result = client.files_upload_v2(
            channel=channel,
            thread_ts=thread_ts,
            file=str(file_path_obj),
            filename=file_path_obj.name,
            initial_comment=f"📎 `{file_path_obj.name}`"
        )
        logger.info(f"파일 첨부 성공: {file_path}")
        return True, "첨부 완료"
    except Exception as e:
        logger.error(f"파일 첨부 실패: {file_path} - {e}")
        return False, f"첨부 실패: {str(e)}"


def send_long_message(say, text: str, thread_ts: str | None, max_length: int = 3900):
    """긴 메시지를 분할해서 전송 (thread_ts가 None이면 채널에 응답)"""
    if len(text) <= max_length:
        say(text=f"{text}", thread_ts=thread_ts)
        return

    # 줄 단위로 분할
    lines = text.split("\n")
    chunks = []
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk = current_chunk + "\n" + line if current_chunk else line

    if current_chunk:
        chunks.append(current_chunk)

    # 분할된 메시지 전송
    for i, chunk in enumerate(chunks):
        prefix = f"({i+1}/{len(chunks)})\n" if len(chunks) > 1 else ""
        say(text=prefix + chunk, thread_ts=thread_ts)
