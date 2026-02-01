"""Claude Code CLI 래퍼"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Awaitable

from seosoyoung.claude.security import SecurityError

logger = logging.getLogger(__name__)

# 환경 변수에서 제외할 민감 정보
SENSITIVE_ENV_KEYS = {
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    # ANTHROPIC_API_KEY는 제거 (Claude Code CLI 로그인 세션 사용)
}

# Claude Code 허용 도구
ALLOWED_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "TodoWrite",
]

# Claude Code 금지 도구
DISALLOWED_TOOLS = [
    "WebFetch",
    "WebSearch",
    "Task",
]


@dataclass
class ClaudeResult:
    """Claude Code 실행 결과"""
    success: bool
    output: str
    session_id: Optional[str] = None
    error: Optional[str] = None
    files: list[str] = field(default_factory=list)  # FILE 마커로 추출된 파일 경로들
    attachments: list[str] = field(default_factory=list)  # ATTACH 마커로 추출된 첨부 파일 경로들
    update_requested: bool = False  # <!-- UPDATE --> 마커 감지 (exit 42)
    restart_requested: bool = False  # <!-- RESTART --> 마커 감지 (exit 43)
    list_run: Optional[str] = None  # <!-- LIST_RUN: 리스트명 --> 마커로 추출된 리스트 이름


class ClaudeRunner:
    """Claude Code CLI 실행기"""

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        timeout: int = 300,  # 5분 기본 타임아웃
        allowed_tools: Optional[list[str]] = None,
        disallowed_tools: Optional[list[str]] = None,
    ):
        self.working_dir = working_dir or Path.cwd()
        self.timeout = timeout
        self.allowed_tools = allowed_tools or ALLOWED_TOOLS
        self.disallowed_tools = disallowed_tools or DISALLOWED_TOOLS
        self._lock = asyncio.Lock()  # 동시 실행 제어

    def _get_filtered_env(self) -> dict:
        """민감 정보를 제외한 환경 변수 반환"""
        return {
            k: v for k, v in os.environ.items()
            if k not in SENSITIVE_ENV_KEYS
        }

    def _extract_list_run_markup(self, output: str) -> Optional[str]:
        """LIST_RUN 마크업에서 리스트 이름 추출

        Args:
            output: Claude 응답 텍스트

        Returns:
            리스트 이름 또는 None
        """
        pattern = r"<!-- LIST_RUN: (.+?) -->"
        match = re.search(pattern, output)
        if match:
            return match.group(1).strip()
        return None

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

        # 허용 도구 설정
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])

        # 금지 도구 설정
        if self.disallowed_tools:
            cmd.extend(["--disallowedTools", ",".join(self.disallowed_tools)])

        if session_id:
            cmd.extend(["--resume", session_id])

        return cmd

    async def run(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ClaudeResult:
        """Claude Code 실행

        Args:
            prompt: 실행할 프롬프트
            session_id: 이어갈 세션 ID (선택)
            on_progress: 진행 상황 콜백 (선택). 텍스트 청크가 생성될 때마다 호출됨.
        """
        async with self._lock:
            if on_progress:
                return await self._execute_streaming(prompt, session_id, on_progress)
            else:
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

    async def _execute_streaming(
        self,
        prompt: str,
        session_id: Optional[str],
        on_progress: Callable[[str], Awaitable[None]],
    ) -> ClaudeResult:
        """스트리밍 모드 실행 (진행 상황 콜백 호출)"""
        cmd = self._build_command(prompt, session_id)
        logger.info(f"Claude Code 스트리밍 실행: {' '.join(cmd[:5])}...")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env=self._get_filtered_env(),
                limit=1024 * 1024,
            )

            result_session_id = None
            current_text = ""  # 현재 assistant 응답 (누적 X)
            result_text = ""   # 최종 result 응답
            files = []
            last_progress_time = asyncio.get_event_loop().time()
            progress_interval = 2.0  # 2초 간격으로 업데이트

            async def read_stream():
                nonlocal result_session_id, last_progress_time, current_text, result_text

                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(),
                            timeout=self.timeout
                        )
                    except asyncio.TimeoutError:
                        process.terminate()
                        await process.wait()
                        return False, "타임아웃"

                    if not line:
                        break

                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue

                    try:
                        data = json.loads(line_str)
                        msg_type = data.get("type")

                        # 세션 ID 추출
                        if msg_type == "system" and data.get("subtype") == "init":
                            result_session_id = data.get("session_id")
                            logger.info(f"세션 ID: {result_session_id}")

                        # assistant 응답: 현재 텍스트만 표시 (누적 X)
                        elif msg_type == "assistant":
                            content = data.get("message", {}).get("content", [])
                            for block in content:
                                if block.get("type") == "text":
                                    current_text = block.get("text", "")

                                    # 진행 상황 콜백 (2초 간격)
                                    current_time = asyncio.get_event_loop().time()
                                    if current_time - last_progress_time >= progress_interval:
                                        try:
                                            display_text = current_text
                                            # 너무 길면 마지막 부분만
                                            if len(display_text) > 1000:
                                                display_text = "...\n" + display_text[-1000:]
                                            await on_progress(display_text)
                                            last_progress_time = current_time
                                        except Exception as e:
                                            logger.warning(f"진행 상황 콜백 오류: {e}")

                        # result 메시지: 최종 응답으로 저장
                        elif msg_type == "result":
                            result_text = data.get("result", "")

                    except json.JSONDecodeError:
                        pass  # JSON이 아닌 라인은 무시

                return True, None

            success, error_msg = await read_stream()

            # stderr 읽기
            stderr_data = await process.stderr.read()
            stderr = stderr_data.decode("utf-8") if stderr_data else ""

            if not success:
                return ClaudeResult(
                    success=False,
                    output=current_text,
                    session_id=result_session_id,
                    error=error_msg
                )

            await process.wait()

            # 최종 출력: result만 사용
            output = result_text

            # FILE 마커 추출
            file_pattern = r"<!-- FILE: (.+?) -->"
            files = re.findall(file_pattern, output)

            # ATTACH 마커 추출
            attach_pattern = r"<!-- ATTACH: (.+?) -->"
            attachments = re.findall(attach_pattern, output)
            if attachments:
                logger.info(f"첨부 파일 요청: {attachments}")

            # 재기동 마커 감지
            update_requested = "<!-- UPDATE -->" in output
            restart_requested = "<!-- RESTART -->" in output
            if update_requested:
                logger.info("업데이트 요청 마커 감지: <!-- UPDATE -->")
            if restart_requested:
                logger.info("재시작 요청 마커 감지: <!-- RESTART -->")

            # LIST_RUN 마커 추출
            list_run = self._extract_list_run_markup(output)
            if list_run:
                logger.info(f"리스트 정주행 요청 마커 감지: {list_run}")

            if stderr:
                logger.warning(f"Claude Code stderr: {stderr[:500]}")

            return ClaudeResult(
                success=True,
                output=output,
                session_id=result_session_id,
                files=files,
                attachments=attachments,
                update_requested=update_requested,
                restart_requested=restart_requested,
                list_run=list_run,
            )

        except FileNotFoundError:
            logger.error("Claude Code CLI를 찾을 수 없습니다.")
            return ClaudeResult(
                success=False,
                output="",
                error="Claude Code CLI를 찾을 수 없습니다."
            )
        except Exception as e:
            logger.exception(f"Claude Code 스트리밍 실행 오류: {e}")
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
        file_pattern = r"<!-- FILE: (.+?) -->"
        files = re.findall(file_pattern, output)

        # ATTACH 마커 추출
        # <!-- ATTACH: /path/to/file --> 패턴
        attach_pattern = r"<!-- ATTACH: (.+?) -->"
        attachments = re.findall(attach_pattern, output)
        if attachments:
            logger.info(f"첨부 파일 요청: {attachments}")

        # 재기동 마커 감지
        update_requested = "<!-- UPDATE -->" in output
        restart_requested = "<!-- RESTART -->" in output
        if update_requested:
            logger.info("업데이트 요청 마커 감지: <!-- UPDATE -->")
        if restart_requested:
            logger.info("재시작 요청 마커 감지: <!-- RESTART -->")

        # LIST_RUN 마커 추출
        list_run = self._extract_list_run_markup(output)
        if list_run:
            logger.info(f"리스트 정주행 요청 마커 감지: {list_run}")

        if stderr:
            logger.warning(f"Claude Code stderr: {stderr[:500]}")

        return ClaudeResult(
            success=True,
            output=output,
            session_id=session_id,
            files=files,
            attachments=attachments,
            update_requested=update_requested,
            restart_requested=restart_requested,
            list_run=list_run,
        )


    async def compact_session(self, session_id: str) -> ClaudeResult:
        """세션 컴팩트 처리

        세션의 대화 내역을 압축하여 토큰 사용량을 줄입니다.
        Claude Code CLI의 `--resume {session_id}` 옵션과 `/compact` 명령을 사용합니다.

        Args:
            session_id: 컴팩트할 세션 ID

        Returns:
            ClaudeResult (compact 결과)
        """
        if not session_id:
            return ClaudeResult(
                success=False,
                output="",
                error="세션 ID가 없습니다."
            )

        # /compact 명령어 전송 (Claude Code CLI 내장 명령)
        # 세션을 이어서 /compact를 실행
        prompt = "/compact"

        logger.info(f"세션 컴팩트 시작: {session_id}")
        result = await self._execute(prompt, session_id)

        if result.success:
            logger.info(f"세션 컴팩트 완료: {session_id}")
        else:
            logger.error(f"세션 컴팩트 실패: {session_id}, {result.error}")

        return result


# 테스트용
async def main():
    runner = ClaudeRunner()
    result = await runner.run("eb_lore 프로젝트 구조를 간단히 설명해줘. 3줄 이내로.")
    print(f"Success: {result.success}")
    print(f"Session ID: {result.session_id}")
    print(f"Output:\n{result.output}")
    if result.error:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
