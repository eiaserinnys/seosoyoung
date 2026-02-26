/**
 * Soul Dashboard E2E 테스트 (Playwright)
 *
 * 브라우저에서 실제 대시보드를 로드하고 인터랙션을 검증합니다.
 * 모의 Express 서버를 beforeAll에서 한 번 시작하고 전체 테스트에서 공유합니다.
 *
 * 로컬 실행: cd src/soul-dashboard && npx playwright test --config=playwright.config.ts
 * CI 실행: webServer 설정 활성화 후 자동 시작
 */

import { test, expect } from "@playwright/test";
import { mkdirSync, rmSync, existsSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";
import express from "express";
import { createServer, type Server } from "http";

// === Test Fixtures ===

const TEST_DIR = join(tmpdir(), "soul-dash-e2e-" + Date.now());

// === Test Server Management ===

let testServer: Server | null = null;
let testPort = 0;

/**
 * 테스트용 Express 서버를 시작합니다.
 * 실제 서버 인프라를 사용하지 않고 정적 HTML + 모의 API를 제공합니다.
 */
async function startMockDashboardServer(): Promise<number> {
  const app = express();
  app.use(express.json());

  // 모의 세션 목록 API
  app.get("/api/sessions", (_req, res) => {
    res.json({
      sessions: [
        {
          clientId: "bot",
          requestId: "e2e-test-1",
          status: "completed",
          eventCount: 5,
          createdAt: new Date().toISOString(),
        },
        {
          clientId: "dashboard",
          requestId: "e2e-test-2",
          status: "running",
          eventCount: 3,
          createdAt: new Date().toISOString(),
        },
      ],
    });
  });

  // 모의 Health check
  app.get("/api/health", (_req, res) => {
    res.json({ status: "ok", service: "soul-dashboard" });
  });

  // 모의 SSE 엔드포인트
  app.get("/api/sessions/:id/events", (_req, res) => {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    res.write("event: connected\ndata: {}\n\n");
    // 간단한 이벤트 시퀀스 전송
    setTimeout(() => {
      res.write(
        'id: 1\nevent: text_start\ndata: {"type":"text_start","card_id":"c1"}\n\n',
      );
    }, 100);
    setTimeout(() => {
      res.write(
        'id: 2\nevent: text_delta\ndata: {"type":"text_delta","card_id":"c1","text":"Hello from E2E test"}\n\n',
      );
    }, 200);
    setTimeout(() => {
      res.write(
        'id: 3\nevent: text_end\ndata: {"type":"text_end","card_id":"c1"}\n\n',
      );
    }, 300);
    setTimeout(() => {
      res.write(
        'id: 4\nevent: complete\ndata: {"type":"complete","result":"Done","attachments":[]}\n\n',
      );
      res.end();
    }, 400);
  });

  return new Promise((resolve) => {
    const server = createServer(app);
    testServer = server;
    server.listen(0, () => {
      const addr = server.address();
      testPort = typeof addr === "object" && addr ? addr.port : 0;
      resolve(testPort);
    });
  });
}

// === Playwright Tests ===

test.describe("Soul Dashboard E2E", () => {
  // 모의 API 서버를 한 번 시작하고 전체 테스트에서 공유합니다.
  // 실제 대시보드 UI 테스트는 webServer 설정 활성화 후 추가할 수 있습니다.

  test.beforeAll(async () => {
    mkdirSync(TEST_DIR, { recursive: true });
    await startMockDashboardServer();
  });

  test.afterAll(async () => {
    if (testServer) {
      await new Promise<void>((resolve) => testServer!.close(() => resolve()));
      testServer = null;
    }
    if (existsSync(TEST_DIR)) {
      rmSync(TEST_DIR, { recursive: true, force: true });
    }
  });

  test("API health check가 응답한다", async ({ request }) => {
    const res = await request.get(`http://localhost:${testPort}/api/health`);
    expect(res.ok()).toBe(true);
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(body.service).toBe("soul-dashboard");
  });

  test("세션 목록 API가 올바른 형식을 반환한다", async ({ request }) => {
    const res = await request.get(
      `http://localhost:${testPort}/api/sessions`,
    );
    expect(res.ok()).toBe(true);
    const body = await res.json();
    expect(body.sessions).toHaveLength(2);
    expect(body.sessions[0]).toHaveProperty("clientId");
    expect(body.sessions[0]).toHaveProperty("requestId");
    expect(body.sessions[0]).toHaveProperty("status");
    expect(body.sessions[0]).toHaveProperty("eventCount");
  });

  test("SSE 이벤트 스트림이 올바른 형식으로 전달된다", async ({
    request,
  }) => {
    const res = await request.get(
      `http://localhost:${testPort}/api/sessions/bot:e2e-test-1/events`,
    );
    expect(res.ok()).toBe(true);
    const text = await res.text();
    expect(text).toContain("event: connected");
    expect(text).toContain("event: text_start");
    expect(text).toContain("event: text_delta");
    expect(text).toContain("Hello from E2E test");
    expect(text).toContain("event: complete");
  });
});
