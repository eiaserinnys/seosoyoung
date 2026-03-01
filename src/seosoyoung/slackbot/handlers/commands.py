"""명령어 핸들러 모듈

mention.py의 try_handle_command에서 분리된 개별 명령어 핸들러들을 제공합니다.
각 핸들러는 keyword-only 인자를 받고, 사용하지 않는 인자는 **_로 흡수합니다.
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

import psutil

from seosoyoung.slackbot.config import Config
from seosoyoung.slackbot.restart import RestartType

logger = logging.getLogger(__name__)


# ── 유틸리티 함수 ──────────────────────────────────────────────


def get_ancestors(pid: int) -> list[int]:
    """PID의 조상 체인(ancestor chain)을 반환"""
    ancestors = []
    try:
        proc = psutil.Process(pid)
        while proc.ppid() != 0:
            parent_pid = proc.ppid()
            ancestors.append(parent_pid)
            proc = psutil.Process(parent_pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    return ancestors


def format_elapsed(elapsed_secs: float) -> str:
    """경과 시간을 사람이 읽기 쉬운 형태로 포맷"""
    if elapsed_secs >= 3600:
        return f"{int(elapsed_secs // 3600)}시간"
    elif elapsed_secs >= 60:
        return f"{int(elapsed_secs // 60)}분"
    else:
        return f"{int(elapsed_secs)}초"


def _collect_all_processes() -> dict:
    """모든 프로세스의 기본 정보(pid, name, ppid, create_time)를 수집"""
    all_processes = {}
    for proc in psutil.process_iter(["pid", "name", "ppid", "create_time"]):
        try:
            all_processes[proc.info["pid"]] = {
                "name": proc.info["name"],
                "ppid": proc.info["ppid"] or 0,
                "create_time": proc.info["create_time"],
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return all_processes


def _collect_claude_processes(*, include_cpu: bool = False, include_exe: bool = False) -> dict:
    """Claude/node 관련 프로세스의 상세 정보를 수집"""
    fields = ["pid", "name", "memory_info", "create_time", "ppid", "cmdline"]
    if include_cpu:
        fields.append("cpu_percent")
    if include_exe:
        fields.append("exe")

    claude_processes = {}
    for proc in psutil.process_iter(fields):
        try:
            name = proc.info["name"].lower()
            if "claude" not in name and "node" not in name:
                continue
            pid = proc.info["pid"]
            mem_bytes = proc.info["memory_info"].rss if proc.info["memory_info"] else 0
            create_time = proc.info["create_time"]
            elapsed_secs = datetime.now().timestamp() - create_time
            cmdline_list = proc.info["cmdline"] or []
            cmdline = " ".join(cmdline_list) if cmdline_list else ""
            if len(cmdline) > 80:
                cmdline = cmdline[:77] + "..."

            info = {
                "pid": pid,
                "ppid": proc.info["ppid"] or 0,
                "name": proc.info["name"],
                "mem_mb": mem_bytes / (1024 * 1024),
                "elapsed_secs": elapsed_secs,
                "elapsed": format_elapsed(elapsed_secs),
                "cmdline": cmdline,
                "create_time": create_time,
            }
            if include_cpu:
                info["cpu"] = proc.info["cpu_percent"] or 0.0
            if include_exe:
                info["exe_path"] = proc.info.get("exe") or ""

            claude_processes[pid] = info
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return claude_processes


def _classify_processes(
    claude_processes: dict, all_processes: dict, *, exclude_desktop: bool = False
) -> tuple[dict, list]:
    """프로세스를 봇 트리와 고아로 분류하여 (bot_tree, orphan_processes) 반환"""
    bot_tree = {}
    orphan_processes = []

    for pid, proc_info in claude_processes.items():
        ancestors = get_ancestors(pid)
        found_root = None
        for ancestor_pid in ancestors:
            if ancestor_pid in all_processes:
                ancestor_name = all_processes[ancestor_pid]["name"].lower()
                if "node" in ancestor_name or "python" in ancestor_name:
                    found_root = ancestor_pid

        if found_root:
            if found_root not in bot_tree:
                root_info = all_processes.get(found_root, {})
                root_create_time = root_info.get("create_time", 0)
                bot_tree[found_root] = {
                    "root_pid": found_root,
                    "root_name": root_info.get("name", "unknown"),
                    "root_elapsed": (
                        format_elapsed(datetime.now().timestamp() - root_create_time)
                        if root_create_time
                        else "N/A"
                    ),
                    "processes": [],
                }
            bot_tree[found_root]["processes"].append(proc_info)
        else:
            if exclude_desktop:
                exe_path = proc_info.get("exe_path", "").lower()
                if "anthropicclaude" in exe_path:
                    continue
            orphan_processes.append(proc_info)

    for tree_info in bot_tree.values():
        tree_info["processes"].sort(key=lambda x: x["elapsed_secs"])
    orphan_processes.sort(key=lambda x: x["mem_mb"], reverse=True)

    return bot_tree, orphan_processes


def _format_mem_size(mb: float) -> str:
    """메모리 크기를 사람이 읽기 쉬운 형태로 포맷"""
    if mb >= 1024:
        return f"{mb / 1024:.1f}GB"
    return f"{mb:.0f}MB"


# ── 명령어 핸들러 ──────────────────────────────────────────────


def handle_help(*, say, ts, **_):
    """help 명령어 핸들러"""
    say(
        text=(
            "📖 *사용법*\n"
            "• `@seosoyoung <질문>` - 질문하기 (세션 생성 + 응답)\n"
            "• `@seosoyoung 번역 <텍스트>` - 번역 테스트\n"
            "• `@seosoyoung help` - 도움말\n"
            "• `@seosoyoung status` - 상태 확인\n"
            "• `@seosoyoung log` - 오늘자 로그 파일 첨부\n"
            "• `@seosoyoung compact` - 스레드 세션 컴팩트\n"
            "• `@seosoyoung cleanup` - 고아 프로세스/세션 정리 (관리자)\n"
            "• `@seosoyoung profile` - 인증 프로필 관리 (관리자)\n"
            "• `@seosoyoung update` - 봇 업데이트 (관리자)\n"
            "• `@seosoyoung restart` - 봇 재시작 (관리자)"
        ),
        thread_ts=ts,
    )


def handle_status(*, say, ts, session_manager, **_):
    """status 명령어 핸들러 - 시스템 상태 및 프로세스 트리 표시"""
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    mem_used_str = _format_mem_size(mem.used / (1024 * 1024))
    mem_total_str = _format_mem_size(mem.total / (1024 * 1024))

    all_processes = _collect_all_processes()
    claude_processes = _collect_claude_processes(include_cpu=True)
    bot_tree, orphan_processes = _classify_processes(claude_processes, all_processes)

    status_lines = [
        f"📊 *상태*",
        f"• 작업 폴더: `{Path.cwd()}`",
        f"• 관리자: {', '.join(Config.auth.admin_users)}",
        f"• 활성 세션: {session_manager.count()}개",
        f"• 디버그 모드: {Config.debug}",
        f"• CPU 사용률: {cpu_percent:.1f}%",
        f"• 메모리: {mem_used_str} / {mem_total_str} ({mem.percent:.1f}%)",
        f"• Claude 관련 프로세스: {len(claude_processes)}개",
    ]

    for root_pid, tree_info in bot_tree.items():
        status_lines.append("")
        status_lines.append(
            f"  *[봇 트리]* 루트 PID {tree_info['root_pid']} "
            f"({tree_info['root_name']}, {tree_info['root_elapsed']})"
        )
        for proc_info in tree_info["processes"]:
            status_lines.append(
                f"    └─ PID {proc_info['pid']}: {proc_info['name']} "
                f"({proc_info['mem_mb']:.0f}MB, {proc_info['elapsed']})"
            )
            if proc_info["cmdline"]:
                status_lines.append(f"       cmd: {proc_info['cmdline']}")

    if orphan_processes:
        status_lines.append("")
        status_lines.append("  ⚠️ *고아 프로세스* (봇과 무관)")
        for proc_info in orphan_processes[:5]:
            status_lines.append(
                f"    - PID {proc_info['pid']}: {proc_info['name']} "
                f"({proc_info['mem_mb']:.0f}MB, {proc_info['elapsed']})"
            )
            if proc_info["cmdline"]:
                status_lines.append(f"      cmd: {proc_info['cmdline']}")
        if len(orphan_processes) > 5:
            status_lines.append(f"    ... 외 {len(orphan_processes) - 5}개")

    say(text="\n".join(status_lines))


def handle_cleanup(*, command, say, ts, client, user_id, session_manager, check_permission, **_):
    """cleanup 명령어 핸들러 - 고아 프로세스 및 오래된 세션 정리"""
    if not check_permission(user_id, client):
        logger.warning(f"cleanup 권한 없음: user={user_id}")
        say(text="관리자 권한이 필요합니다.", thread_ts=ts)
        return

    is_confirm = command == "cleanup confirm"

    all_processes = _collect_all_processes()
    claude_processes = _collect_claude_processes(include_exe=True)
    _, orphan_processes = _classify_processes(
        claude_processes, all_processes, exclude_desktop=True
    )

    # 오래된 세션 식별
    old_sessions = _collect_old_sessions(session_manager)
    threshold_hours = 24

    mem_str = _format_mem_size(sum(p["mem_mb"] for p in orphan_processes))

    if not is_confirm:
        say(text=_format_cleanup_preview(orphan_processes, old_sessions, mem_str), thread_ts=ts)
        return

    # Confirm: 실제 정리 수행
    terminated_lines, failed_lines, reclaimed_mem_mb = _terminate_processes(orphan_processes)
    cleaned_session_count = session_manager.cleanup_old_sessions(threshold_hours)

    say(
        text=_format_cleanup_result(
            terminated_lines, failed_lines, reclaimed_mem_mb,
            cleaned_session_count, session_manager,
        ),
        thread_ts=ts,
    )


def _collect_old_sessions(session_manager, threshold_hours: int = 24) -> list[dict]:
    """오래된 세션(threshold_hours 이상)을 식별하여 반환"""
    old_sessions = []
    now = datetime.now()
    for session in session_manager.list_active():
        try:
            created_at = datetime.fromisoformat(session.created_at)
            age_hours = (now - created_at).total_seconds() / 3600
            if age_hours >= threshold_hours:
                old_sessions.append({
                    "thread_ts": session.thread_ts,
                    "age_hours": age_hours,
                    "username": session.username or "unknown",
                })
        except Exception:
            pass
    return old_sessions


def _format_cleanup_preview(orphan_processes: list, old_sessions: list, mem_str: str) -> str:
    """cleanup dry-run 결과 메시지 포맷"""
    lines = ["*정리 대상 확인*", ""]

    if orphan_processes:
        lines.append("⚠️ *고아 프로세스* (봇과 무관):")
        for proc_info in orphan_processes:
            lines.append(
                f"  - PID {proc_info['pid']}: {proc_info['name']} "
                f"({proc_info['mem_mb']:.0f}MB, {proc_info['elapsed']})"
            )
        lines.append(f"  총 {mem_str} 회수 예정")
    else:
        lines.append("✅ 고아 프로세스 없음")

    lines.append("")

    if old_sessions:
        lines.append(f"📋 *오래된 세션* (24시간 이상):")
        lines.append(f"  - {len(old_sessions)}개 세션 정리 대상")
    else:
        lines.append("✅ 오래된 세션 없음")

    if orphan_processes or old_sessions:
        lines.append("")
        lines.append("실제 정리하려면 `@서소영 cleanup confirm`을 실행하세요.")

    return "\n".join(lines)


def _terminate_processes(orphan_processes: list) -> tuple[list[str], list[str], float]:
    """고아 프로세스를 종료하고 (terminated_lines, failed_lines, reclaimed_mb) 반환"""
    terminated_lines = []
    failed_lines = []
    reclaimed_mem_mb = 0.0

    for proc_info in orphan_processes:
        try:
            proc = psutil.Process(proc_info["pid"])
            proc.terminate()
            reclaimed_mem_mb += proc_info["mem_mb"]
            terminated_lines.append(
                f"  - PID {proc_info['pid']}: {proc_info['name']} "
                f"({proc_info['mem_mb']:.0f}MB) - 종료됨"
            )
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            failed_lines.append(
                f"  - PID {proc_info['pid']}: {proc_info['name']} - 실패: {e}"
            )

    return terminated_lines, failed_lines, reclaimed_mem_mb


def _format_cleanup_result(
    terminated_lines: list[str],
    failed_lines: list[str],
    reclaimed_mem_mb: float,
    cleaned_session_count: int,
    session_manager,
) -> str:
    """cleanup confirm 결과 메시지 포맷"""
    lines = ["*정리 완료*", ""]

    if terminated_lines:
        lines.append(f"✅ *종료된 프로세스*: {len(terminated_lines)}개")
        lines.extend(terminated_lines)
        lines.append(f"  회수된 메모리: 약 {_format_mem_size(reclaimed_mem_mb)}")
    else:
        lines.append("✅ 종료할 프로세스 없음")

    if failed_lines:
        lines.append("")
        lines.append("❌ *종료 실패*:")
        lines.extend(failed_lines)

    lines.append("")
    lines.append(f"✅ *정리된 세션*: {cleaned_session_count}개")

    mem = psutil.virtual_memory()
    mem_used_gb = mem.used / (1024 * 1024 * 1024)
    mem_total_gb = mem.total / (1024 * 1024 * 1024)
    lines.append("")
    lines.append("*현재 상태*:")
    lines.append(f"  - 활성 세션: {session_manager.count()}개")
    lines.append(f"  - 메모리 사용: {mem_used_gb:.1f}GB / {mem_total_gb:.1f}GB ({mem.percent:.1f}%)")

    return "\n".join(lines)


def handle_log(*, say, ts, thread_ts, channel, client, user_id, check_permission, **_):
    """log 명령어 핸들러 - 오늘자 로그 파일 첨부"""
    if not check_permission(user_id, client):
        logger.warning(f"log 권한 없음: user={user_id}")
        say(text="관리자 권한이 필요합니다.", thread_ts=ts)
        return

    log_dir = Path(Config.get_log_path())
    target_ts = thread_ts or ts

    log_files = [
        (log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log", "오늘자 로그 파일"),
        (log_dir / "cli_stderr.log", "CLI stderr 로그"),
    ]

    found_any = False
    for log_file, label in log_files:
        if not log_file.exists():
            continue
        found_any = True
        try:
            client.files_upload_v2(
                channel=channel,
                thread_ts=target_ts,
                file=str(log_file),
                filename=log_file.name,
                initial_comment=f"📋 {label} (`{log_file.name}`)",
            )
        except Exception as e:
            logger.exception(f"로그 파일 첨부 실패: {e}")
            say(text=f"로그 파일 첨부 실패 (`{log_file.name}`): `{e}`", thread_ts=target_ts)

    if not found_any:
        say(text="수집 가능한 로그 파일이 없습니다.", thread_ts=target_ts)


def handle_translate(*, text, say, ts, channel, client, plugin_manager=None, **_):
    """번역 명령어 핸들러

    TranslatePlugin의 설정과 translate_text() 메서드를 사용합니다.
    """
    tp = plugin_manager.plugins.get("translate") if plugin_manager else None
    if not tp:
        say(text="번역 플러그인이 로드되지 않았습니다.", thread_ts=ts)
        return

    translate_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    translate_text = re.sub(r"^번역[\s\n]+", "", translate_text, flags=re.IGNORECASE).strip()

    if not translate_text:
        say(text="번역할 텍스트를 입력해주세요.\n예: `@seosoyoung 번역 Hello, world!`", thread_ts=ts)
        return

    try:
        client.reactions_add(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
        translated, cost, glossary_terms, source_lang = tp.translate_text(translate_text)
        target_lang = "영어" if source_lang.value == "ko" else "한국어"
        lines = [
            f"*번역 결과* ({source_lang.value} → {target_lang})",
            f"```{translated}```",
            f"`💵 ${cost:.4f}`",
        ]
        if glossary_terms:
            terms_str = ", ".join(f"{s}→{t}" for s, t in glossary_terms[:5])
            if len(glossary_terms) > 5:
                terms_str += f" 외 {len(glossary_terms) - 5}개"
            lines.append(f"`📖 {terms_str}`")
        say(text="\n".join(lines), thread_ts=ts)
        client.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
        client.reactions_add(channel=channel, timestamp=ts, name=Config.emoji.translate_done)
    except Exception as e:
        logger.exception(f"번역 테스트 실패: {e}")
        try:
            client.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
        except Exception:
            pass
        say(text=f"번역 실패: `{e}`", thread_ts=ts)


def handle_update_restart(
    *,
    command,
    say,
    ts,
    user_id,
    client,
    restart_manager,
    check_permission,
    get_running_session_count,
    send_restart_confirmation,
    **_,
):
    """update/restart 명령어 핸들러"""
    if not check_permission(user_id, client):
        logger.warning(f"권한 없음: user={user_id}")
        say(text="관리자 권한이 필요합니다.", thread_ts=ts)
        return

    restart_type = RestartType.UPDATE if command == "update" else RestartType.RESTART
    running_count = get_running_session_count()

    if running_count > 0:
        send_restart_confirmation(
            client=client,
            channel=Config.slack.notify_channel,
            restart_type=restart_type,
            running_count=running_count,
            user_id=user_id,
            original_thread_ts=ts,
        )
        return

    type_name = "업데이트" if command == "update" else "재시작"
    logger.info(f"{type_name} 요청 - 프로세스 종료")
    restart_manager.force_restart(restart_type)


def handle_compact(*, say, ts, thread_ts, **_):
    """compact 명령어 핸들러 - 안내 메시지"""
    reply_ts = thread_ts or ts
    say(
        text="compact는 Soulstream 서버에서 실행 중 자동으로 처리됩니다.",
        thread_ts=reply_ts,
    )


_VALID_PROFILE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _run_soul_profile_api(async_fn):
    """SoulServiceClient 프로필 API를 동기적으로 호출

    slack_bolt sync mode에서 핸들러 스레드에는 이벤트 루프가 없으므로
    asyncio.run()으로 새 루프를 생성하여 호출합니다.

    Args:
        async_fn: SoulServiceClient 인스턴스를 받아 코루틴을 반환하는 함수

    Returns:
        API 응답 딕셔너리
    """
    from seosoyoung.slackbot.claude.service_client import SoulServiceClient

    async def _wrapper():
        soul = SoulServiceClient(
            base_url=Config.claude.soul_url,
            token=Config.claude.soul_token,
        )
        try:
            return await async_fn(soul)
        finally:
            await soul.close()

    return asyncio.run(_wrapper())


def _handle_profile_list(say, reply_ts):
    """profile list: Soulstream API로 프로필 + rate limit 조회 후 게이지 바 UI 표시"""
    from seosoyoung.slackbot.handlers.credential_ui import (
        build_credential_alert_blocks,
        build_credential_alert_text,
    )

    async def _fetch(soul):
        profiles_data = await soul.list_profiles()
        try:
            rate_limits = await soul.get_rate_limits()
        except Exception:
            rate_limits = {"active_profile": None, "profiles": []}
        return profiles_data, rate_limits

    profiles_data, rate_limits = _run_soul_profile_api(_fetch)

    active = profiles_data.get("active")
    profiles = profiles_data.get("profiles", [])

    if not profiles:
        say(text="저장된 프로필이 없습니다.", thread_ts=reply_ts)
        return

    # rate limit 데이터 병합
    rate_map = {rp["name"]: rp for rp in rate_limits.get("profiles", [])}

    merged_profiles = []
    for p in profiles:
        name = p["name"]
        rate = rate_map.get(name, {})
        merged_profiles.append({
            "name": name,
            "five_hour": rate.get("five_hour", {"utilization": "unknown", "resets_at": None}),
            "seven_day": rate.get("seven_day", {"utilization": "unknown", "resets_at": None}),
        })

    blocks = build_credential_alert_blocks(active or "", merged_profiles)
    fallback_text = build_credential_alert_text(active or "", merged_profiles)

    # 헤더를 "알림" 대신 "프로필 목록"으로 교체
    if blocks:
        blocks[0]["text"]["text"] = blocks[0]["text"]["text"].replace(
            ":warning: *크레덴셜 사용량 알림*", "📋 *크레덴셜 프로필*"
        )
    fallback_text = fallback_text.replace("크레덴셜 사용량 알림", "크레덴셜 프로필")

    say(text=fallback_text, blocks=blocks, thread_ts=reply_ts)


_PROFILE_SUBCMD_LABELS = {
    "save": "저장할",
    "delete": "삭제할",
    "change": "전환할",
}

_PROFILE_SUBCMD_API = {
    "save": lambda soul, name: soul.save_profile(name),
    "delete": lambda soul, name: soul.delete_profile(name),
    "change": lambda soul, name: soul.activate_profile(name),
}

_PROFILE_SUBCMD_RESULT = {
    "save": lambda name: f"✅ 프로필 '{name}'을(를) 저장했습니다.",
    "delete": lambda name: f"✅ 프로필 '{name}'을(를) 삭제했습니다.",
    "change": lambda name: f"✅ 프로필 '{name}'(으)로 전환했습니다.",
}


def handle_profile(*, command, say, thread_ts, client, user_id, check_permission, **_):
    """profile 명령어 핸들러 - Soulstream API 기반 인증 프로필 관리"""
    from seosoyoung.slackbot.claude.service_client import SoulServiceError

    if not check_permission(user_id, client):
        logger.warning(f"profile 권한 없음: user={user_id}")
        say(text="관리자 권한이 필요합니다.", thread_ts=thread_ts)
        return

    parts = command.split()
    subcmd = parts[1] if len(parts) > 1 else None
    arg = parts[2] if len(parts) > 2 else None
    reply_ts = thread_ts

    try:
        if subcmd is None or subcmd == "list":
            _handle_profile_list(say, reply_ts)
        elif subcmd in _PROFILE_SUBCMD_API:
            verb = _PROFILE_SUBCMD_LABELS[subcmd]
            if not arg:
                say(
                    text=f"{verb} 프로필 이름을 입력해주세요.\n예: `@seosoyoung profile {subcmd} work`",
                    thread_ts=reply_ts,
                )
                return
            if not _VALID_PROFILE_NAME.match(arg):
                say(
                    text="프로필 이름은 영문/숫자로 시작하고, 영문/숫자/하이픈/언더스코어만 사용 가능합니다 (최대 64자).",
                    thread_ts=reply_ts,
                )
                return
            _run_soul_profile_api(lambda soul: _PROFILE_SUBCMD_API[subcmd](soul, arg))
            say(text=_PROFILE_SUBCMD_RESULT[subcmd](arg), thread_ts=reply_ts)
        else:
            say(
                text=(
                    "📁 *profile 명령어 사용법*\n"
                    "• `profile` / `profile list` - 프로필 목록 + 사용량\n"
                    "• `profile save <이름>` - 현재 인증을 프로필로 저장\n"
                    "• `profile change <이름>` - 프로필 전환\n"
                    "• `profile delete <이름>` - 프로필 삭제"
                ),
                thread_ts=reply_ts,
            )
    except SoulServiceError as e:
        say(text=f"❌ {e}", thread_ts=reply_ts)
    except Exception as e:
        logger.exception(f"profile 명령어 오류: {e}")
        say(text=f"❌ 오류가 발생했습니다: {e}", thread_ts=reply_ts)


def handle_plugins(*, command, say, ts, user_id, client, check_permission, plugin_manager=None, **_):
    """plugins 명령어 핸들러 — 플러그인 목록/로드/언로드/리로드"""
    if not check_permission(user_id, client):
        logger.warning(f"plugins 권한 없음: user={user_id}")
        say(text="관리자 권한이 필요합니다.", thread_ts=ts)
        return

    if not plugin_manager:
        say(text="플러그인 매니저가 초기화되지 않았습니다.", thread_ts=ts)
        return

    parts = command.split()
    subcmd = parts[1] if len(parts) > 1 else "list"
    target = parts[2] if len(parts) > 2 else None

    if subcmd == "list":
        plugins = plugin_manager.plugins
        if not plugins:
            say(text="로드된 플러그인이 없습니다.", thread_ts=ts)
            return

        lines = ["🔌 *로드된 플러그인*"]
        for name, plugin in plugins.items():
            meta = plugin.meta
            priority = plugin_manager._priorities.get(name, 0)
            lines.append(
                f"• `{meta.name}` v{meta.version} (priority: {priority})"
            )
            if meta.description:
                lines.append(f"  _{meta.description}_")
        say(text="\n".join(lines), thread_ts=ts)

    elif subcmd == "reload" and target:
        from seosoyoung.utils.async_bridge import run_in_new_loop

        try:
            run_in_new_loop(plugin_manager.reload(target))
            say(text=f"✅ 플러그인 `{target}` 리로드 완료", thread_ts=ts)
        except Exception as e:
            say(text=f"❌ 리로드 실패 (`{target}`): {e}", thread_ts=ts)

    elif subcmd == "unload" and target:
        from seosoyoung.utils.async_bridge import run_in_new_loop

        try:
            run_in_new_loop(plugin_manager.unload(target))
            say(text=f"✅ 플러그인 `{target}` 언로드 완료", thread_ts=ts)
        except Exception as e:
            say(text=f"❌ 언로드 실패 (`{target}`): {e}", thread_ts=ts)

    elif subcmd == "load" and target:
        say(
            text=(
                "플러그인 로드는 `plugins.yaml` 레지스트리 기반으로 동작합니다.\n"
                "봇 재시작 시 자동으로 로드됩니다."
            ),
            thread_ts=ts,
        )

    else:
        say(
            text=(
                "🔌 *plugins 명령어 사용법*\n"
                "• `plugins list` - 로드된 플러그인 목록\n"
                "• `plugins reload <이름>` - 플러그인 리로드\n"
                "• `plugins unload <이름>` - 플러그인 언로드"
            ),
            thread_ts=ts,
        )


def handle_resume_list_run(*, say, ts, list_runner_ref=None, **_):
    """정주행 재개 명령어 핸들러"""
    list_runner = list_runner_ref() if list_runner_ref else None

    if not list_runner:
        say(text="리스트 러너가 초기화되지 않았습니다.", thread_ts=ts)
        return

    paused_sessions = list_runner.get_paused_sessions()
    if not paused_sessions:
        say(text="현재 중단된 정주행 세션이 없습니다.", thread_ts=ts)
        return

    session_to_resume = paused_sessions[-1]
    if list_runner.resume_run(session_to_resume.session_id):
        say(
            text=(
                f"✅ *정주행 재개*\n"
                f"• 리스트: {session_to_resume.list_name}\n"
                f"• 세션 ID: {session_to_resume.session_id}\n"
                f"• 진행률: {session_to_resume.current_index}/{len(session_to_resume.card_ids)} 카드"
            ),
            thread_ts=ts,
        )
    else:
        say(text="정주행 재개에 실패했습니다.", thread_ts=ts)
