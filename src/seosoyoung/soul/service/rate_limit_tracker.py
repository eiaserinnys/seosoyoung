"""
RateLimitTracker - 프로필별 rate limit 상태 추적 모듈

프로필별 five_hour/seven_day rate limit utilization을 추적하고,
95% 임계값 도달 시 알림을 트리거합니다.
상태는 JSON 파일로 영속화되어 재시작 시 복원됩니다.

저장 경로: {profiles_dir}/_rate_limits.json
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

# 95% 알림 임계값
_ALERT_THRESHOLD = 0.95

# rate limit 타입
_RATE_LIMIT_TYPES = ("five_hour", "seven_day")

# 기본 (알려지지 않은) 상태
_UNKNOWN_STATE = {"utilization": "unknown", "resets_at": None}


def _now_utc() -> datetime:
    """현재 UTC 시간."""
    return datetime.now(timezone.utc)


def _parse_iso(iso_str: Optional[str]) -> Optional[datetime]:
    """ISO 8601 문자열을 datetime으로 파싱.

    None이거나 파싱 실패 시 None 반환.
    """
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None


def _is_expired(resets_at: Optional[str]) -> bool:
    """resets_at 시간이 경과했는지 확인.

    None이면 만료되지 않은 것으로 처리.
    """
    dt = _parse_iso(resets_at)
    if dt is None:
        return False
    return _now_utc() >= dt


class RateLimitTracker:
    """프로필별 rate limit 상태 추적기.

    Args:
        profiles_dir: 프로필 저장 디렉토리 (영속화 파일 위치)
    """

    def __init__(self, profiles_dir: Path | str) -> None:
        self._dir = Path(profiles_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._persist_path = self._dir / "_rate_limits.json"
        self._lock = threading.Lock()

        # 내부 상태: {profile: {type: {utilization, resets_at, alerted_95}}}
        self._states: dict[str, dict[str, dict[str, Any]]] = {}

        # 초기 로드
        self._load()

    def _load(self) -> None:
        """영속화 파일에서 상태 복원."""
        if not self._persist_path.is_file():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._states = data
                logger.info(f"Rate limit 상태 로드: {len(self._states)}개 프로필")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Rate limit 상태 로드 실패 (빈 상태로 시작): {e}")
            self._states = {}

    def save(self) -> None:
        """현재 상태를 JSON 파일로 영속화."""
        with self._lock:
            data = self._states.copy()

        tmp_path = self._persist_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._persist_path)
            logger.debug("Rate limit 상태 저장 완료")
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def record(
        self,
        profile: str,
        rate_limit_type: str,
        utilization: float,
        resets_at: Optional[str],
    ) -> bool:
        """rate limit 이벤트 기록.

        Args:
            profile: 프로필 이름
            rate_limit_type: "five_hour" 또는 "seven_day"
            utilization: 사용률 (0.0 ~ 1.0)
            resets_at: 리셋 시간 (ISO 8601 문자열, None 가능)

        Returns:
            True: 95% 알림을 트리거해야 하는 경우
            False: 알림 불필요
        """
        with self._lock:
            if profile not in self._states:
                self._states[profile] = {}

            profile_state = self._states[profile]

            if rate_limit_type not in profile_state:
                profile_state[rate_limit_type] = {
                    "utilization": 0.0,
                    "resets_at": None,
                    "alerted_95": False,
                }

            entry = profile_state[rate_limit_type]

            # 이전 리셋 시간이 만료되었으면 알림 플래그 초기화
            old_resets_at = entry.get("resets_at")
            if old_resets_at and _is_expired(old_resets_at):
                entry["alerted_95"] = False

            # 값 갱신
            entry["utilization"] = utilization
            entry["resets_at"] = resets_at

            # 95% 알림 판정
            should_alert = False
            if utilization >= _ALERT_THRESHOLD and not entry.get("alerted_95"):
                # 만료되지 않은 경우에만 알림
                if not _is_expired(resets_at):
                    entry["alerted_95"] = True
                    should_alert = True
                    logger.info(
                        f"Rate limit 95% 알림 트리거: "
                        f"profile={profile}, type={rate_limit_type}, "
                        f"utilization={utilization}"
                    )

        # 기록할 때마다 자동 저장
        self.save()

        return should_alert

    def get_profile_state(
        self, profile: str
    ) -> dict[str, dict[str, Any]]:
        """특정 프로필의 rate limit 상태 조회.

        만료된 항목은 utilization 0으로 자동 처리.
        기록되지 않은 프로필/타입은 "unknown" 상태 반환.

        Returns:
            {
                "five_hour": {"utilization": 0.51, "resets_at": "..."},
                "seven_day": {"utilization": "unknown", "resets_at": None},
            }
        """
        with self._lock:
            profile_state = self._states.get(profile, {})

        result: dict[str, dict[str, Any]] = {}
        for rate_type in _RATE_LIMIT_TYPES:
            entry = profile_state.get(rate_type)
            if entry is None:
                result[rate_type] = dict(_UNKNOWN_STATE)
            else:
                resets_at = entry.get("resets_at")
                if _is_expired(resets_at):
                    result[rate_type] = {
                        "utilization": 0.0,
                        "resets_at": resets_at,
                    }
                else:
                    result[rate_type] = {
                        "utilization": entry["utilization"],
                        "resets_at": resets_at,
                    }

        return result

    def get_all_states(self) -> dict[str, dict[str, dict[str, Any]]]:
        """모든 프로필의 rate limit 상태 조회.

        Returns:
            {profile_name: get_profile_state(profile_name) 결과}
        """
        with self._lock:
            profiles = list(self._states.keys())

        if not profiles:
            return {}

        return {p: self.get_profile_state(p) for p in profiles}

    def build_credential_alert(
        self, active_profile: str
    ) -> dict[str, Any]:
        """credential_alert SSE 이벤트 데이터 생성.

        Args:
            active_profile: 현재 활성 프로필 이름

        Returns:
            credential_alert 이벤트 페이로드
        """
        all_states = self.get_all_states()

        profiles_data = []
        for name, state in all_states.items():
            profiles_data.append({
                "name": name,
                "five_hour": state["five_hour"],
                "seven_day": state["seven_day"],
            })

        return {
            "type": "credential_alert",
            "active_profile": active_profile,
            "profiles": profiles_data,
        }
