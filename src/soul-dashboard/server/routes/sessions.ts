/**
 * Sessions Routes - 세션 목록 및 상세 조회 API
 *
 * GET /api/sessions         - 전체 세션 목록
 * GET /api/sessions/:id     - 특정 세션 상세 정보
 */

import { Router } from "express";
import type { SessionStore } from "../session-store.js";
import type { SessionDetail, SessionSummary } from "../../shared/types.js";
import { parseSessionId } from "../utils/parse-session-id.js";

export function createSessionsRouter(sessionStore: SessionStore): Router {
  const router = Router();

  /**
   * GET /api/sessions
   *
   * 저장된 모든 세션의 요약 목록을 반환합니다.
   * JSONL 파일시스템을 스캔하여 세션 메타데이터를 수집합니다.
   */
  router.get("/", async (_req, res) => {
    try {
      const sessions: SessionSummary[] =
        await sessionStore.listSessions();
      res.json({ sessions });
    } catch (err) {
      console.error("[sessions] Failed to list sessions:", err);
      res.status(500).json({
        error: {
          code: "INTERNAL_ERROR",
          message: "Failed to list sessions",
        },
      });
    }
  });

  /**
   * GET /api/sessions/:id
   *
   * 특정 세션의 상세 정보를 반환합니다.
   * :id 형식은 "clientId:requestId" (URL 인코딩 필요).
   *
   * 또는 query param으로 분리: ?clientId=...&requestId=...
   */
  router.get("/:id", async (req, res) => {
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

      const events = await sessionStore.readEvents(clientId, requestId);

      if (events.length === 0) {
        res.status(404).json({
          error: {
            code: "SESSION_NOT_FOUND",
            message: `Session not found: ${clientId}:${requestId}`,
          },
        });
        return;
      }

      // 이벤트에서 세션 메타데이터 추출
      const lastEvent = events[events.length - 1];
      const lastEventType = lastEvent?.event?.type as string | undefined;
      const status = sessionStore.inferStatus(lastEventType);

      // session 이벤트에서 claude_session_id 추출
      let claudeSessionId: string | undefined;
      for (const record of events) {
        if (record.event.type === "session") {
          claudeSessionId = record.event.session_id as string;
        }
      }

      // complete 이벤트에서 result 추출
      let result: string | undefined;
      let error: string | undefined;
      for (const record of events) {
        if (record.event.type === "complete") {
          result = record.event.result as string;
        }
        if (record.event.type === "error") {
          error = record.event.message as string;
        }
      }

      // 첫 progress 이벤트에서 prompt 힌트 추출
      let prompt: string | undefined;
      for (const record of events) {
        if (record.event.type === "progress") {
          prompt = record.event.text as string;
          break;
        }
      }

      const detail: SessionDetail = {
        clientId,
        requestId,
        status,
        eventCount: events.length,
        lastEventType,
        claudeSessionId,
        prompt,
        result,
        error,
        events,
      };

      res.json(detail);
    } catch (err) {
      console.error("[sessions] Failed to get session:", err);
      res.status(500).json({
        error: {
          code: "INTERNAL_ERROR",
          message: "Failed to get session details",
        },
      });
    }
  });

  return router;
}

