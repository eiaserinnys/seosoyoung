"""rescue-bot 서비스 cogito Reflector 싱글톤

모듈 레벨에서 생성되어, @reflect.capability 데코레이터가
inspect 기반으로 소스 위치를 자동 추적할 수 있게 한다.
"""

from cogito import Reflector
from pathlib import Path

reflect = Reflector(
    name="rescue-bot",
    description=(
        "서소영 긴급 복구용 봇. "
        "soulstream 없이 Claude Code SDK를 직접 실행하여 "
        "장애 시에도 슬랙 명령을 처리한다."
    ),
    source_root=str(Path(__file__).resolve().parent),
    # supervisor가 할당하는 고정 포트. cogito identity에서 서비스 디스커버리 메타데이터로 사용.
    port=3107,
)
