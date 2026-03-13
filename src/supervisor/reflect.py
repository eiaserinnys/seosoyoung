"""supervisor 서비스 cogito Reflector 싱글톤

모듈 레벨에서 생성되어, @reflect.capability 데코레이터가
inspect 기반으로 소스 위치를 자동 추적할 수 있게 한다.
"""

from cogito import Reflector
from pathlib import Path

reflect = Reflector(
    name="supervisor",
    description="seosoyoung 프로세스 관리자",
    source_root=str(Path(__file__).resolve().parent),
    port=8042,
)
