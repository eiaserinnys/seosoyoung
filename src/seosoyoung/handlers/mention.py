"""@seosoyoung 멘션 핸들러"""

import asyncio
import os
import re
import logging
from pathlib import Path

from seosoyoung.config import Config
from seosoyoung.restart import RestartType
from seosoyoung.translator import detect_language, translate
from seosoyoung.slack import download_files_sync, build_file_context
from seosoyoung.handlers.message import process_thread_message, build_slack_context

logger = logging.getLogger(__name__)

# Recall 지연 임포트 (의존성 순환 방지)
_recall = None


def _get_recall():
    """Recall 싱글톤 반환 (지연 초기화)"""
    global _recall
    if _recall is None and Config.RECALL_ENABLED:
        try:
            from anthropic import AsyncAnthropic
            from seosoyoung.recall import Recall

            api_key = Config.RECALL_API_KEY
            if not api_key:
                logger.warning("RECALL_API_KEY가 설정되지 않아 Recall 비활성화")
                return None

            workspace_path = Path.cwd()
            client = AsyncAnthropic(api_key=api_key)
            model = Config.RECALL_MODEL

            _recall = Recall(
                workspace_path=workspace_path,
                client=client,
                model=model,
                threshold=Config.RECALL_THRESHOLD,
                timeout=Config.RECALL_TIMEOUT,
            )
            logger.info(f"Recall 초기화 완료 (모델: {model})")
        except Exception as e:
            logger.error(f"Recall 초기화 실패: {e}")
            return None
    return _recall


def _run_recall(user_request: str):
    """Recall 실행 (동기 래퍼)

    Args:
        user_request: 사용자 요청

    Returns:
        RecallResult 또는 None
    """
    recall = _get_recall()
    if not recall:
        return None

    try:
        result = asyncio.run(recall.analyze(user_request))
        if result.suitable_tools:
            logger.info(
                f"Recall 완료: {len(result.suitable_tools)}개 도구 적합, "
                f"최고점={result.selected_tool}({result.confidence*10:.0f}점), "
                f"시간={result.evaluation_time_ms:.0f}ms"
            )
        else:
            logger.info(f"Recall 완료: 적합한 도구 없음")
        return result
    except Exception as e:
        logger.error(f"Recall 실패: {e}")
        return None


def extract_command(text: str) -> str:
    """멘션에서 명령어 추출"""
    match = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    return match.lower()


def _is_resume_list_run_command(command: str) -> bool:
    """정주행 재개 명령어인지 확인

    다음과 같은 패턴을 인식합니다:
    - 정주행 재개해줘
    - 정주행 재개
    - 리스트런 재개
    - resume list run
    """
    resume_patterns = [
        r"정주행\s*(을\s*)?재개",
        r"리스트런\s*(을\s*)?재개",
        r"resume\s*(list\s*)?run",
    ]
    for pattern in resume_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def build_prompt_with_recall(
    context: str,
    question: str,
    file_context: str,
    recall_result=None,
    slack_context: str = "",
) -> str:
    """Recall 결과를 포함한 프롬프트 구성.

    Args:
        context: 채널 히스토리 컨텍스트
        question: 사용자 질문
        file_context: 첨부 파일 컨텍스트
        recall_result: RecallResult 객체 (선택사항)
        slack_context: 슬랙 컨텍스트 블록 문자열

    Returns:
        구성된 프롬프트 문자열
    """
    prompt_parts = []

    if slack_context:
        prompt_parts.append(slack_context)

    prompt_parts.append(f"아래는 Slack 채널의 최근 대화입니다:\n\n{context}")

    # Recall 결과 주입
    if recall_result and recall_result.has_recommendation:
        recall_injection = recall_result.to_prompt_injection()
        if recall_injection:
            prompt_parts.append(f"\n{recall_injection}")

    if question:
        prompt_parts.append(f"\n사용자의 질문: {question}")

    if file_context:
        prompt_parts.append(file_context)

    prompt_parts.append("\n위 컨텍스트를 참고하여 질문에 답변해주세요.")

    return "\n".join(prompt_parts)


def get_channel_history(client, channel: str, limit: int = 20) -> str:
    """채널의 최근 메시지를 가져와서 컨텍스트 문자열로 반환"""
    try:
        result = client.conversations_history(channel=channel, limit=limit)
        messages = result.get("messages", [])

        # 시간순 정렬 (오래된 것부터)
        messages = list(reversed(messages))

        context_lines = []
        for msg in messages:
            user = msg.get("user", "unknown")
            text = msg.get("text", "")
            context_lines.append(f"<{user}>: {text}")

        return "\n".join(context_lines)
    except Exception as e:
        logger.warning(f"채널 히스토리 가져오기 실패: {e}")
        return ""


def register_mention_handlers(app, dependencies: dict):
    """멘션 핸들러 등록

    Args:
        app: Slack Bolt App 인스턴스
        dependencies: 의존성 딕셔너리
    """
    session_manager = dependencies["session_manager"]
    restart_manager = dependencies["restart_manager"]
    get_running_session_count = dependencies["get_running_session_count"]
    run_claude_in_session = dependencies["run_claude_in_session"]
    check_permission = dependencies["check_permission"]
    get_user_role = dependencies["get_user_role"]
    send_restart_confirmation = dependencies["send_restart_confirmation"]
    list_runner_ref = dependencies.get("list_runner_ref", lambda: None)

    @app.event("app_mention")
    def handle_mention(event, say, client):
        """@seosoyoung 멘션 처리

        - 채널에서 멘션: 세션 생성 + Claude 실행
        - 스레드에서 멘션 (세션 있음): handle_message에서 처리
        - 스레드에서 멘션 (세션 없음): 원샷 답변
        - help/status/update/restart: 관리자 명령어
        """
        user_id = event["user"]
        text = event.get("text", "")
        channel = event["channel"]
        ts = event["ts"]
        thread_ts = event.get("thread_ts")

        logger.info(f"멘션 수신: user={user_id}, channel={channel}, text={text[:50]}")

        command = extract_command(text)

        # 관리자 명령어는 스레드/세션 여부와 관계없이 항상 처리
        admin_commands = ["help", "status", "update", "restart", "compact", "profile"]
        is_admin_command = command in admin_commands or command.startswith("profile ")

        # 정주행 재개 명령어 처리
        if _is_resume_list_run_command(command):
            list_runner = list_runner_ref()
            if not list_runner:
                say(text="리스트 러너가 초기화되지 않았습니다.", thread_ts=ts)
                return

            paused_sessions = list_runner.get_paused_sessions()
            if not paused_sessions:
                say(text="현재 중단된 정주행 세션이 없습니다.", thread_ts=ts)
                return

            # 가장 최근 중단된 세션 재개
            session_to_resume = paused_sessions[-1]
            if list_runner.resume_run(session_to_resume.session_id):
                say(
                    text=(
                        f"✅ *정주행 재개*\n"
                        f"• 리스트: {session_to_resume.list_name}\n"
                        f"• 세션 ID: {session_to_resume.session_id}\n"
                        f"• 진행률: {session_to_resume.current_index}/{len(session_to_resume.card_ids)} 카드"
                    ),
                    thread_ts=ts
                )
            else:
                say(text="정주행 재개에 실패했습니다.", thread_ts=ts)
            return

        # 스레드에서 멘션된 경우 (관리자 명령어가 아닐 때만 세션 체크)
        if thread_ts and not is_admin_command:
            session = session_manager.get(thread_ts)
            if session:
                # 세션이 있는 스레드에서 멘션 → 직접 처리
                # (message.py는 봇 멘션이 포함된 메시지를 무시하므로 여기서 처리)
                logger.debug("스레드에서 멘션됨 (세션 있음) - 직접 처리")

                if restart_manager.is_pending:
                    say(
                        text="재시작을 대기하는 중입니다.\n재시작이 완료되면 다시 대화를 요청해주세요.",
                        thread_ts=thread_ts
                    )
                    return

                process_thread_message(
                    event, text, thread_ts, ts, channel, session, say, client,
                    get_user_role, run_claude_in_session, log_prefix="스레드 멘션"
                )
                return
            logger.debug("스레드에서 멘션됨 (세션 없음) - 원샷 답변")

        logger.info(f"명령어 처리: command={command}")

        # 재시작 대기 중이면 안내 메시지 (관리자 명령어 제외)
        if restart_manager.is_pending and not is_admin_command:
            say(
                text="재시작을 대기하는 중입니다.\n재시작이 완료되면 다시 대화를 요청해주세요.",
                thread_ts=ts
            )
            return

        # 관리자 명령어 처리
        if command == "help":
            say(
                text=(
                    "📖 *사용법*\n"
                    "• `@seosoyoung <질문>` - 질문하기 (세션 생성 + 응답)\n"
                    "• `@seosoyoung 번역 <텍스트>` - 번역 테스트\n"
                    "• `@seosoyoung help` - 도움말\n"
                    "• `@seosoyoung status` - 상태 확인\n"
                    "• `@seosoyoung compact` - 스레드 세션 컴팩트\n"
                    "• `@seosoyoung profile` - 인증 프로필 관리 (관리자)\n"
                    "• `@seosoyoung update` - 봇 업데이트 (관리자)\n"
                    "• `@seosoyoung restart` - 봇 재시작 (관리자)"
                ),
                thread_ts=ts
            )
            return

        if command == "status":
            say(
                text=(
                    f"📊 *상태*\n"
                    f"• 작업 폴더: `{Path.cwd()}`\n"
                    f"• 관리자: {', '.join(Config.ADMIN_USERS)}\n"
                    f"• 활성 세션: {session_manager.count()}개\n"
                    f"• 디버그 모드: {Config.DEBUG}"
                )
            )
            return

        # 번역 테스트 명령어
        if command.startswith("번역 ") or command.startswith("번역\n"):
            translate_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
            # "번역 " 또는 "번역\n" 제거
            translate_text = re.sub(r"^번역[\s\n]+", "", translate_text, flags=re.IGNORECASE).strip()

            if not translate_text:
                say(text="번역할 텍스트를 입력해주세요.\n예: `@seosoyoung 번역 Hello, world!`", thread_ts=ts)
                return

            try:
                # 번역 진행 중 리액션
                client.reactions_add(channel=channel, timestamp=ts, name="hourglass_flowing_sand")

                source_lang = detect_language(translate_text)
                translated, cost, glossary_terms, _ = translate(translate_text, source_lang)

                target_lang = "영어" if source_lang.value == "ko" else "한국어"

                # 응답 구성
                lines = [
                    f"*번역 결과* ({source_lang.value} → {target_lang})",
                    f"```{translated}```",
                    f"`💵 ${cost:.4f}`"
                ]
                if glossary_terms:
                    terms_str = ", ".join(f"{s}→{t}" for s, t in glossary_terms[:5])
                    if len(glossary_terms) > 5:
                        terms_str += f" 외 {len(glossary_terms) - 5}개"
                    lines.append(f"`📖 {terms_str}`")

                say(text="\n".join(lines), thread_ts=ts)

                # 완료 리액션
                client.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
                client.reactions_add(channel=channel, timestamp=ts, name=Config.EMOJI_TRANSLATE_DONE)

            except Exception as e:
                logger.exception(f"번역 테스트 실패: {e}")
                try:
                    client.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
                except Exception:
                    pass
                say(text=f"번역 실패: `{e}`", thread_ts=ts)
            return

        if command in ["update", "restart"]:
            if not check_permission(user_id, client):
                logger.warning(f"권한 없음: user={user_id}")
                say(text="관리자 권한이 필요합니다.", thread_ts=ts)
                return

            restart_type = RestartType.UPDATE if command == "update" else RestartType.RESTART

            # 실행 중인 세션이 있으면 확인 프로세스
            running_count = get_running_session_count()
            if running_count > 0:
                send_restart_confirmation(
                    client=client,
                    channel=Config.TRELLO_NOTIFY_CHANNEL,
                    restart_type=restart_type,
                    running_count=running_count,
                    user_id=user_id,
                    original_thread_ts=ts
                )
                return

            # 실행 중인 세션이 없으면 즉시 재시작
            type_name = "업데이트" if command == "update" else "재시작"
            logger.info(f"{type_name} 요청 - 프로세스 종료")
            restart_manager.force_restart(restart_type)
            return

        # compact 명령어 처리
        if command == "compact":
            if not thread_ts:
                say(text="스레드에서 사용해주세요.", thread_ts=ts)
                return

            session = session_manager.get(thread_ts)
            if not session or not session.session_id:
                say(text="활성 세션이 없습니다.", thread_ts=thread_ts)
                return

            say(text="컴팩트 중입니다...", thread_ts=thread_ts)

            try:
                from seosoyoung.claude import get_claude_runner

                runner = get_claude_runner()
                compact_result = asyncio.run(runner.compact_session(session.session_id))

                if compact_result.success:
                    if compact_result.session_id:
                        session_manager.update_session_id(thread_ts, compact_result.session_id)
                    say(text="컴팩트가 완료됐습니다.", thread_ts=thread_ts)
                else:
                    say(text=f"컴팩트에 실패했습니다: {compact_result.error}", thread_ts=thread_ts)
            except Exception as e:
                logger.exception(f"compact 명령어 오류: {e}")
                say(text=f"컴팩트 중 오류가 발생했습니다: {e}", thread_ts=thread_ts)
            return

        # profile 명령어 처리
        if command.startswith("profile"):
            if not check_permission(user_id, client):
                logger.warning(f"profile 권한 없음: user={user_id}")
                say(text="관리자 권한이 필요합니다.", thread_ts=thread_ts)
                return

            from seosoyoung.profile.manager import ProfileManager

            # 프로필 경로 설정 (CLAUDE_CONFIG_DIR + Junction 방식)
            profiles_dir = Path.cwd() / ".local" / "claude_profiles"
            claude_config_dir = Path.home() / ".claude"
            manager = ProfileManager(profiles_dir=profiles_dir)

            # 서브커맨드 파싱
            parts = command.split()
            subcmd = parts[1] if len(parts) > 1 else None
            arg = parts[2] if len(parts) > 2 else None

            # 응답 위치: 스레드에서 호출했으면 스레드, 채널에서 호출했으면 채널
            reply_ts = thread_ts

            try:
                if subcmd == "list":
                    profiles = manager.list_profiles()
                    if not profiles:
                        say(text="저장된 프로필이 없습니다.", thread_ts=reply_ts)
                    else:
                        lines = ["*📋 프로필 목록*"]
                        for p in profiles:
                            marker = "✅ " if p.is_active else "• "
                            lines.append(f"{marker}`{p.name}`")
                        say(text="\n".join(lines), thread_ts=reply_ts)

                elif subcmd == "save":
                    if not arg:
                        say(text="저장할 프로필 이름을 입력해주세요.\n예: `@seosoyoung profile save work`", thread_ts=reply_ts)
                    else:
                        result = manager.save_profile(arg, claude_config_dir)
                        say(text=f"✅ {result}", thread_ts=reply_ts)

                elif subcmd == "change":
                    if not arg:
                        say(text="전환할 프로필 이름을 입력해주세요.\n예: `@seosoyoung profile change work`", thread_ts=reply_ts)
                    else:
                        result = manager.change_profile(arg)
                        say(text=f"🔄 {result}", thread_ts=reply_ts)

                elif subcmd == "delete":
                    if not arg:
                        say(text="삭제할 프로필 이름을 입력해주세요.\n예: `@seosoyoung profile delete work`", thread_ts=reply_ts)
                    else:
                        result = manager.delete_profile(arg)
                        say(text=f"🗑️ {result}", thread_ts=reply_ts)

                else:
                    say(
                        text=(
                            "📁 *profile 명령어 사용법*\n"
                            "• `profile list` - 저장된 프로필 목록\n"
                            "• `profile save <이름>` - 현재 인증을 프로필로 저장\n"
                            "• `profile change <이름>` - 프로필로 전환 (재시작 후 적용)\n"
                            "• `profile delete <이름>` - 프로필 삭제"
                        ),
                        thread_ts=reply_ts
                    )

            except (ValueError, FileNotFoundError, FileExistsError) as e:
                say(text=f"❌ {e}", thread_ts=reply_ts)
            except Exception as e:
                logger.exception(f"profile 명령어 오류: {e}")
                say(text=f"❌ 오류가 발생했습니다: {e}", thread_ts=reply_ts)
            return

        # 일반 질문: 세션 생성 + Claude 실행
        user_info = get_user_role(user_id, client)
        if not user_info:
            say(text="사용자 정보를 확인할 수 없습니다.", thread_ts=thread_ts or ts)
            return

        # 세션 생성 위치 결정
        session_thread_ts = thread_ts or ts
        is_existing_thread = thread_ts is not None  # 기존 스레드에서 호출됨

        # 세션 생성 (역할 정보 포함)
        session = session_manager.create(
            thread_ts=session_thread_ts,
            channel_id=channel,
            user_id=user_id,
            username=user_info["username"],
            role=user_info["role"]
        )

        # 멘션 텍스트에서 질문 추출 (멘션 제거)
        clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        # 첨부 파일 처리
        file_context = ""
        if event.get("files"):
            try:
                downloaded_files = download_files_sync(event, session_thread_ts)
                if downloaded_files:
                    file_context = build_file_context(downloaded_files)
                    logger.info(f"파일 {len(downloaded_files)}개 다운로드 완료")
            except Exception as e:
                logger.error(f"파일 다운로드 실패: {e}")

        if not clean_text and not file_context:
            logger.info(f"빈 질문 - 세션만 생성됨: thread_ts={session_thread_ts}")
            return

        # 초기 메시지 표시 (리콜 시작 전) - blockquote 형태
        initial_text = "> 소영이 생각합니다..."
        if is_existing_thread:
            # 스레드 내 후속 대화: 해당 스레드에 응답
            initial_msg = client.chat_postMessage(
                channel=channel,
                thread_ts=session_thread_ts,
                text=initial_text,
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": initial_text}
                }]
            )
            initial_msg_ts = initial_msg["ts"]
        else:
            # 채널에서 최초 멘션: 채널 루트에 응답
            initial_msg = client.chat_postMessage(
                channel=channel,
                text=initial_text,
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": initial_text}
                }]
            )
            initial_msg_ts = initial_msg["ts"]

        # Recall 실행 (활성화된 경우)
        recall_result = None
        if Config.RECALL_ENABLED and clean_text:
            recall_result = _run_recall(clean_text)

            # 디버깅용: Recall 결과를 M(멘션 메시지)의 스레드에 답글
            # P(사고 과정)에 스레드를 달지 않기 위해 session_thread_ts(=M의 ts)를 사용
            if recall_result and recall_result.suitable_tools:
                recall_debug_lines = ["*🔍 Recall 결과*", ""]
                for tool_info in recall_result.suitable_tools:
                    recall_debug_lines.append(f"*{tool_info['name']}* ({tool_info['type']}) - {tool_info['score']}점")
                    if tool_info.get('approach'):
                        recall_debug_lines.append(f"> {tool_info['approach']}")
                    if tool_info.get('reason'):
                        # reason의 각 줄을 blockquote로
                        for line in tool_info['reason'].split('\n'):
                            if line.strip():
                                recall_debug_lines.append(f"> {line}")
                    recall_debug_lines.append("")

                recall_debug_lines.append(f"`⏱️ {recall_result.evaluation_time_ms:.0f}ms`")

                client.chat_postMessage(
                    channel=channel,
                    thread_ts=session_thread_ts,
                    text="\n".join(recall_debug_lines),
                )

        # 채널 컨텍스트 가져오기
        context = get_channel_history(client, channel, limit=20)

        # 슬랙 컨텍스트 생성
        slack_ctx = build_slack_context(
            channel=channel,
            user_id=user_id,
            thread_ts=ts,
            parent_thread_ts=thread_ts,
        )

        # 프롬프트 구성 (Recall 결과 + 슬랙 컨텍스트 포함)
        prompt = build_prompt_with_recall(
            context=context,
            question=clean_text,
            file_context=file_context,
            recall_result=recall_result,
            slack_context=slack_ctx,
        )

        # Claude 실행 (스레드 락으로 동시 실행 방지)
        run_claude_in_session(
            session, prompt, ts, channel, say, client,
            is_existing_thread=is_existing_thread,
            initial_msg_ts=initial_msg_ts
        )
