"""Claude Code CLI 래퍼"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from seosoyoung.config import Config

logger = logging.getLogger(__name__)

# 환경 변수에서 제외할 민감 정보
SENSITIVE_ENV_KEYS = {
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "ANTHROPIC_API_KEY",
}


@dataclass
class ClaudeResult:
    """Claude Code 실행 결과"""
    success: bool
    output: str
    session_id: Optional[str] = None
    error: Optional[str] = None
    files: list[str] = field(default_factory=list)  # FILE 마커로 추출된 파일 경로들


class ClaudeRunner:
    """Claude Code CLI 실행기"""

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        timeout: int = 300,  # 5분 기본 타임아웃
    ):
        self.working_dir = working_dir or Path(Config.EB_RENPY_PATH)
        self.timeout = timeout
        self._lock = asyncio.Lock()  # 동시 실행 제어

    def _get_filtered_env(self) -> dict:
        """민감 정보를 제외한 환경 변수 반환"""
        return {
            k: v for k, v in os.environ.items()
            if k not in SENSITIVE_ENV_KEYS
        }

    def _build_command(
        self,
        prompt: str,
        session_id: Optional[str] = None,
    ) -> list[str]:
        """Claude Code CLI 명령어 구성"""
        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "stream-json",
            "--dangerously-skip-permissions",
            "--verbose",
        ]

        if session_id:
            cmd.extend(["--resume", session_id])

        return cmd

    async def run(
        self,
        prompt: str,
        session_id: Optional[str] = None,
    ) -> ClaudeResult:
        """Claude Code 실행"""
        async with self._lock:
            return await self._execute(prompt, session_id)

    async def _execute(
        self,
        prompt: str,
        session_id: Optional[str] = None,
    ) -> ClaudeResult:
        """실제 실행 로직"""
        cmd = self._build_command(prompt, session_id)
        logger.info(f"Claude Code 실행: {' '.join(cmd[:5])}...")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env=self._get_filtered_env(),
                limit=1024 * 1024,  # 1MB 버퍼
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.terminate()
                await process.wait()
                logger.error(f"Claude Code 타임아웃 ({self.timeout}초)")
                return ClaudeResult(
                    success=False,
                    output="",
                    error=f"타임아웃: {self.timeout}초 초과"
                )

            return self._parse_output(stdout.decode("utf-8"), stderr.decode("utf-8"))

        except FileNotFoundError:
            logger.error("Claude Code CLI를 찾을 수 없습니다. claude 명령어가 PATH에 있는지 확인하세요.")
            return ClaudeResult(
                success=False,
                output="",
                error="Claude Code CLI를 찾을 수 없습니다."
            )
        except Exception as e:
            logger.exception(f"Claude Code 실행 오류: {e}")
            return ClaudeResult(
                success=False,
                output="",
                error=str(e)
            )

    def _parse_output(self, stdout: str, stderr: str) -> ClaudeResult:
        """stream-json 출력 파싱"""
        session_id = None
        output_parts = []
        files = []

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                msg_type = data.get("type")

                # 세션 ID 추출 (init 메시지에서)
                if msg_type == "system" and data.get("subtype") == "init":
                    session_id = data.get("session_id")
                    logger.info(f"세션 ID: {session_id}")

                # assistant 응답 수집
                elif msg_type == "assistant":
                    content = data.get("message", {}).get("content", [])
                    for block in content:
                        if block.get("type") == "text":
                            output_parts.append(block.get("text", ""))

                # result 메시지 (최종 결과)
                elif msg_type == "result":
                    result_text = data.get("result", "")
                    if result_text:
                        output_parts.append(result_text)

            except json.JSONDecodeError:
                # JSON이 아닌 라인은 그대로 추가
                output_parts.append(line)

        output = "\n".join(output_parts)

        # FILE 마커 추출
        # <!-- FILE: /path/to/file --> 패턴
        import re
        file_pattern = r"<!-- FILE: (.+?) -->"
        files = re.findall(file_pattern, output)

        if stderr:
            logger.warning(f"Claude Code stderr: {stderr[:500]}")

        return ClaudeResult(
            success=True,
            output=output,
            session_id=session_id,
            files=files,
        )


# 테스트용
async def main():
    runner = ClaudeRunner()
    result = await runner.run("eb_renpy 프로젝트 구조를 간단히 설명해줘. 3줄 이내로.")
    print(f"Success: {result.success}")
    print(f"Session ID: {result.session_id}")
    print(f"Output:\n{result.output}")
    if result.error:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
