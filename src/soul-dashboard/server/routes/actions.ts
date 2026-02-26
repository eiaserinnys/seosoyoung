/**
 * Actions Routes - 세션 생성 및 메시지 전송 API
 *
 * POST /api/sessions                  - 새 세션 생성 (Soul에 실행 요청)
 * POST /api/sessions/:id/message      - 실행 중인 세션에 메시지 전송 (개입)
 */

import { Router } from "express";
import type {
  CreateSessionRequest,
  SendMessageRequest,
  UserMessageEvent,
} from "../../shared/types.js";
import type { EventHub } from "../event-hub.js";
import type { SessionStore } from "../session-store.js";
import { parseSessionId } from "../utils/parse-session-id.js";

const MAX_PROMPT_LENGTH = 100_000;
const MAX_MESSAGE_LENGTH = 50_000;

export interface ActionsRouterOptions {
  /** Soul 서버 기본 URL */
  soulBaseUrl: string;
  /** 인증 토큰 */
  authToken?: string;
  /** EventHub 인스턴스 (user_message 브로드캐스트용) */
  eventHub?: EventHub;
  /** SessionStore 인스턴스 (user_message JSONL persist용) */
  sessionStore?: SessionStore;
}

export function createActionsRouter(options: ActionsRouterOptions): Router {
  const { soulBaseUrl, authToken, eventHub, sessionStore } = options;
  const router = Router();

  /**
   * POST /api/sessions
   *
   * 대시보드에서 새 Claude Code 세션을 시작합니다.
   * Soul 서버의 /execute 엔드포인트에 요청을 프록시합니다.
   *
   * Body:
   * {
   *   prompt: string;
   *   clientId?: string;       // 기본값: "dashboard"
   *   resumeSessionId?: string; // 이전 세션 이어하기
   * }
   */
  router.post("/", async (req, res) => {
    try {
      const body = req.body as CreateSessionRequest;

      if (!body.prompt || typeof body.prompt !== "string") {
        res.status(400).json({
          error: {
            code: "INVALID_REQUEST",
            message: "prompt is required",
          },
        });
        return;
      }

      if (body.prompt.length > MAX_PROMPT_LENGTH) {
        res.status(400).json({
          error: {
            code: "INVALID_REQUEST",
            message: `prompt exceeds maximum length of ${MAX_PROMPT_LENGTH}`,
          },
        });
        return;
      }

      const clientId = body.clientId ?? "dashboard";
      const requestId = generateRequestId();

      // Soul 서버에 실행 요청
      const soulResponse = await fetch(`${soulBaseUrl}/execute`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken
            ? { Authorization: `Bearer ${authToken}` }
            : {}),
        },
        body: JSON.stringify({
          client_id: clientId,
          request_id: requestId,
          prompt: body.prompt,
          resume_session_id: body.resumeSessionId ?? null,
          use_mcp: true,
        }),
      });

      if (!soulResponse.ok) {
        const errorBody = await soulResponse.text();
        console.error(
          `[actions] Soul execute failed (${soulResponse.status}):`,
          errorBody,
        );

        // Soul 에러는 502 Bad Gateway로 변환 (대시보드 자체 에러와 구분)
        res.status(502).json({
          error: {
            code: "SOUL_ERROR",
            message: `Soul server returned ${soulResponse.status}`,
            details: { body: errorBody },
          },
        });
        return;
      }

      // Soul이 SSE 스트림을 반환하지만, 대시보드에서는 세션 정보만 반환
      // 클라이언트는 별도로 /api/sessions/:id/events에 SSE 연결
      if (soulResponse.body) {
        await soulResponse.body.cancel();
      }

      const sessionKey = `${clientId}:${requestId}`;

      // user_message 이벤트 브로드캐스트 + JSONL persist (세션 시작 시 사용자의 원본 프롬프트)
      const userMessageEvent: UserMessageEvent = {
        type: "user_message",
        user: clientId,
        text: body.prompt,
      };

      if (eventHub) {
        eventHub.broadcast(sessionKey, 0, userMessageEvent);
      }

      // JSONL에 user_message를 persist하여 히스토리 리플레이 시에도 사용할 수 있게 함
      if (sessionStore) {
        sessionStore.appendEvent(
          clientId, requestId, 0,
          userMessageEvent as unknown as Record<string, unknown>,
        ).catch((err) => {
          console.warn(`[actions] Failed to persist user_message for ${sessionKey}:`, err);
        });
      }

      res.status(201).json({
        clientId,
        requestId,
        sessionKey,
        status: "running",
      });
    } catch (err) {
      console.error("[actions] Failed to create session:", err);
      res.status(500).json({
        error: {
          code: "INTERNAL_ERROR",
          message: "Failed to create session",
        },
      });
    }
  });

  /**
   * POST /api/sessions/:id/message
   *
   * 실행 중인 세션에 개입 메시지를 전송합니다.
   * Soul 서버의 /tasks/:clientId/:requestId/intervene 엔드포인트에 프록시합니다.
   *
   * Body:
   * {
   *   text: string;
   *   user: string;
   *   attachmentPaths?: string[];
   * }
   */
  router.post("/:id/message", async (req, res) => {
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

      const body = req.body as SendMessageRequest;

      if (!body.text || typeof body.text !== "string") {
        res.status(400).json({
          error: {
            code: "INVALID_REQUEST",
            message: "text is required",
          },
        });
        return;
      }

      if (body.text.length > MAX_MESSAGE_LENGTH) {
        res.status(400).json({
          error: {
            code: "INVALID_REQUEST",
            message: `text exceeds maximum length of ${MAX_MESSAGE_LENGTH}`,
          },
        });
        return;
      }

      if (!body.user || typeof body.user !== "string") {
        res.status(400).json({
          error: {
            code: "INVALID_REQUEST",
            message: "user is required",
          },
        });
        return;
      }

      // Soul 서버에 개입 요청
      const soulResponse = await fetch(
        `${soulBaseUrl}/tasks/${encodeURIComponent(clientId)}/${encodeURIComponent(requestId)}/intervene`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(authToken
              ? { Authorization: `Bearer ${authToken}` }
              : {}),
          },
          body: JSON.stringify({
            text: body.text,
            user: body.user,
            attachment_paths: body.attachmentPaths ?? [],
          }),
        },
      );

      if (!soulResponse.ok) {
        const errorBody = await soulResponse.text();
        console.error(
          `[actions] Soul intervene failed (${soulResponse.status}):`,
          errorBody,
        );

        // Soul 에러는 502 Bad Gateway로 변환
        res.status(502).json({
          error: {
            code: "SOUL_ERROR",
            message: `Soul server returned ${soulResponse.status}`,
            details: { body: errorBody },
          },
        });
        return;
      }

      const result = await soulResponse.json();
      res.json(result);
    } catch (err) {
      console.error("[actions] Failed to send message:", err);
      res.status(500).json({
        error: {
          code: "INTERNAL_ERROR",
          message: "Failed to send message",
        },
      });
    }
  });

  return router;
}

/**
 * 대시보드 요청용 고유 request_id 생성.
 * "dash-" 접두사 + 타임스탬프 + 랜덤 4자리.
 */
function generateRequestId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 6);
  return `dash-${timestamp}-${random}`;
}
