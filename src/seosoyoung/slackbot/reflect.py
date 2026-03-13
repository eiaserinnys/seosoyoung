"""bot 서비스 cogito Reflector 싱글톤

모듈 레벨에서 생성되어, @reflect.capability 데코레이터가
inspect 기반으로 소스 위치를 자동 추적할 수 있게 한다.
"""

from cogito import Reflector
from pathlib import Path

reflect = Reflector(
    name="bot",
    description=(
        "서소영 Slack SocketMode 봇. "
        "이벤트 처리, 멘션 응답, 플러그인 시스템을 통해 soulstream과 연동한다."
    ),
    source_root=str(Path(__file__).resolve().parent),
    # supervisor가 할당하는 고정 포트. cogito identity에서 서비스 디스커버리 메타데이터로 사용.
    port=3106,
)
