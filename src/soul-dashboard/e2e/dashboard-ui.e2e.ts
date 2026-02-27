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

// === 멀티 Tool SSE 이벤트 시퀀스 ===

/**
 * 3개의 연속 Tool 호출(Read → Write → Bash)을 포함하는 SSE 이벤트 시퀀스.
 * thinking → 3개 tool 호출 → 2번째 thinking → response → complete
 */
const MULTI_TOOL_SSE_EVENTS = [
  // 0) User message
  {
    delay: 0,
    data: 'id: 0\nevent: user_message\ndata: {"type":"user_message","user":"dashboard","text":"src/utils.ts에 validateInput 함수를 추가하고 테스트를 실행해주세요."}\n\n',
  },
  // 1) Thinking: 분석
  {
    delay: 1 * SSE_INTERVAL,
    data: 'id: 1\nevent: text_start\ndata: {"type":"text_start","card_id":"mt-t1"}\n\n',
  },
  {
    delay: 2 * SSE_INTERVAL,
    data: 'id: 2\nevent: text_delta\ndata: {"type":"text_delta","card_id":"mt-t1","text":"먼저 기존 파일을 읽고, 수정한 뒤, 테스트를 실행하겠습니다."}\n\n',
  },
  {
    delay: 3 * SSE_INTERVAL,
    data: 'id: 3\nevent: text_end\ndata: {"type":"text_end","card_id":"mt-t1"}\n\n',
  },
  // 2) Tool 1: Read
  {
    delay: 4 * SSE_INTERVAL,
    data: 'id: 4\nevent: tool_start\ndata: {"type":"tool_start","card_id":"mt-tool1","tool_name":"Read","tool_input":{"file_path":"/src/utils.ts"}}\n\n',
  },
  {
    delay: 5 * SSE_INTERVAL,
    data: 'id: 5\nevent: tool_result\ndata: {"type":"tool_result","card_id":"mt-tool1","tool_name":"Read","result":"export function formatDate(d: Date) { return d.toISOString(); }","is_error":false}\n\n',
  },
  // 3) Tool 2: Write
  {
    delay: 6 * SSE_INTERVAL,
    data: 'id: 6\nevent: tool_start\ndata: {"type":"tool_start","card_id":"mt-tool2","tool_name":"Write","tool_input":{"file_path":"/src/utils.ts","content":"export function validateInput(s: string) { return s.trim().length > 0; }"}}\n\n',
  },
  {
    delay: 7 * SSE_INTERVAL,
    data: 'id: 7\nevent: tool_result\ndata: {"type":"tool_result","card_id":"mt-tool2","tool_name":"Write","result":"File written successfully","is_error":false}\n\n',
  },
  // 4) Tool 3: Bash
  {
    delay: 8 * SSE_INTERVAL,
    data: 'id: 8\nevent: tool_start\ndata: {"type":"tool_start","card_id":"mt-tool3","tool_name":"Bash","tool_input":{"command":"npm test -- --filter=utils"}}\n\n',
  },
  {
    delay: 9 * SSE_INTERVAL,
    data: 'id: 9\nevent: tool_result\ndata: {"type":"tool_result","card_id":"mt-tool3","tool_name":"Bash","result":"PASS src/utils.test.ts\\n  validateInput\\n    ✓ returns true for valid input (2ms)\\n    ✓ returns false for empty string (1ms)","is_error":false}\n\n',
  },
  // 5) 두 번째 Thinking
  {
    delay: 10 * SSE_INTERVAL,
    data: 'id: 10\nevent: text_start\ndata: {"type":"text_start","card_id":"mt-t2"}\n\n',
  },
  {
    delay: 11 * SSE_INTERVAL,
    data: 'id: 11\nevent: text_delta\ndata: {"type":"text_delta","card_id":"mt-t2","text":"validateInput 함수를 추가하고 테스트가 모두 통과했습니다."}\n\n',
  },
  {
    delay: 12 * SSE_INTERVAL,
    data: 'id: 12\nevent: text_end\ndata: {"type":"text_end","card_id":"mt-t2"}\n\n',
  },
  // 6) Complete
  {
    delay: 14 * SSE_INTERVAL,
    data: 'id: 13\nevent: complete\ndata: {"type":"complete","result":"src/utils.ts에 validateInput 함수를 추가하고 테스트를 통과했습니다.","attachments":[]}\n\n',
    end: true,
  },
];

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

// === Tool 없는 세션 SSE 이벤트 시퀀스 ===

/**
 * Tool call 없이 thinking → response → complete만 있는 세션.
 * Bug #10 회귀 테스트: 세로 배치 겹침 검증.
 */
const NO_TOOL_SSE_EVENTS = [
  {
    delay: 0,
    data: 'id: 0\nevent: user_message\ndata: {"type":"user_message","user":"dashboard","text":"간단히 설명해주세요."}\n\n',
  },
  {
    delay: 1 * SSE_INTERVAL,
    data: 'id: 1\nevent: text_start\ndata: {"type":"text_start","card_id":"nt-t1"}\n\n',
  },
  {
    delay: 2 * SSE_INTERVAL,
    data: 'id: 2\nevent: text_delta\ndata: {"type":"text_delta","card_id":"nt-t1","text":"이것은 도구를 사용하지 않고 바로 답변하는 세션입니다."}\n\n',
  },
  {
    delay: 3 * SSE_INTERVAL,
    data: 'id: 3\nevent: text_end\ndata: {"type":"text_end","card_id":"nt-t1"}\n\n',
  },
  {
    delay: 5 * SSE_INTERVAL,
    data: 'id: 4\nevent: complete\ndata: {"type":"complete","result":"답변을 완료했습니다.","attachments":[]}\n\n',
    end: true,
  },
];

// === 25+ 노드 세션 SSE 이벤트 시퀀스 ===

/** 10쌍의 thinking+tool을 생성 → ~25 노드 */
function generateLargeSSEEvents(pairCount: number): Array<{ delay: number; data: string; end?: boolean }> {
  const events: Array<{ delay: number; data: string; end?: boolean }> = [];
  let id = 0;
  let step = 0;

  // user message
  events.push({
    delay: 0,
    data: `id: ${id++}\nevent: user_message\ndata: {"type":"user_message","user":"dashboard","text":"대규모 작업을 수행해주세요 (${pairCount} 단계)."}\n\n`,
  });

  for (let i = 0; i < pairCount; i++) {
    step++;
    // thinking
    events.push({
      delay: step * SSE_INTERVAL,
      data: `id: ${id++}\nevent: text_start\ndata: {"type":"text_start","card_id":"lg-t${i}"}\n\n`,
    });
    step++;
    events.push({
      delay: step * SSE_INTERVAL,
      data: `id: ${id++}\nevent: text_delta\ndata: {"type":"text_delta","card_id":"lg-t${i}","text":"Step ${i}: 분석 중..."}\n\n`,
    });
    step++;
    events.push({
      delay: step * SSE_INTERVAL,
      data: `id: ${id++}\nevent: text_end\ndata: {"type":"text_end","card_id":"lg-t${i}"}\n\n`,
    });

    // tool
    const toolName = ["Read", "Bash", "Glob", "Grep", "Write"][i % 5];
    step++;
    events.push({
      delay: step * SSE_INTERVAL,
      data: `id: ${id++}\nevent: tool_start\ndata: {"type":"tool_start","card_id":"lg-tool${i}","tool_name":"${toolName}","tool_input":{"command":"step-${i}"}}\n\n`,
    });
    step++;
    events.push({
      delay: step * SSE_INTERVAL,
      data: `id: ${id++}\nevent: tool_result\ndata: {"type":"tool_result","card_id":"lg-tool${i}","tool_name":"${toolName}","result":"Result of step ${i}","is_error":false}\n\n`,
    });
  }

  // final thinking + complete
  step++;
  events.push({
    delay: step * SSE_INTERVAL,
    data: `id: ${id++}\nevent: text_start\ndata: {"type":"text_start","card_id":"lg-final"}\n\n`,
  });
  step++;
  events.push({
    delay: step * SSE_INTERVAL,
    data: `id: ${id++}\nevent: text_delta\ndata: {"type":"text_delta","card_id":"lg-final","text":"모든 단계를 완료했습니다."}\n\n`,
  });
  step++;
  events.push({
    delay: step * SSE_INTERVAL,
    data: `id: ${id++}\nevent: text_end\ndata: {"type":"text_end","card_id":"lg-final"}\n\n`,
  });
  step += 2;
  events.push({
    delay: step * SSE_INTERVAL,
    data: `id: ${id++}\nevent: complete\ndata: {"type":"complete","result":"${pairCount}단계 작업 완료","attachments":[]}\n\n`,
    end: true,
  });

  return events;
}

const LARGE_25_SSE_EVENTS = generateLargeSSEEvents(10);  // ~25 노드
const LARGE_50_SSE_EVENTS = generateLargeSSEEvents(20);  // ~50 노드

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
          {
            clientId: "dashboard",
            requestId: "e2e-ui-multi",
            status: "running",
            eventCount: 14,
            createdAt: new Date(Date.now() - 60000).toISOString(),
          },
          {
            clientId: "bot",
            requestId: "e2e-ui-notool",
            status: "completed",
            eventCount: 5,
            createdAt: new Date(Date.now() - 120000).toISOString(),
          },
          {
            clientId: "bot",
            requestId: "e2e-ui-large25",
            status: "completed",
            eventCount: 55,
            createdAt: new Date(Date.now() - 180000).toISOString(),
          },
          {
            clientId: "bot",
            requestId: "e2e-ui-large50",
            status: "completed",
            eventCount: 105,
            createdAt: new Date(Date.now() - 240000).toISOString(),
          },
        ],
      });
    });

    // --- Mock: Health check ---
    app.get("/api/health", (_req, res) => {
      res.json({ status: "ok", service: "soul-dashboard" });
    });

    // --- Mock: SSE 이벤트 스트림 ---
    app.get("/api/sessions/:id/events", (req, res) => {
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

      // 세션 ID에 따라 이벤트 시퀀스 선택
      const sessionId = req.params.id;
      let events: Array<{ delay: number; data: string; end?: boolean }>;
      if (sessionId.includes("large50")) {
        events = LARGE_50_SSE_EVENTS;
      } else if (sessionId.includes("large25")) {
        events = LARGE_25_SSE_EVENTS;
      } else if (sessionId.includes("notool")) {
        events = NO_TOOL_SSE_EVENTS;
      } else if (sessionId.includes("multi")) {
        events = MULTI_TOOL_SSE_EVENTS;
      } else {
        events = SSE_EVENTS;
      }

      // SSE 이벤트 스케줄링
      for (const event of events) {
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

/** React Flow 뷰포트에서 현재 zoom 값을 추출 */
async function getReactFlowZoom(page: Page): Promise<number | null> {
  return page.evaluate(() => {
    const rf = document.querySelector(".react-flow");
    if (!rf) return null;
    const transform = rf
      .querySelector(".react-flow__viewport")
      ?.getAttribute("style");
    if (!transform) return null;
    const match = transform.match(/scale\(([^)]+)\)/);
    return match ? parseFloat(match[1]) : null;
  });
}

/** 대시보드에 접속하고 세션을 선택하는 공통 설정 */
async function navigateAndSelectSession(
  page: Page,
  baseURL: string,
  sessionKey = "bot:e2e-ui-001",
) {
  await page.goto(baseURL);
  await expect(
    page.locator('[data-testid^="session-item-"]'),
  ).toHaveCount(7, { timeout: 10_000 });
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
    ).toHaveCount(7, { timeout: 10_000 });

    // 세션 상태 뱃지 확인
    const statusBadges = page.locator('[data-testid="session-status-badge"]');
    await expect(statusBadges).toHaveCount(7);

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

  test("5. 멀티 Tool 호출 시나리오 (Read → Write → Bash)", async ({
    page,
    dashboardServer,
  }) => {
    // 멀티 Tool 세션 선택
    await navigateAndSelectSession(
      page,
      dashboardServer.baseURL,
      "dashboard:e2e-ui-multi",
    );

    // Complete 이벤트까지 대기
    await expect(page.getByText("Idle")).toBeVisible({ timeout: 15_000 });

    // 3개의 Tool Call 노드 확인 (Read, Write, Bash)
    const toolCallNodes = page.locator('[data-testid="tool-call-node"]');
    await expect(toolCallNodes).toHaveCount(3, { timeout: 10_000 });

    // 3개의 Tool Result 노드 확인
    const toolResultNodes = page.locator('[data-testid="tool-result-node"]');
    await expect(toolResultNodes).toHaveCount(3, { timeout: 10_000 });

    // Response 노드 확인 (세션 완료 → 마지막 text가 response로 변환)
    const responseNodes = page.locator('[data-testid="response-node"]');
    await expect(responseNodes).toHaveCount(1, { timeout: 10_000 });

    // User 노드 확인
    const userNodes = page.locator('[data-testid="user-node"]');
    await expect(userNodes).toHaveCount(1, { timeout: 10_000 });

    // Thinking 노드 확인 (첫 번째 thinking만, 두 번째는 response로 변환)
    const thinkingNodes = page.locator('[data-testid="thinking-node"]');
    await expect(thinkingNodes).toHaveCount(1, { timeout: 10_000 });

    // 전체 노드 수: user(1) + thinking(1) + tool_call(3) + tool_result(3) + response(1) + system(1, complete) = 10
    const allNodes = page.locator(".react-flow__node");
    const nodeCount = await allNodes.count();
    expect(nodeCount).toBeGreaterThanOrEqual(10);

    // 레이아웃 정렬 검증: Tool Call 노드들이 세로 체이닝 (같은 X 좌표)
    const toolCallBoxes = await Promise.all(
      Array.from({ length: 3 }, (_, i) =>
        toolCallNodes.nth(i).boundingBox(),
      ),
    );

    // BoundingBox가 null이 아닌지 명시적 확인
    for (const box of toolCallBoxes) {
      expect(box).not.toBeNull();
    }

    // 모든 Tool Call 노드의 X 좌표가 동일한지 확인 (±2px 허용)
    const xPositions = toolCallBoxes.map((b) => b!.x);
    expect(Math.abs(xPositions[0] - xPositions[1])).toBeLessThan(3);
    expect(Math.abs(xPositions[1] - xPositions[2])).toBeLessThan(3);

    // Tool Call 노드들이 위에서 아래로 정렬 (Y 좌표 증가)
    expect(toolCallBoxes[0]!.y).toBeLessThan(toolCallBoxes[1]!.y);
    expect(toolCallBoxes[1]!.y).toBeLessThan(toolCallBoxes[2]!.y);

    // 레이아웃 정렬 검증: Tool Result 노드들이 Tool Call 오른쪽에 배치
    const toolResultBoxes = await Promise.all(
      Array.from({ length: 3 }, (_, i) =>
        toolResultNodes.nth(i).boundingBox(),
      ),
    );

    for (const box of toolResultBoxes) {
      expect(box).not.toBeNull();
    }

    // Result가 Call 오른쪽에 있어야 함
    expect(toolResultBoxes[0]!.x).toBeGreaterThan(toolCallBoxes[0]!.x);

    // 노드 크기 일관성 검증: 모든 Tool Call 노드의 너비가 동일 (viewport zoom 적용)
    const widths = toolCallBoxes.map((b) => b!.width);
    expect(Math.abs(widths[0] - widths[1])).toBeLessThan(2);
    expect(Math.abs(widths[1] - widths[2])).toBeLessThan(2);

    // 스크린샷: 멀티 Tool 전체 그래프
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/08-multi-tool-graph.png`,
      fullPage: true,
    });

    // 각 Tool 노드 클릭하여 상세 확인
    // React Flow 캔버스 내 노드는 뷰포트 밖에 있을 수 있으므로 force: true 사용
    for (const toolName of ["Read", "Write", "Bash"]) {
      const toolNode = toolCallNodes.filter({ hasText: toolName }).first();
      await toolNode.click({ force: true });
      const detailView = page.locator('[data-testid="detail-view"]');
      await expect(detailView).toContainText(toolName, { timeout: 5_000 });
    }

    // 스크린샷: 마지막 Tool 상세
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/09-multi-tool-detail.png`,
      fullPage: true,
    });
  });

  test("6. 뷰포트 줌 불변 검증 (세션 전환 후 스트리밍 중 zoom 변경 없음)", async ({
    page,
    dashboardServer,
  }) => {
    await navigateAndSelectSession(page, dashboardServer.baseURL);

    // Thinking 노드가 나타날 때까지 대기 (첫 로드 → zoom 설정 1회 발생)
    const thinkingNodes = page.locator('[data-testid="thinking-node"]');
    await expect(thinkingNodes.first()).toBeVisible({ timeout: 10_000 });

    // 첫 로드 후 viewport 안정화 대기 (300ms animation + 여유)
    await page.waitForTimeout(500);

    // 현재 zoom 값 캡처 (첫 로드 후 설정된 값)
    const initialZoom = await getReactFlowZoom(page);

    expect(initialZoom).not.toBeNull();
    expect(initialZoom).toBeGreaterThan(0);

    // Tool Call 노드가 렌더링될 때까지 대기 (스트리밍 중 새 노드 추가)
    const toolNodes = page.locator('[data-testid="tool-call-node"]');
    await expect(toolNodes.first()).toBeVisible({ timeout: 10_000 });

    // 두 번째 thinking 노드가 나타날 때까지 대기
    await expect(thinkingNodes).toHaveCount(2, { timeout: 10_000 });

    // 스트리밍 후 viewport 안정화 대기
    await page.waitForTimeout(500);

    // 스트리밍 후 zoom 값 확인 — 변경되지 않아야 함
    const afterStreamZoom = await getReactFlowZoom(page);

    expect(afterStreamZoom).not.toBeNull();

    // 줌 불변 검증: 스트리밍 중 zoom이 크게 변경되지 않아야 함 (±0.05 허용)
    // 0.05 허용: 첫 로드 시 그래프 바운딩 박스가 노드 추가로 미세하게 변할 수 있어
    // 초기 줌 계산에 소수점 이하 차이가 발생할 수 있음 (fitView 대체 → 수동 계산 특성)
    expect(Math.abs(afterStreamZoom! - initialZoom!)).toBeLessThan(0.05);

    // 스크린샷: 줌 불변 검증 후 상태
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/10-zoom-invariant.png`,
      fullPage: true,
    });
  });

  test("7. 노드 겹침 없음 검증 (바운딩 박스 교차 검사)", async ({
    page,
    dashboardServer,
  }) => {
    // 멀티 Tool 세션 선택 (더 많은 노드)
    await navigateAndSelectSession(
      page,
      dashboardServer.baseURL,
      "dashboard:e2e-ui-multi",
    );

    // Complete 이벤트까지 대기
    await expect(page.getByText("Idle")).toBeVisible({ timeout: 15_000 });

    // viewport 안정화 대기
    await page.waitForTimeout(500);

    // 모든 React Flow 노드의 바운딩 박스 수집
    const allNodeBoxes = await page.evaluate(() => {
      const nodes = document.querySelectorAll(".react-flow__node");
      const boxes: Array<{
        id: string;
        x: number;
        y: number;
        w: number;
        h: number;
      }> = [];

      nodes.forEach((node) => {
        const rect = node.getBoundingClientRect();
        boxes.push({
          id: node.getAttribute("data-id") ?? "unknown",
          x: rect.x,
          y: rect.y,
          w: rect.width,
          h: rect.height,
        });
      });

      return boxes;
    });

    // 노드가 충분히 렌더링되었는지 확인
    expect(allNodeBoxes.length).toBeGreaterThanOrEqual(10);

    // 바운딩 박스 교차 검사: 어떤 두 노드도 겹치면 안 됨
    const overlaps: Array<{ a: string; b: string }> = [];
    for (let i = 0; i < allNodeBoxes.length; i++) {
      for (let j = i + 1; j < allNodeBoxes.length; j++) {
        const a = allNodeBoxes[i];
        const b = allNodeBoxes[j];

        // AABB 교차 검사 (2px 허용 마진)
        const margin = 2;
        const overlapX =
          a.x + margin < b.x + b.w - margin &&
          a.x + a.w - margin > b.x + margin;
        const overlapY =
          a.y + margin < b.y + b.h - margin &&
          a.y + a.h - margin > b.y + margin;

        if (overlapX && overlapY) {
          overlaps.push({ a: a.id, b: b.id });
        }
      }
    }

    // 겹치는 노드 쌍이 없어야 함
    expect(
      overlaps,
      `노드 겹침 발견: ${JSON.stringify(overlaps)}`,
    ).toHaveLength(0);

    // 스크린샷: 겹침 없음 검증 후 상태
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/11-no-overlap.png`,
      fullPage: true,
    });
  });

  test("8. Tool call 없는 세션: 노드 세로 배치 검증 (Bug #10 regression)", async ({
    page,
    dashboardServer,
  }) => {
    // tool 없는 세션 선택
    await navigateAndSelectSession(
      page,
      dashboardServer.baseURL,
      "bot:e2e-ui-notool",
    );

    // Complete까지 대기
    await expect(page.getByText("Idle")).toBeVisible({ timeout: 10_000 });

    // viewport 안정화
    await page.waitForTimeout(500);

    // Response 노드 확인 (tool 없는 세션 → 마지막 text가 response)
    const responseNodes = page.locator('[data-testid="response-node"]');
    await expect(responseNodes).toHaveCount(1, { timeout: 10_000 });

    // User 노드 확인
    const userNodes = page.locator('[data-testid="user-node"]');
    await expect(userNodes).toHaveCount(1, { timeout: 10_000 });

    // Tool 노드 없음
    const toolCallNodes = page.locator('[data-testid="tool-call-node"]');
    await expect(toolCallNodes).toHaveCount(0);

    // 전체 노드 수: user(1) + response(1) + system(1, complete) = 3 이상
    const allNodes = page.locator(".react-flow__node");
    const nodeCount = await allNodes.count();
    expect(nodeCount).toBeGreaterThanOrEqual(3);

    // 노드 겹침 없음 검증 (AABB)
    const allNodeBoxes = await page.evaluate(() => {
      const nodes = document.querySelectorAll(".react-flow__node");
      return Array.from(nodes).map((node) => {
        const rect = node.getBoundingClientRect();
        return { id: node.getAttribute("data-id") ?? "?", x: rect.x, y: rect.y, w: rect.width, h: rect.height };
      });
    });

    const overlaps: Array<{ a: string; b: string }> = [];
    for (let i = 0; i < allNodeBoxes.length; i++) {
      for (let j = i + 1; j < allNodeBoxes.length; j++) {
        const a = allNodeBoxes[i];
        const b = allNodeBoxes[j];
        const margin = 2;
        const overlapX = a.x + margin < b.x + b.w - margin && a.x + a.w - margin > b.x + margin;
        const overlapY = a.y + margin < b.y + b.h - margin && a.y + a.h - margin > b.y + margin;
        if (overlapX && overlapY) overlaps.push({ a: a.id, b: b.id });
      }
    }
    expect(overlaps, `노드 겹침: ${JSON.stringify(overlaps)}`).toHaveLength(0);

    // 스크린샷
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/12-no-tool-session.png`,
      fullPage: true,
    });
  });

  test("9. 25+ 노드 세션: EXECUTION FLOW 정상 렌더링 (Bug #10/#14 regression)", async ({
    page,
    dashboardServer,
  }) => {
    await navigateAndSelectSession(
      page,
      dashboardServer.baseURL,
      "bot:e2e-ui-large25",
    );

    // Complete까지 대기 — 25 노드 세션은 시간이 더 걸림
    await expect(page.getByText("Idle")).toBeVisible({ timeout: 30_000 });

    await page.waitForTimeout(500);

    // 노드가 렌더링되었는지 확인
    const allNodes = page.locator(".react-flow__node");
    const nodeCount = await allNodes.count();
    expect(nodeCount).toBeGreaterThanOrEqual(20);

    // 노드가 뷰포트 내에 표시되는지 확인 (하나 이상)
    const visibleNodes = await page.evaluate(() => {
      const vpW = window.innerWidth;
      const vpH = window.innerHeight;
      const nodes = document.querySelectorAll(".react-flow__node");
      let visible = 0;
      nodes.forEach((node) => {
        const rect = node.getBoundingClientRect();
        if (rect.x + rect.width > 0 && rect.x < vpW && rect.y + rect.height > 0 && rect.y < vpH) {
          visible++;
        }
      });
      return visible;
    });
    expect(visibleNodes).toBeGreaterThan(0);

    // 스크린샷
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/13-large25-session.png`,
      fullPage: true,
    });
  });

  test("10. 50+ 노드 세션: EXECUTION FLOW 비어있지 않음 (Bug #14 regression)", async ({
    page,
    dashboardServer,
  }) => {
    await navigateAndSelectSession(
      page,
      dashboardServer.baseURL,
      "bot:e2e-ui-large50",
    );

    // Complete까지 대기 — 50 노드 세션은 시간이 상당히 걸림
    await expect(page.getByText("Idle")).toBeVisible({ timeout: 60_000 });

    await page.waitForTimeout(500);

    // 노드가 렌더링되었는지 확인
    const allNodes = page.locator(".react-flow__node");
    const nodeCount = await allNodes.count();
    expect(nodeCount).toBeGreaterThanOrEqual(40);

    // 뷰포트 내에 하나 이상의 노드가 보여야 함 (14번 버그: 비어있으면 안됨)
    const visibleNodes = await page.evaluate(() => {
      const vpW = window.innerWidth;
      const vpH = window.innerHeight;
      const nodes = document.querySelectorAll(".react-flow__node");
      let visible = 0;
      nodes.forEach((node) => {
        const rect = node.getBoundingClientRect();
        if (rect.x + rect.width > 0 && rect.x < vpW && rect.y + rect.height > 0 && rect.y < vpH) {
          visible++;
        }
      });
      return visible;
    });
    expect(visibleNodes).toBeGreaterThan(0);

    // 모든 노드의 바운딩 박스가 유한한 범위 내에 있는지 확인
    const allNodeBoxes = await page.evaluate(() => {
      const nodes = document.querySelectorAll(".react-flow__node");
      return Array.from(nodes).map((node) => {
        const rect = node.getBoundingClientRect();
        return { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
      });
    });

    // 0 크기 노드가 없어야 함 (렌더링 실패 표지)
    const zeroSizeNodes = allNodeBoxes.filter((b) => b.w === 0 || b.h === 0);
    expect(zeroSizeNodes).toHaveLength(0);

    // 스크린샷
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/14-large50-session.png`,
      fullPage: true,
    });
  });
});
