/**
 * 통합 테스트: API 파이프라인
 *
 * 체크리스트 항목:
 * - [1] 슬랙봇에서 요청 → Soul 실행 → 대시보드 실시간 카드 확인
 * - [2] 대시보드에서 새 세션 생성 (origin: dashboard) → Soul 실행 → 결과 확인
 * - [5] 기존 슬랙봇 기능 회귀 테스트 (하위호환 확인)
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { type Server } from "http";
import { mkdirSync, writeFileSync, rmSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";
import {
  createTestApp,
  startTestServer,
  createMockSoulServer,
  type TestAppContext,
} from "../../../src/soul-dashboard/server/test-app-factory.js";

const TEST_DIR = join(tmpdir(), "soul-dash-api-" + Date.now());

function createTestJsonl(
  clientId: string,
  requestId: string,
  events: Array<{ id: number; event: Record<string, unknown> }>,
): void {
  const dir = join(TEST_DIR, clientId);
  mkdirSync(dir, { recursive: true });
  const lines = events.map((e) => JSON.stringify(e)).join("\n") + "\n";
  writeFileSync(join(dir, `${requestId}.jsonl`), lines, "utf-8");
}

describe("API Pipeline Integration", () => {
  let dashServer: Server;
  let dashPort: number;
  let soulServer: Server;
  let soulPort: number;
  let soulRequests: Array<{ type: string; body: unknown; params?: Record<string, string> }>;
  let ctx: TestAppContext;

  beforeEach(async () => {
    mkdirSync(TEST_DIR, { recursive: true });

    const soul = await createMockSoulServer();
    soulServer = soul.server;
    soulPort = soul.port;
    soulRequests = soul.requests;

    ctx = createTestApp({ eventsBaseDir: TEST_DIR, soulPort });
    const started = await startTestServer(ctx.app);
    dashServer = started.server;
    dashPort = started.port;
  });

  afterEach(async () => {
    ctx?.soulClient?.close();
    ctx?.eventHub?.closeAll();
    await new Promise<void>((resolve) => dashServer?.close(() => resolve()));
    await new Promise<void>((resolve) => soulServer?.close(() => resolve()));
    rmSync(TEST_DIR, { recursive: true, force: true });
  });

  // === [5] 기존 슬랙봇 하위호환 ===

  describe("[체크리스트 5] 기존 세션 데이터 호환", () => {
    it("슬랙봇이 생성한 JSONL 세션을 정상 조회", async () => {
      createTestJsonl("bot", "slack-req-001", [
        { id: 1, event: { type: "progress", text: "Processing slack request..." } },
        { id: 2, event: { type: "session", session_id: "claude-sess-abc" } },
        { id: 3, event: { type: "text_start", card_id: "card001" } },
        { id: 4, event: { type: "text_delta", card_id: "card001", text: "Hello from Soul" } },
        { id: 5, event: { type: "text_end", card_id: "card001" } },
        { id: 6, event: { type: "complete", result: "Done", attachments: [] } },
      ]);

      const res = await fetch(`http://localhost:${dashPort}/api/sessions`);
      expect(res.ok).toBe(true);

      const data = await res.json();
      expect(data.sessions).toHaveLength(1);
      expect(data.sessions[0].clientId).toBe("bot");
      expect(data.sessions[0].requestId).toBe("slack-req-001");
      expect(data.sessions[0].status).toBe("completed");
      expect(data.sessions[0].eventCount).toBe(6);
    });

    it("세션 상세 조회: 이벤트 전체와 메타데이터", async () => {
      createTestJsonl("bot", "req-detail", [
        { id: 1, event: { type: "progress", text: "Working..." } },
        { id: 2, event: { type: "session", session_id: "sess-xyz" } },
        { id: 3, event: { type: "complete", result: "Finished", attachments: [] } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:req-detail`,
      );
      expect(res.ok).toBe(true);

      const detail = await res.json();
      expect(detail.clientId).toBe("bot");
      expect(detail.requestId).toBe("req-detail");
      expect(detail.status).toBe("completed");
      expect(detail.claudeSessionId).toBe("sess-xyz");
      expect(detail.events).toHaveLength(3);
    });

    it("여러 클라이언트의 세션이 공존", async () => {
      createTestJsonl("bot", "slack-1", [
        { id: 1, event: { type: "progress", text: "Slack" } },
        { id: 2, event: { type: "complete", result: "OK", attachments: [] } },
      ]);
      createTestJsonl("dashboard", "dash-1", [
        { id: 1, event: { type: "progress", text: "Dashboard" } },
      ]);

      const res = await fetch(`http://localhost:${dashPort}/api/sessions`);
      const data = await res.json();
      expect(data.sessions).toHaveLength(2);

      const clients = data.sessions.map((s: any) => s.clientId).sort();
      expect(clients).toEqual(["bot", "dashboard"]);
    });
  });

  // === [1] 슬랙봇 → Soul → 대시보드 ===

  describe("[체크리스트 1] 슬랙봇 요청 → 대시보드 카드 확인", () => {
    it("JSONL 세션의 이벤트를 SSE로 스트리밍", async () => {
      createTestJsonl("bot", "slack-stream-1", [
        { id: 1, event: { type: "progress", text: "Slack request received" } },
        { id: 2, event: { type: "text_start", card_id: "c1" } },
        { id: 3, event: { type: "text_delta", card_id: "c1", text: "Analyzing..." } },
        { id: 4, event: { type: "text_end", card_id: "c1" } },
        { id: 5, event: { type: "tool_start", card_id: "t1", tool_name: "Read", tool_input: { file_path: "/test.ts" } } },
        { id: 6, event: { type: "tool_result", card_id: "t1", tool_name: "Read", result: "file content", is_error: false } },
        { id: 7, event: { type: "complete", result: "All done", attachments: [] } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:slack-stream-1/events`,
      );
      expect(res.ok).toBe(true);
      expect(res.headers.get("content-type")).toContain("text/event-stream");

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let collected = "";

      const timeout = setTimeout(() => reader.cancel(), 2000);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          collected += decoder.decode(value, { stream: true });
          if (collected.includes("complete")) break;
        }
      } catch { /* reader cancelled */ }
      clearTimeout(timeout);

      expect(collected).toContain("event: connected");
      expect(collected).toContain("event: text_start");
      expect(collected).toContain("event: text_delta");
      expect(collected).toContain("event: tool_start");
      expect(collected).toContain("event: tool_result");
      expect(collected).toContain("event: complete");
      expect(collected).toContain("id: 1");
      expect(collected).toContain("id: 7");
    });
  });

  // === [2] 대시보드에서 세션 생성 ===

  describe("[체크리스트 2] 대시보드에서 세션 생성 → Soul 실행", () => {
    it("POST /api/sessions로 새 세션 생성 요청", async () => {
      const res = await fetch(`http://localhost:${dashPort}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: "Hello, analyze this code" }),
      });

      expect(res.status).toBe(201);
      const data = await res.json();

      expect(data.clientId).toBe("dashboard");
      expect(data.requestId).toBeDefined();
      expect(data.requestId).toMatch(/^dash-/);
      expect(data.sessionKey).toContain("dashboard:");
      expect(data.status).toBe("running");

      expect(soulRequests).toHaveLength(1);
      expect(soulRequests[0].type).toBe("execute");
      expect((soulRequests[0].body as any).prompt).toBe("Hello, analyze this code");
      expect((soulRequests[0].body as any).client_id).toBe("dashboard");
      expect((soulRequests[0].body as any).use_mcp).toBe(true);
    });

    it("커스텀 clientId로 세션 생성", async () => {
      const res = await fetch(`http://localhost:${dashPort}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: "Custom client", clientId: "test-client" }),
      });

      expect(res.status).toBe(201);
      const data = await res.json();
      expect(data.clientId).toBe("test-client");
    });

    it("prompt 없이 세션 생성 시 400 에러", async () => {
      const res = await fetch(`http://localhost:${dashPort}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      expect(res.status).toBe(400);
      const data = await res.json();
      expect(data.error.code).toBe("INVALID_REQUEST");
    });

    it("초대형 prompt 거부 (100K 초과)", async () => {
      const hugePrompt = "A".repeat(100_001);
      const res = await fetch(`http://localhost:${dashPort}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: hugePrompt }),
      });

      expect(res.status).toBe(400);
    });
  });

  // === 인터벤션 ===

  describe("대시보드에서 세션에 메시지 전송", () => {
    it("POST /api/sessions/:id/message로 개입 메시지 전송", async () => {
      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:req-1/message`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: "Please stop and explain", user: "admin" }),
        },
      );

      expect(res.ok).toBe(true);

      expect(soulRequests).toHaveLength(1);
      expect(soulRequests[0].type).toBe("intervene");
      expect((soulRequests[0].body as any).text).toBe("Please stop and explain");
      expect((soulRequests[0].body as any).user).toBe("admin");
      expect(soulRequests[0].params!.clientId).toBe("bot");
      expect(soulRequests[0].params!.requestId).toBe("req-1");
    });

    it("text 없이 메시지 전송 시 400 에러", async () => {
      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:req-1/message`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user: "admin" }),
        },
      );
      expect(res.status).toBe(400);
    });

    it("user 없이 메시지 전송 시 400 에러", async () => {
      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:req-1/message`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: "hello" }),
        },
      );
      expect(res.status).toBe(400);
    });
  });

  // === Health check ===

  describe("Health check", () => {
    it("GET /api/health 정상 응답", async () => {
      const res = await fetch(`http://localhost:${dashPort}/api/health`);
      expect(res.ok).toBe(true);

      const data = await res.json();
      expect(data.status).toBe("ok");
      expect(data.service).toBe("soul-dashboard");
      expect(typeof data.connectedClients).toBe("number");
      expect(typeof data.activeSubscriptions).toBe("number");
    });
  });
});
