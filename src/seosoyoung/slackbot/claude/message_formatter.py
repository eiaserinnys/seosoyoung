"""슬랙 메시지 포맷팅 유틸리티

Claude 응답을 슬랙 메시지 형식으로 변환하는 함수들을 제공합니다.
- 백틱 이스케이프
- 트렐로 헤더
- 진행 상황(on_progress) 포맷팅

순수 텍스트 변환 함수들은 slackbot.formatting으로 추출되었습니다.
이 모듈은 하위호환을 위해 re-export합니다.
"""

import logging

from seosoyoung.slackbot.formatting import (  # noqa: F401 — re-export
    DM_MSG_MAX_LEN,
    PROGRESS_MAX_LEN,
    SLACK_MSG_MAX_LEN,
    build_trello_header,
    escape_backticks,
    format_as_blockquote,
    format_dm_progress,
    format_trello_progress,
    truncate_progress_text,
)

logger = logging.getLogger(__name__)
