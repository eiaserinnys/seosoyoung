/**
 * Event Hub - 대시보드 클라이언트 브로드캐스트 (1:N)
 *
 * Soul에서 수신한 이벤트를 연결된 대시보드 SSE 클라이언트들에게
 * 브로드캐스트합니다. 세션별로 리스너를 관리합니다.
 */

import type { Response } from "express";
import type { SoulSSEEvent } from "../shared/types.js";

interface SSEClient {
  id: string;
  res: Response;
  sessionKey: string;
  lastEventId: number;
}

/**
 * 대시보드 SSE 클라이언트 브로드캐스트 허브.
 *
 * 사용 패턴:
 * 1. 대시보드 클라이언트가 SSE 연결 → addClient()
 * 2. SoulClient가 이벤트 수신 → broadcast()
 * 3. EventHub가 해당 세션의 모든 클라이언트에게 이벤트 전송
 * 4. 클라이언트 연결 종료 → removeClient()
 */
export class EventHub {
  /** sessionKey → SSEClient[] */
  private readonly clients = new Map<string, SSEClient[]>();
  /** clientId → SSEClient (모든 클라이언트 조회용) */
  private readonly allClients = new Map<string, SSEClient>();
  private clientIdCounter = 0;

  /**
   * SSE 클라이언트를 세션에 등록합니다.
   *
   * @param sessionKey - "clientId:requestId" 형식의 세션 키
   * @param res - Express Response 객체 (SSE 스트림용)
   * @param lastEventId - 클라이언트가 마지막으로 수신한 이벤트 ID
   * @returns 클라이언트 ID (해제 시 사용)
   */
  addClient(
    sessionKey: string,
    res: Response,
    lastEventId?: number,
  ): string {
    const clientId = `dash-${++this.clientIdCounter}`;

    // SSE 헤더 설정
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });

    // 초기 연결 확인 이벤트
    res.write(
      `event: connected\ndata: ${JSON.stringify({ clientId, sessionKey })}\n\n`,
    );

    const client: SSEClient = {
      id: clientId,
      res,
      sessionKey,
      lastEventId: lastEventId ?? 0,
    };

    // 세션별 클라이언트 목록에 추가
    if (!this.clients.has(sessionKey)) {
      this.clients.set(sessionKey, []);
    }
    this.clients.get(sessionKey)!.push(client);
    this.allClients.set(clientId, client);

    // 연결 종료 시 자동 정리
    res.on("close", () => {
      this.removeClient(clientId);
    });

    return clientId;
  }

  /**
   * SSE 클라이언트를 해제합니다.
   */
  removeClient(clientId: string): void {
    const client = this.allClients.get(clientId);
    if (!client) return;

    // 세션별 목록에서 제거
    const sessionClients = this.clients.get(client.sessionKey);
    if (sessionClients) {
      const idx = sessionClients.findIndex((c) => c.id === clientId);
      if (idx !== -1) {
        sessionClients.splice(idx, 1);
      }
      // 빈 세션 정리
      if (sessionClients.length === 0) {
        this.clients.delete(client.sessionKey);
      }
    }

    this.allClients.delete(clientId);

    // Response 종료
    if (!client.res.writableEnded) {
      client.res.end();
    }
  }

  /**
   * 특정 세션의 모든 클라이언트에게 이벤트를 브로드캐스트합니다.
   *
   * @param sessionKey - 세션 키
   * @param eventId - EventStore의 단조증가 ID
   * @param event - Soul SSE 이벤트
   */
  broadcast(
    sessionKey: string,
    eventId: number,
    event: SoulSSEEvent,
  ): void {
    const sessionClients = this.clients.get(sessionKey);
    if (!sessionClients || sessionClients.length === 0) return;

    const eventType = event.type;
    const data = JSON.stringify(event);
    const sseMessage = `id: ${eventId}\nevent: ${eventType}\ndata: ${data}\n\n`;

    // 죽은 연결 수집
    const deadClients: string[] = [];

    for (const client of sessionClients) {
      try {
        if (client.res.writableEnded) {
          deadClients.push(client.id);
          continue;
        }
        client.res.write(sseMessage);
        client.lastEventId = eventId;
      } catch {
        deadClients.push(client.id);
      }
    }

    // 죽은 연결 정리
    for (const deadId of deadClients) {
      this.removeClient(deadId);
    }
  }

  /**
   * 특정 클라이언트에게 이벤트 배열을 순서대로 전송합니다 (재연결 시 미수신 이벤트 전송).
   *
   * @param clientId - 대시보드 클라이언트 ID
   * @param events - 전송할 이벤트 배열
   */
  replayEvents(
    clientId: string,
    events: Array<{ id: number; event: Record<string, unknown> }>,
  ): void {
    const client = this.allClients.get(clientId);
    if (!client || client.res.writableEnded) return;

    for (const record of events) {
      const eventType = (record.event.type as string) ?? "unknown";
      const data = JSON.stringify(record.event);
      const sseMessage = `id: ${record.id}\nevent: ${eventType}\ndata: ${data}\n\n`;

      try {
        client.res.write(sseMessage);
        client.lastEventId = record.id;
      } catch {
        this.removeClient(clientId);
        return;
      }
    }
  }

  /**
   * Keepalive 코멘트를 모든 연결된 클라이언트에게 전송합니다.
   */
  sendKeepalive(): void {
    const deadClients: string[] = [];

    for (const [clientId, client] of this.allClients) {
      try {
        if (client.res.writableEnded) {
          deadClients.push(clientId);
          continue;
        }
        client.res.write(": keepalive\n\n");
      } catch {
        deadClients.push(clientId);
      }
    }

    for (const deadId of deadClients) {
      this.removeClient(deadId);
    }
  }

  /** 특정 세션의 연결된 클라이언트 수 */
  getClientCount(sessionKey: string): number {
    return this.clients.get(sessionKey)?.length ?? 0;
  }

  /** 전체 연결된 클라이언트 수 */
  getTotalClientCount(): number {
    return this.allClients.size;
  }

  /** 세션별 클라이언트 수 맵 */
  getStats(): Record<string, number> {
    const stats: Record<string, number> = {};
    for (const [key, clients] of this.clients) {
      stats[key] = clients.length;
    }
    return stats;
  }

  /**
   * 모든 SSE 클라이언트 연결을 종료합니다.
   * 서버 셧다운 시 호출합니다.
   */
  closeAll(): void {
    for (const [clientId] of this.allClients) {
      this.removeClient(clientId);
    }
  }
}
