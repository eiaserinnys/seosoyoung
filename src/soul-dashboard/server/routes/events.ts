/**
 * Events Routes - SSE 이벤트 스트림 엔드포인트
 *
 * GET /api/sessions/:id/events - SSE 스트림 (세션의 실시간 이벤트)
 *
 * 대시보드 클라이언트가 이 엔드포인트에 연결하면:
 * 1. JSONL에서 기존 이벤트를 재생 (Last-Event-ID 이후)
 * 2. EventHub에 등록하여 라이브 이벤트 수신
 */

import { Router } from "express";
import type { SessionStore } from "../session-store.js";
import type { EventHub } from "../event-hub.js";
import type { SoulClient } from "../soul-client.js";
import { parseSessionId } from "../utils/parse-session-id.js";

export interface EventsRouterDeps {
  sessionStore: SessionStore;
  eventHub: EventHub;
  soulClient: SoulClient;
}

export function createEventsRouter(deps: EventsRouterDeps): Router {
  const { sessionStore, eventHub, soulClient } = deps;
  const router = Router();

  /**
   * GET /api/sessions/:id/events
   *
   * SSE 스트림 엔드포인트.
   * 대시보드 클라이언트가 세션의 실시간 이벤트를 구독합니다.
   *
   * 헤더:
   * - Last-Event-ID: 재연결 시 마지막으로 수신한 이벤트 ID
   *
   * Query:
   * - clientId, requestId: 세션 식별 (또는 :id를 "clientId:requestId"로)
   *
   * 동작:
   * 1. JSONL에서 전체 이벤트를 한 번만 읽음
   * 2. Last-Event-ID 이후의 이벤트를 즉시 전송 (히스토리 재생)
   * 3. EventHub에 등록하여 라이브 이벤트를 실시간 수신
   * 4. SoulClient가 해당 세션을 아직 구독하지 않았으면 자동 구독
   */
  router.get("/:id/events", async (req, res) => {
    try {
      const { clientId, requestId } = parseSessionId(
        req.params.id,
        req.query as Record<string, string>,
      );

      if (!clientId || !requestId) {
        res.status(400).json({
          error: {
            code: "INVALID_SESSION_ID",
            message:
              'Session ID format: "clientId:requestId" or use ?clientId=...&requestId=...',
          },
        });
        return;
      }

      const sessionKey = `${clientId}:${requestId}`;

      // Last-Event-ID 파싱
      const lastEventIdHeader = req.headers["last-event-id"];
      let lastEventId = 0;
      if (typeof lastEventIdHeader === "string") {
        const parsed = parseInt(lastEventIdHeader, 10);
        if (!isNaN(parsed)) {
          lastEventId = parsed;
        }
      }

      // JSONL에서 전체 이벤트를 한 번만 읽기 (이중 읽기 방지)
      let allEvents: Awaited<ReturnType<typeof sessionStore.readEvents>>;
      try {
        allEvents = await sessionStore.readEvents(clientId, requestId);
      } catch (err) {
        console.warn(
          `[events] Failed to read events for ${sessionKey}:`,
          err,
        );
        allEvents = [];
      }

      // EventHub에 클라이언트 등록 (SSE 헤더 설정 포함)
      const dashClientId = eventHub.addClient(
        sessionKey,
        res,
        lastEventId,
      );

      // user_message는 세션 생성 시 actions.ts에서 JSONL에 persist됨.
      // progress.text 기반 합성은 잘못된 텍스트(Claude thinking)를 표시하므로 제거.
      // JSONL에 user_message가 없는 레거시 세션은 user 노드 없이 표시됨.

      // 재생할 이벤트 결정
      const eventsToReplay =
        lastEventId > 0
          ? allEvents.filter((ev) => ev.id > lastEventId)
          : allEvents;

      if (eventsToReplay.length > 0) {
        eventHub.replayEvents(dashClientId, eventsToReplay);
      }

      // SoulClient가 이 세션을 아직 구독하지 않았으면 자동 구독
      const activeSubs = soulClient.getActiveSubscriptions();
      if (!activeSubs.includes(sessionKey)) {
        const lastEvent = allEvents[allEvents.length - 1];
        const lastType = lastEvent?.event?.type as string | undefined;
        const status = sessionStore.inferStatus(lastType);

        if (status === "running") {
          const maxId = allEvents.reduce(
            (max, ev) => Math.max(max, ev.id),
            0,
          );
          soulClient.subscribe(clientId, requestId, maxId);
        }
      }

      // 연결이 끊어질 때 정리는 EventHub.addClient에서 자동 처리됨
    } catch (err) {
      console.error("[events] SSE connection error:", err);
      if (!res.headersSent) {
        res.status(500).json({
          error: {
            code: "INTERNAL_ERROR",
            message: "Failed to establish SSE connection",
          },
        });
      }
    }
  });

  return router;
}
