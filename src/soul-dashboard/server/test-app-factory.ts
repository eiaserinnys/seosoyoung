/**
 * 테스트용 Express 앱 팩토리
 *
 * 통합 테스트에서 실제 Express 앱을 생성할 때 사용합니다.
 * express 모듈 해석이 src/ 디렉토리에서 이루어지므로
 * node_modules 경로 문제가 발생하지 않습니다.
 */

import express, { type Express } from "express";
import { createServer, type Server } from "http";
import { SessionStore } from "./session-store.js";
import { EventHub } from "./event-hub.js";
import { SoulClient } from "./soul-client.js";
import { createSessionsRouter } from "./routes/sessions.js";
import { createEventsRouter } from "./routes/events.js";
import { createActionsRouter } from "./routes/actions.js";

export interface TestAppOptions {
  /** JSONL 이벤트 저장 디렉토리 */
  eventsBaseDir: string;
  /** Soul 서버 포트 (기본값: 39999 - 연결 안 됨) */
  soulPort?: number;
}

export interface TestAppContext {
  app: Express;
  sessionStore: SessionStore;
  eventHub: EventHub;
  soulClient: SoulClient;
}

/**
 * 테스트용 Express 앱과 의존성을 생성합니다.
 */
export function createTestApp(options: TestAppOptions): TestAppContext {
  const sessionStore = new SessionStore({ baseDir: options.eventsBaseDir });
  const eventHub = new EventHub();
  const soulBaseUrl = `http://localhost:${options.soulPort ?? 39999}`;
  const soulClient = new SoulClient({ soulBaseUrl });

  const app = express();
  app.use(express.json({ limit: "1mb" }));

  app.get("/api/health", (_req, res) => {
    res.json({
      status: "ok",
      service: "soul-dashboard",
      connectedClients: eventHub.getTotalClientCount(),
      activeSubscriptions: soulClient.getActiveSubscriptions().length,
    });
  });

  app.use("/api/sessions", createSessionsRouter(sessionStore));
  app.use(
    "/api/sessions",
    createEventsRouter({ sessionStore, eventHub, soulClient }),
  );
  app.use(
    "/api/sessions",
    createActionsRouter({ soulBaseUrl }),
  );

  return { app, sessionStore, eventHub, soulClient };
}

/**
 * Express 앱을 랜덤 포트에서 시작합니다.
 */
export function startTestServer(app: Express): Promise<{ server: Server; port: number }> {
  return new Promise((resolve, reject) => {
    const server = createServer(app);
    server.on("error", reject);
    server.listen(0, () => {
      const addr = server.address();
      const port = typeof addr === "object" && addr ? addr.port : 0;
      resolve({ server, port });
    });
  });
}

/**
 * Mock Soul 서버를 생성합니다.
 * /execute와 /tasks/:clientId/:requestId/intervene 엔드포인트를 제공합니다.
 */
export function createMockSoulServer(): Promise<{
  server: Server;
  port: number;
  requests: Array<{ type: string; body: unknown; params?: Record<string, string> }>;
}> {
  return new Promise((resolve) => {
    const requests: Array<{ type: string; body: unknown; params?: Record<string, string> }> = [];
    const soulApp = express();
    soulApp.use(express.json());

    soulApp.post("/execute", (req, res) => {
      requests.push({ type: "execute", body: req.body });

      // SSE 스트림 시뮬레이트 (즉시 종료)
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      });
      res.write(
        'event: progress\ndata: {"type":"progress","text":"Starting..."}\n\n',
      );
      res.end();
    });

    soulApp.post("/tasks/:clientId/:requestId/intervene", (req, res) => {
      requests.push({
        type: "intervene",
        body: req.body,
        params: req.params as Record<string, string>,
      });
      res.json({ status: "queued" });
    });

    const server = createServer(soulApp);
    server.listen(0, () => {
      const addr = server.address();
      const port = typeof addr === "object" && addr ? addr.port : 0;
      resolve({ server, port, requests });
    });
  });
}
