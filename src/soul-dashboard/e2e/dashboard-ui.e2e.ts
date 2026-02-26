/**
 * Soul Dashboard 브라우저 UI E2E 테스트
 *
 * 실제 브라우저에서 대시보드를 렌더링하고 각 단계마다 스크린샷을 캡처합니다.
 * 빌드된 클라이언트(dist/client/)를 Mock Express 서버에서 직접 서빙하며,
 * Mock API 엔드포인트(세션 목록, SSE 이벤트)도 같은 서버에서 제공합니다.
 *
 * 사전 요건: `npx vite build` 실행으로 dist/client/ 생성
 * 실행: cd src/soul-dashboard && npx playwright test dashboard-ui --config=playwright.config.ts
 */

import { test as base, expect, type Page } from "@playwright/test";
import { mkdirSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import express from "express";
import { createServer, type Server } from "http";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// === SSE 이벤트 타이밍 상수 ===

const SSE_INTERVAL = 200;

const SSE_EVENTS = [
  // 0) User message
  {
    delay: 0,
    data: 'id: 0\nevent: user_message\ndata: {"type":"user_message","user":"dashboard","text":"src/index.ts 파일을 분석하고 에러 핸들링을 추가해주세요."}\n\n',
  },
  // 1) Thinking 카드: text_start → text_delta → text_end
  {
    delay: 1 * SSE_INTERVAL,
    data: 'id: 1\nevent: text_start\ndata: {"type":"text_start","card_id":"card-t1"}\n\n',
  },
  {
    delay: 2 * SSE_INTERVAL,
    data: 'id: 2\nevent: text_delta\ndata: {"type":"text_delta","card_id":"card-t1","text":"파일 구조를 분석하겠습니다. src/index.ts를 먼저 확인하고 의존성을 추적합니다."}\n\n',
  },
  {
    delay: 3 * SSE_INTERVAL,
    data: 'id: 3\nevent: text_end\ndata: {"type":"text_end","card_id":"card-t1"}\n\n',
  },
  // 2) Tool 호출: tool_start → tool_result
  {
    delay: 4 * SSE_INTERVAL,
    data: 'id: 4\nevent: tool_start\ndata: {"type":"tool_start","card_id":"card-tool1","tool_name":"Read","tool_input":{"file_path":"/src/index.ts"}}\n\n',
  },
  {
    delay: 6 * SSE_INTERVAL,
    data: 'id: 5\nevent: tool_result\ndata: {"type":"tool_result","card_id":"card-tool1","tool_name":"Read","result":"export function main() {\\n  console.log(\\"hello\\");\\n}","is_error":false}\n\n',
  },
  // 3) 두 번째 Thinking 카드
  {
    delay: 7 * SSE_INTERVAL,
    data: 'id: 6\nevent: text_start\ndata: {"type":"text_start","card_id":"card-t2"}\n\n',
  },
  {
    delay: 8 * SSE_INTERVAL,
    data: 'id: 7\nevent: text_delta\ndata: {"type":"text_delta","card_id":"card-t2","text":"파일을 확인했습니다. main 함수를 수정하여 에러 핸들링을 추가하겠습니다."}\n\n',
  },
  {
    delay: 9 * SSE_INTERVAL,
    data: 'id: 8\nevent: text_end\ndata: {"type":"text_end","card_id":"card-t2"}\n\n',
  },
  // 4) Complete 이벤트
  {
    delay: 11 * SSE_INTERVAL,
    data: 'id: 9\nevent: complete\ndata: {"type":"complete","result":"작업이 완료되었습니다. src/index.ts에 에러 핸들링을 추가했습니다.","attachments":[]}\n\n',
    end: true,
  },
];

// === Mock Dashboard Server Fixture ===

interface MockDashboardServer {
  port: number;
  baseURL: string;
  server: Server;
}

/**
 * 빌드된 클라이언트 + Mock API를 서빙하는 통합 서버.
 * 랜덤 포트 사용으로 포트 충돌을 방지합니다.
 */
const test = base.extend<{ dashboardServer: MockDashboardServer }>({
  dashboardServer: async ({}, use) => {
    const app = express();

    // --- Mock: 세션 목록 ---
    app.get("/api/sessions", (_req, res) => {
      res.json({
        sessions: [
          {
            clientId: "bot",
            requestId: "e2e-ui-001",
            status: "running",
            eventCount: 5,
            createdAt: new Date().toISOString(),
          },
          {
            clientId: "dashboard",
            requestId: "e2e-ui-002",
            status: "completed",
            eventCount: 12,
            createdAt: new Date(Date.now() - 3600000).toISOString(),
          },
          {
            clientId: "bot",
            requestId: "e2e-ui-003",
            status: "error",
            eventCount: 3,
            createdAt: new Date(Date.now() - 7200000).toISOString(),
          },
        ],
      });
    });

    // --- Mock: Health check ---
    app.get("/api/health", (_req, res) => {
      res.json({ status: "ok", service: "soul-dashboard" });
    });

    // --- Mock: SSE 이벤트 스트림 ---
    app.get("/api/sessions/:id/events", (_req, res) => {
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      });

      const timers: NodeJS.Timeout[] = [];

      // 클라이언트 연결 종료 시 타이머 정리 (ERR_STREAM_DESTROYED 방지)
      res.on("close", () => {
        timers.forEach(clearTimeout);
      });

      // 연결 확인
      res.write("event: connected\ndata: {}\n\n");

      // SSE 이벤트 스케줄링
      for (const event of SSE_EVENTS) {
        timers.push(
          setTimeout(() => {
            if (!res.writableEnded) {
              res.write(event.data);
              if (event.end) {
                res.end();
              }
            }
          }, event.delay),
        );
      }
    });

    // --- 빌드된 클라이언트 정적 파일 서빙 ---
    const clientDistDir = path.resolve(__dirname, "../dist/client");
    app.use(express.static(clientDistDir));

    // SPA fallback: API 외 모든 GET 요청에 index.html 반환
    app.get("/{*splat}", (_req, res) => {
      res.sendFile(path.join(clientDistDir, "index.html"));
    });

    // 랜덤 포트에서 서버 시작
    const server = createServer(app);
    const port = await new Promise<number>((resolve, reject) => {
      const onError = (err: Error) => reject(err);
      server.once("error", onError);
      server.listen(0, () => {
        server.removeListener("error", onError);
        const addr = server.address();
        const p = typeof addr === "object" && addr ? addr.port : 0;
        resolve(p);
      });
    });

    const baseURL = `http://localhost:${port}`;

    await use({ port, baseURL, server });

    // 정리: SSE 등 열린 연결을 강제 종료한 후 서버 종료 (타임아웃 가드 포함)
    server.closeAllConnections();
    await Promise.race([
      new Promise<void>((resolve) => server.close(() => resolve())),
      new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
    ]);
  },
});

// === Screenshot 디렉토리 ===

const SCREENSHOT_DIR = path.join(__dirname, "screenshots");

// === Helpers ===

/** 대시보드에 접속하고 세션을 선택하는 공통 설정 */
async function navigateAndSelectSession(
  page: Page,
  baseURL: string,
  sessionKey = "bot:e2e-ui-001",
) {
  await page.goto(baseURL);
  await expect(
    page.locator('[data-testid^="session-item-"]'),
  ).toHaveCount(3, { timeout: 10_000 });
  await page
    .locator(`[data-testid="session-item-${sessionKey}"]`)
    .click();
}

// === Tests ===

test.describe("Soul Dashboard 브라우저 UI", () => {
  test.beforeAll(async () => {
    // 스크린샷 디렉토리 생성
    mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("1. 대시보드 초기 렌더링 + 세션 목록 로드", async ({
    page,
    dashboardServer,
  }) => {
    // Mock 서버로 이동
    await page.goto(dashboardServer.baseURL);

    // 대시보드 레이아웃 확인
    const layout = page.locator('[data-testid="dashboard-layout"]');
    await expect(layout).toBeVisible({ timeout: 15_000 });

    // 헤더에 "Soul Dashboard" 텍스트 확인
    await expect(page.locator("header")).toContainText("Soul Dashboard");

    // 세션 패널 확인
    const sessionPanel = page.locator('[data-testid="session-panel"]');
    await expect(sessionPanel).toBeVisible();

    // 스크린샷: 초기 로딩 상태
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/01-initial-loading.png`,
      fullPage: true,
    });

    // 세션 목록 로드 대기
    const sessionList = page.locator('[data-testid="session-list"]');
    await expect(sessionList).toBeVisible();

    // 세션 항목이 렌더링될 때까지 대기 (mock에서 3개 반환)
    await expect(
      page.locator('[data-testid^="session-item-"]'),
    ).toHaveCount(3, { timeout: 10_000 });

    // 세션 상태 뱃지 확인
    const statusBadges = page.locator('[data-testid="session-status-badge"]');
    await expect(statusBadges).toHaveCount(3);

    // 그래프 패널 확인 (세션 미선택 → "Select a session" 안내)
    const graphPanel = page.locator('[data-testid="graph-panel"]');
    await expect(graphPanel).toBeVisible();

    // 디테일 패널 확인 (노드 미선택 → "Select a node" 안내)
    const detailPanel = page.locator('[data-testid="detail-panel"]');
    await expect(detailPanel).toBeVisible();

    // 스크린샷: 세션 목록 로드 완료
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/02-sessions-loaded.png`,
      fullPage: true,
    });
  });

  test("2. SSE 이벤트 → React Flow 노드 그래프 렌더링", async ({
    page,
    dashboardServer,
  }) => {
    await navigateAndSelectSession(page, dashboardServer.baseURL);

    // SSE 연결 + 이벤트 수신 대기
    // Thinking 노드가 나타날 때까지 대기 (text_start 이벤트 이후)
    const thinkingNodes = page.locator('[data-testid="thinking-node"]');
    await expect(thinkingNodes.first()).toBeVisible({ timeout: 10_000 });

    // 스크린샷: 첫 thinking 노드 렌더링
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/03-first-thinking-node.png`,
      fullPage: true,
    });

    // Tool Call 노드가 나타날 때까지 대기 (tool_start 이벤트 이후)
    const toolNodes = page.locator('[data-testid="tool-call-node"]');
    await expect(toolNodes.first()).toBeVisible({ timeout: 10_000 });

    // 두 번째 thinking 노드도 나타날 때까지 대기
    await expect(thinkingNodes).toHaveCount(2, { timeout: 10_000 });

    // React Flow 캔버스에 노드와 엣지가 렌더링되었는지 확인
    const reactFlowNodes = page.locator(".react-flow__node");
    const nodeCount = await reactFlowNodes.count();
    expect(nodeCount).toBeGreaterThanOrEqual(3); // thinking + tool + thinking

    // 스크린샷: 전체 노드 그래프 렌더링
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/04-node-graph-rendered.png`,
      fullPage: true,
    });
  });

  test("3. 노드 클릭 → Detail 패널 표시", async ({
    page,
    dashboardServer,
  }) => {
    await navigateAndSelectSession(page, dashboardServer.baseURL);

    // 노드들이 렌더링될 때까지 대기
    const thinkingNodes = page.locator('[data-testid="thinking-node"]');
    await expect(thinkingNodes.first()).toBeVisible({ timeout: 10_000 });

    // Tool 노드가 렌더링될 때까지 대기
    const toolNodes = page.locator('[data-testid="tool-call-node"]');
    await expect(toolNodes.first()).toBeVisible({ timeout: 10_000 });

    // Thinking 노드 클릭
    await thinkingNodes.first().click();

    // Detail 패널에 내용이 표시되는지 확인
    const detailView = page.locator('[data-testid="detail-view"]');
    await expect(detailView).toBeVisible();

    // Thinking 카드 상세에서 "Detail" 헤더 확인
    await expect(detailView.getByText("Detail")).toBeVisible();

    // 스크린샷: Thinking 노드 선택 → Detail 패널
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/05-thinking-detail.png`,
      fullPage: true,
    });

    // Tool Call 노드 클릭
    await toolNodes.first().click();

    // Detail 패널이 Tool 상세로 업데이트되는지 확인
    // Tool 상세에는 도구 이름("Read")이 표시되어야 함
    await expect(detailView).toContainText("Read", { timeout: 5_000 });

    // 스크린샷: Tool 노드 선택 → Detail 패널
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/06-tool-detail.png`,
      fullPage: true,
    });
  });

  test("4. Complete 상태 + 레이아웃 검증", async ({ page, dashboardServer }) => {
    await navigateAndSelectSession(page, dashboardServer.baseURL);

    // Complete 이벤트 수신까지 대기 (약 2.2초 후)
    // Complete 이벤트 후 연결 상태가 disconnected("Idle")로 변경됨
    await expect(page.getByText("Idle")).toBeVisible({ timeout: 10_000 });

    // 그래프 재빌드 debounce(100ms) + React 렌더링 대기
    // 전체 노드 그래프가 렌더링된 상태 확인
    const thinkingNodes = page.locator('[data-testid="thinking-node"]');
    await expect(thinkingNodes.first()).toBeVisible({ timeout: 10_000 });

    const toolNodes = page.locator('[data-testid="tool-call-node"]');
    await expect(toolNodes.first()).toBeVisible({ timeout: 10_000 });

    // user 노드 존재 확인 (user_message 이벤트 추가됨)
    const userNodes = page.locator('[data-testid="user-node"]');
    await expect(userNodes.first()).toBeVisible({ timeout: 10_000 });

    // thinking + tool 노드가 모두 존재하는지 확인
    const thinkingCount = await thinkingNodes.count();
    expect(thinkingCount).toBeGreaterThanOrEqual(1);

    // 레이아웃 검증: thinking 노드들이 세로로 정렬되고, tool 노드가 오른쪽에 배치
    const allNodes = page.locator(".react-flow__node");
    const nodeCount = await allNodes.count();
    expect(nodeCount).toBeGreaterThanOrEqual(4); // user + thinking + tool + thinking (or response)

    // 스크린샷: Complete 상태의 전체 대시보드
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/07-complete-state.png`,
      fullPage: true,
    });
  });
});
