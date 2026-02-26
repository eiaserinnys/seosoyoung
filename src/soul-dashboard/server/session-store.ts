/**
 * Session Store - JSONL 파일 읽기 전용 저장소
 *
 * Phase 4의 EventStore(Python)가 생성한 JSONL 파일을 읽어
 * 세션 목록과 이벤트 내역을 제공합니다.
 *
 * 파일 경로 규칙: {baseDir}/{clientId}/{requestId}.jsonl
 * 각 줄: {"id": <monotonic_int>, "event": <event_dict>}
 */

import { readFile, readdir, stat, mkdir, appendFile } from "fs/promises";
import { join, basename, dirname } from "path";
import type {
  EventRecord,
  SessionSummary,
  SessionStatus,
} from "../shared/types.js";

export interface SessionStoreOptions {
  /** JSONL 파일 기본 디렉토리 */
  baseDir: string;
}

/**
 * JSONL 파일 읽기 전용 세션 저장소.
 *
 * EventStore(Python)가 작성한 JSONL 파일을 읽어
 * 대시보드 API에 세션/이벤트 데이터를 제공합니다.
 */
export class SessionStore {
  private readonly baseDir: string;

  constructor(options: SessionStoreOptions) {
    this.baseDir = options.baseDir;
  }

  /**
   * 모든 세션의 요약 목록을 반환합니다.
   *
   * 파일시스템을 스캔하여 {baseDir}/{clientId}/{requestId}.jsonl 패턴의
   * 파일에서 세션 메타데이터를 수집합니다.
   */
  async listSessions(): Promise<SessionSummary[]> {
    const sessions: SessionSummary[] = [];

    let clientDirs: string[];
    try {
      clientDirs = await readdir(this.baseDir);
    } catch {
      // baseDir이 없으면 빈 목록 반환
      return sessions;
    }

    for (const clientId of clientDirs) {
      // 경로 탈출 및 XSS 방지: 안전한 문자만 포함된 디렉토리만 허용
      if (!this.isValidPathComponent(clientId)) {
        console.warn(
          `[SessionStore] Skipping invalid client directory: ${clientId}`,
        );
        continue;
      }

      const clientPath = join(this.baseDir, clientId);

      let clientStat;
      try {
        clientStat = await stat(clientPath);
      } catch {
        continue;
      }
      if (!clientStat.isDirectory()) continue;

      let files: string[];
      try {
        files = await readdir(clientPath);
      } catch {
        continue;
      }

      for (const file of files) {
        if (!file.endsWith(".jsonl")) continue;

        const requestId = basename(file, ".jsonl");

        // 파일명도 안전한 문자만 허용
        if (!this.isValidPathComponent(requestId)) {
          console.warn(
            `[SessionStore] Skipping invalid request file: ${file}`,
          );
          continue;
        }
        const filePath = join(clientPath, file);

        try {
          const summary = await this.readSessionSummary(
            clientId,
            requestId,
            filePath,
          );
          sessions.push(summary);
        } catch (err) {
          console.warn(
            `[SessionStore] Failed to read session ${clientId}:${requestId}:`,
            err,
          );
        }
      }
    }

    // 최신 세션이 먼저 오도록 정렬
    sessions.sort((a, b) => {
      const aTime = a.createdAt ?? "";
      const bTime = b.createdAt ?? "";
      return bTime.localeCompare(aTime);
    });

    return sessions;
  }

  /**
   * 특정 세션의 모든 이벤트를 반환합니다.
   *
   * @param clientId - 클라이언트 ID
   * @param requestId - 요청 ID
   * @returns 이벤트 레코드 배열 (id 오름차순)
   */
  async readEvents(
    clientId: string,
    requestId: string,
  ): Promise<EventRecord[]> {
    const filePath = this.sessionPath(clientId, requestId);

    let content: string;
    try {
      content = await readFile(filePath, "utf-8");
    } catch {
      return [];
    }

    return this.parseJsonl(content);
  }

  /**
   * 특정 ID 이후의 이벤트만 반환합니다 (Last-Event-ID 재연결용).
   *
   * @param clientId - 클라이언트 ID
   * @param requestId - 요청 ID
   * @param afterId - 이 ID 이후의 이벤트만 반환
   */
  async readEventsSince(
    clientId: string,
    requestId: string,
    afterId: number,
  ): Promise<EventRecord[]> {
    const events = await this.readEvents(clientId, requestId);
    return events.filter((ev) => ev.id > afterId);
  }

  /**
   * JSONL 파일에 이벤트를 추가합니다.
   *
   * 대시보드에서 생성한 이벤트(user_message 등)를 JSONL에 기록하여
   * 히스토리 리플레이 시에도 사용할 수 있게 합니다.
   *
   * @param clientId - 클라이언트 ID
   * @param requestId - 요청 ID
   * @param eventId - 이벤트 ID (단조증가)
   * @param event - 이벤트 페이로드
   */
  async appendEvent(
    clientId: string,
    requestId: string,
    eventId: number,
    event: Record<string, unknown>,
  ): Promise<void> {
    const filePath = this.sessionPath(clientId, requestId);
    const dirPath = dirname(filePath);

    // 디렉토리가 없으면 생성
    await mkdir(dirPath, { recursive: true });

    const record = JSON.stringify({ id: eventId, event });
    await appendFile(filePath, record + "\n", "utf-8");
  }

  /**
   * 세션의 마지막 이벤트 타입으로 상태를 추론합니다.
   */
  inferStatus(lastEventType?: string): SessionStatus {
    if (!lastEventType) return "unknown";
    if (lastEventType === "complete" || lastEventType === "result")
      return "completed";
    if (lastEventType === "error") return "error";
    return "running";
  }

  private sessionPath(clientId: string, requestId: string): string {
    // 경로 탈출 방지: 안전한 문자만 허용
    const safeClientId = this.sanitize(clientId);
    const safeRequestId = this.sanitize(requestId);
    return join(this.baseDir, safeClientId, `${safeRequestId}.jsonl`);
  }

  private sanitize(value: string): string {
    return value.replace(/[^\w.\-]/g, "_");
  }

  private isValidPathComponent(value: string): boolean {
    return /^[\w.\-]+$/.test(value);
  }

  private parseJsonl(content: string): EventRecord[] {
    const records: EventRecord[] = [];
    const lines = content.split("\n");

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      try {
        const record = JSON.parse(trimmed) as EventRecord;
        if (typeof record.id === "number" && record.event) {
          records.push(record);
        }
      } catch {
        console.warn("[SessionStore] Skipping corrupted JSONL line");
      }
    }

    return records;
  }

  private async readSessionSummary(
    clientId: string,
    requestId: string,
    filePath: string,
  ): Promise<SessionSummary> {
    const content = await readFile(filePath, "utf-8");
    const records = this.parseJsonl(content);

    const eventCount = records.length;
    const lastRecord = records[records.length - 1];
    const lastEventType = lastRecord?.event?.type as string | undefined;
    const firstRecord = records[0];

    // 첫 이벤트의 타임스탬프에서 생성 시간 추정
    let createdAt: string | undefined;
    if (firstRecord?.event) {
      // created_at 필드가 이벤트에 있을 수 있음
      const eventData = firstRecord.event as Record<string, unknown>;
      if (typeof eventData.created_at === "string") {
        createdAt = eventData.created_at;
      }
    }

    // 파일 수정 시간을 폴백으로 사용
    if (!createdAt) {
      try {
        const fileStat = await stat(filePath);
        createdAt = fileStat.birthtime.toISOString();
      } catch {
        // ignore
      }
    }

    // 완료 시간: complete/error 이벤트의 타임스탬프
    let completedAt: string | undefined;
    if (
      lastEventType === "complete" ||
      lastEventType === "error" ||
      lastEventType === "result"
    ) {
      try {
        const fileStat = await stat(filePath);
        completedAt = fileStat.mtime.toISOString();
      } catch {
        // ignore
      }
    }

    return {
      clientId,
      requestId,
      status: this.inferStatus(lastEventType),
      eventCount,
      lastEventType,
      createdAt,
      completedAt,
    };
  }
}
