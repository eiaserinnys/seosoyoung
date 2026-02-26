/**
 * 통합 테스트: SSE 재연결 및 이벤트 재전송
 *
 * 체크리스트 항목:
 * - [3] 대시보드 재접속 시 미수신 이벤트 재전송 (Last-Event-ID 확인)
 * - [4] 브라우저 알림 동작 확인 (완료/에러/질문 트리거)
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { type Server } from "http";
import { mkdirSync, writeFileSync, rmSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";
import {
  createTestApp,
  startTestServer,
  type TestAppContext,
} from "../../../src/soul-dashboard/server/test-app-factory.js";

const TEST_DIR = join(tmpdir(), "soul-dash-sse-" + Date.now());

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

/** SSE 스트림에서 이벤트를 파싱하여 배열로 반환 */
function parseSSEEvents(raw: string): Array<{ id?: string; event?: string; data?: string }> {
  const events: Array<{ id?: string; event?: string; data?: string }> = [];
  const blocks = raw.split("\n\n").filter((b) => b.trim());

  for (const block of blocks) {
    if (block.startsWith(":")) continue;
    const event: { id?: string; event?: string; data?: string } = {};
    for (const line of block.split("\n")) {
      if (line.startsWith("id: ")) event.id = line.slice(4);
      else if (line.startsWith("event: ")) event.event = line.slice(7);
      else if (line.startsWith("data: ")) event.data = line.slice(6);
    }
    if (event.event || event.data) events.push(event);
  }
  return events;
}

describe("SSE Reconnection & Event Replay", () => {
  let dashServer: Server;
  let dashPort: number;
  let ctx: TestAppContext;

  beforeEach(async () => {
    mkdirSync(TEST_DIR, { recursive: true });
    ctx = createTestApp({ eventsBaseDir: TEST_DIR });
    const started = await startTestServer(ctx.app);
    dashServer = started.server;
    dashPort = started.port;
  });

  afterEach(async () => {
    ctx?.soulClient?.close();
    ctx?.eventHub?.closeAll();
    await new Promise<void>((resolve) => dashServer?.close(() => resolve()));
    rmSync(TEST_DIR, { recursive: true, force: true });
  });

  // === [3] Last-Event-ID 재연결 ===

  describe("[체크리스트 3] 재접속 시 미수신 이벤트 재전송", () => {
    it("Last-Event-ID 없이 연결: 전체 히스토리 재생", async () => {
      createTestJsonl("bot", "full-replay", [
        { id: 1, event: { type: "progress", text: "Step 1" } },
        { id: 2, event: { type: "text_start", card_id: "c1" } },
        { id: 3, event: { type: "text_delta", card_id: "c1", text: "Hello" } },
        { id: 4, event: { type: "text_end", card_id: "c1" } },
        { id: 5, event: { type: "complete", result: "Done", attachments: [] } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:full-replay/events`,
      );

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let collected = "";

      const timeout = setTimeout(() => reader.cancel(), 2000);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          collected += decoder.decode(value, { stream: true });
          if (collected.includes('"complete"')) break;
        }
      } catch { /* cancelled */ }
      clearTimeout(timeout);

      const events = parseSSEEvents(collected);
      const connected = events.filter((e) => e.event === "connected");
      expect(connected).toHaveLength(1);

      const dataEvents = events.filter((e) => e.event !== "connected");
      // 합성 user_message(id:0) + 원본 5개 = 6개
      expect(dataEvents.length).toBe(6);
      expect(dataEvents[0].id).toBe("0");
      expect(dataEvents[0].event).toBe("user_message");
      expect(dataEvents[1].id).toBe("1");
      expect(dataEvents[5].id).toBe("5");
    });

    it("Last-Event-ID=3 으로 재연결: ID 4, 5만 재전송", async () => {
      createTestJsonl("bot", "partial-replay", [
        { id: 1, event: { type: "progress", text: "Step 1" } },
        { id: 2, event: { type: "text_start", card_id: "c1" } },
        { id: 3, event: { type: "text_delta", card_id: "c1", text: "Hello" } },
        { id: 4, event: { type: "text_end", card_id: "c1" } },
        { id: 5, event: { type: "complete", result: "Done", attachments: [] } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:partial-replay/events`,
        { headers: { "Last-Event-ID": "3" } },
      );

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let collected = "";

      const timeout = setTimeout(() => reader.cancel(), 2000);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          collected += decoder.decode(value, { stream: true });
          if (collected.includes('"complete"')) break;
        }
      } catch { /* cancelled */ }
      clearTimeout(timeout);

      const events = parseSSEEvents(collected);
      const dataEvents = events.filter((e) => e.event !== "connected");

      expect(dataEvents.length).toBe(2);
      expect(dataEvents[0].id).toBe("4");
      expect(dataEvents[1].id).toBe("5");
    });

    it("Last-Event-ID가 마지막 이벤트 이후: 히스토리 재생 없음", async () => {
      createTestJsonl("bot", "no-replay", [
        { id: 1, event: { type: "progress", text: "Done" } },
        { id: 2, event: { type: "complete", result: "Done", attachments: [] } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:no-replay/events`,
        { headers: { "Last-Event-ID": "99" } },
      );

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let collected = "";

      const timeout = setTimeout(() => reader.cancel(), 500);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          collected += decoder.decode(value, { stream: true });
        }
      } catch { /* cancelled */ }
      clearTimeout(timeout);

      const events = parseSSEEvents(collected);
      const dataEvents = events.filter((e) => e.event !== "connected");
      expect(dataEvents.length).toBe(0);
    });
  });

  // === [4] 브라우저 알림 트리거 ===

  describe("[체크리스트 4] 알림 트리거 이벤트 전송 확인", () => {
    it("complete 이벤트가 SSE로 전달됨 (알림 트리거)", async () => {
      createTestJsonl("bot", "notify-complete", [
        { id: 1, event: { type: "progress", text: "Working..." } },
        { id: 2, event: { type: "complete", result: "Task completed successfully", attachments: [] } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:notify-complete/events`,
      );

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let collected = "";

      const timeout = setTimeout(() => reader.cancel(), 2000);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          collected += decoder.decode(value, { stream: true });
          if (collected.includes('"complete"')) break;
        }
      } catch { /* cancelled */ }
      clearTimeout(timeout);

      const events = parseSSEEvents(collected);
      const completeEvent = events.find((e) => e.event === "complete");
      expect(completeEvent).toBeDefined();
      const data = JSON.parse(completeEvent!.data!);
      expect(data.type).toBe("complete");
      expect(data.result).toBe("Task completed successfully");
    });

    it("error 이벤트가 SSE로 전달됨 (에러 알림 트리거)", async () => {
      createTestJsonl("bot", "notify-error", [
        { id: 1, event: { type: "progress", text: "Working..." } },
        { id: 2, event: { type: "error", message: "Rate limit exceeded", error_code: "RATE_LIMIT" } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:notify-error/events`,
      );

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let collected = "";

      const timeout = setTimeout(() => reader.cancel(), 2000);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          collected += decoder.decode(value, { stream: true });
          if (collected.includes('"error"')) break;
        }
      } catch { /* cancelled */ }
      clearTimeout(timeout);

      const events = parseSSEEvents(collected);
      const errorEvent = events.find((e) => e.event === "error");
      expect(errorEvent).toBeDefined();
      const data = JSON.parse(errorEvent!.data!);
      expect(data.type).toBe("error");
      expect(data.message).toBe("Rate limit exceeded");
    });

    it("intervention_sent 이벤트가 SSE로 전달됨 (질문/개입 알림)", async () => {
      createTestJsonl("bot", "notify-intervention", [
        { id: 1, event: { type: "progress", text: "Running..." } },
        { id: 2, event: { type: "intervention_sent", user: "admin", text: "Please clarify" } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:notify-intervention/events`,
      );

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let collected = "";

      const timeout = setTimeout(() => reader.cancel(), 2000);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          collected += decoder.decode(value, { stream: true });
          if (collected.includes('"intervention_sent"')) break;
        }
      } catch { /* cancelled */ }
      clearTimeout(timeout);

      const events = parseSSEEvents(collected);
      const interventionEvent = events.find((e) => e.event === "intervention_sent");
      expect(interventionEvent).toBeDefined();
      const data = JSON.parse(interventionEvent!.data!);
      expect(data.type).toBe("intervention_sent");
      expect(data.user).toBe("admin");
    });
  });

  // === 라이브 브로드캐스트 + 히스토리 재생 복합 ===

  describe("라이브 브로드캐스트 + 히스토리 재생 복합", () => {
    it("히스토리 재생 후 라이브 이벤트 수신", async () => {
      createTestJsonl("bot", "live-test", [
        { id: 1, event: { type: "progress", text: "Starting..." } },
        { id: 2, event: { type: "text_start", card_id: "c1" } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:live-test/events`,
      );

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let collected = "";

      // 히스토리 수집 대기
      await new Promise((resolve) => setTimeout(resolve, 200));

      // 라이브 이벤트 브로드캐스트
      ctx.eventHub.broadcast("bot:live-test", 3, {
        type: "text_delta",
        card_id: "c1",
        text: "Live data!",
      });

      await new Promise((resolve) => setTimeout(resolve, 200));

      const timeout = setTimeout(() => reader.cancel(), 500);
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          collected += decoder.decode(value, { stream: true });
        }
      } catch { /* cancelled */ }
      clearTimeout(timeout);

      expect(collected).toContain("id: 1");
      expect(collected).toContain("id: 2");
      expect(collected).toContain("id: 3");
      expect(collected).toContain("Live data!");
    });
  });
});
