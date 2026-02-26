/**
 * 통합 테스트: 장시간 세션 + 에러 케이스
 *
 * 체크리스트 항목:
 * - [6] 장시간 세션 (컴팩트 발생) 정상 렌더링
 * - [7] 에러 케이스 (타임아웃, rate limit) 정상 표시
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

const TEST_DIR = join(tmpdir(), "soul-dash-long-" + Date.now());

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

describe("Long Session & Error Cases", () => {
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

  // === [6] 장시간 세션 ===

  describe("[체크리스트 6] 장시간 세션 정상 렌더링", () => {
    it("100개 이상의 이벤트가 포함된 세션을 정상 로드", async () => {
      const events: Array<{ id: number; event: Record<string, unknown> }> = [];
      let id = 1;

      events.push({ id: id++, event: { type: "progress", text: "Starting long session..." } });
      events.push({ id: id++, event: { type: "session", session_id: "long-session-abc" } });

      for (let i = 0; i < 50; i++) {
        const cardId = `text-${i}`;
        events.push({ id: id++, event: { type: "text_start", card_id: cardId } });
        events.push({ id: id++, event: { type: "text_delta", card_id: cardId, text: `Thinking step ${i}...` } });
        events.push({ id: id++, event: { type: "text_end", card_id: cardId } });

        const toolId = `tool-${i}`;
        events.push({ id: id++, event: { type: "tool_start", card_id: toolId, tool_name: "Bash", tool_input: { command: `echo step ${i}` } } });
        events.push({ id: id++, event: { type: "tool_result", card_id: toolId, tool_name: "Bash", result: `step ${i} done`, is_error: false } });
      }

      events.push({ id: id++, event: { type: "complete", result: "Long session completed", attachments: [] } });
      createTestJsonl("bot", "long-session", events);

      const listRes = await fetch(`http://localhost:${dashPort}/api/sessions`);
      const listData = await listRes.json();
      expect(listData.sessions).toHaveLength(1);
      expect(listData.sessions[0].eventCount).toBe(events.length);
      expect(listData.sessions[0].status).toBe("completed");

      const detailRes = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:long-session`,
      );
      expect(detailRes.ok).toBe(true);
      const detail = await detailRes.json();
      expect(detail.events).toHaveLength(events.length);
      expect(detail.claudeSessionId).toBe("long-session-abc");
    });

    it("compact 이벤트가 포함된 세션을 정상 처리", async () => {
      createTestJsonl("bot", "compact-session", [
        { id: 1, event: { type: "progress", text: "Starting..." } },
        { id: 2, event: { type: "session", session_id: "compact-sess" } },
        { id: 3, event: { type: "text_start", card_id: "c1" } },
        { id: 4, event: { type: "text_delta", card_id: "c1", text: "Long analysis..." } },
        { id: 5, event: { type: "text_end", card_id: "c1" } },
        { id: 6, event: { type: "context_usage", used_tokens: 180000, max_tokens: 200000, percent: 90 } },
        { id: 7, event: { type: "compact", trigger: "auto", message: "Context compacted: 180K → 50K tokens" } },
        { id: 8, event: { type: "text_start", card_id: "c2" } },
        { id: 9, event: { type: "text_delta", card_id: "c2", text: "After compaction..." } },
        { id: 10, event: { type: "text_end", card_id: "c2" } },
        { id: 11, event: { type: "complete", result: "Done after compact", attachments: [] } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:compact-session`,
      );
      const detail = await res.json();

      expect(detail.events).toHaveLength(11);
      expect(detail.status).toBe("completed");

      const compactEvent = detail.events.find((e: any) => e.event.type === "compact");
      expect(compactEvent).toBeDefined();
      expect(compactEvent.event.trigger).toBe("auto");

      const contextEvent = detail.events.find((e: any) => e.event.type === "context_usage");
      expect(contextEvent).toBeDefined();
      expect(contextEvent.event.percent).toBe(90);
    });

    it("compact 후 SSE 이벤트 순서가 유지됨", async () => {
      createTestJsonl("bot", "compact-sse", [
        { id: 1, event: { type: "text_start", card_id: "c1" } },
        { id: 2, event: { type: "text_end", card_id: "c1" } },
        { id: 3, event: { type: "compact", trigger: "auto", message: "Compacted" } },
        { id: 4, event: { type: "text_start", card_id: "c2" } },
        { id: 5, event: { type: "text_end", card_id: "c2" } },
        { id: 6, event: { type: "complete", result: "Done", attachments: [] } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:compact-sse/events`,
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

      expect(dataEvents).toHaveLength(6);
      expect(dataEvents[0].id).toBe("1");
      expect(dataEvents[2].event).toBe("compact");
      expect(dataEvents[5].id).toBe("6");
    });
  });

  // === [7] 에러 케이스 ===

  describe("[체크리스트 7] 에러 케이스 정상 표시", () => {
    it("에러로 종료된 세션 상태가 'error'", async () => {
      createTestJsonl("bot", "error-session", [
        { id: 1, event: { type: "progress", text: "Starting..." } },
        { id: 2, event: { type: "text_start", card_id: "c1" } },
        { id: 3, event: { type: "text_delta", card_id: "c1", text: "Analyzing..." } },
        { id: 4, event: { type: "error", message: "Rate limit exceeded. Please wait 60 seconds.", error_code: "RATE_LIMIT" } },
      ]);

      const listRes = await fetch(`http://localhost:${dashPort}/api/sessions`);
      const listData = await listRes.json();
      expect(listData.sessions[0].status).toBe("error");
      expect(listData.sessions[0].lastEventType).toBe("error");

      const detailRes = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:error-session`,
      );
      const detail = await detailRes.json();
      expect(detail.status).toBe("error");
      expect(detail.error).toBe("Rate limit exceeded. Please wait 60 seconds.");
    });

    it("타임아웃 에러 세션", async () => {
      createTestJsonl("bot", "timeout-session", [
        { id: 1, event: { type: "progress", text: "Working..." } },
        { id: 2, event: { type: "tool_start", card_id: "t1", tool_name: "Bash", tool_input: { command: "long-running-cmd" } } },
        { id: 3, event: { type: "error", message: "Execution timed out after 300 seconds", error_code: "TIMEOUT" } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:timeout-session`,
      );
      const detail = await res.json();

      expect(detail.status).toBe("error");
      expect(detail.error).toContain("timed out");
      expect(detail.events[1].event.type).toBe("tool_start");
    });

    it("존재하지 않는 세션 조회 시 404", async () => {
      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/ghost:phantom`,
      );
      expect(res.status).toBe(404);
      const data = await res.json();
      expect(data.error.code).toBe("SESSION_NOT_FOUND");
    });

    it("잘못된 세션 ID 형식 시 400", async () => {
      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/invalid-format/events`,
      );
      expect(res.status).toBe(400);
      const data = await res.json();
      expect(data.error.code).toBe("INVALID_SESSION_ID");
    });

    it("도구 실행 에러가 포함된 세션 (성공적으로 복구)", async () => {
      createTestJsonl("bot", "tool-error", [
        { id: 1, event: { type: "text_start", card_id: "c1" } },
        { id: 2, event: { type: "text_end", card_id: "c1" } },
        { id: 3, event: { type: "tool_start", card_id: "t1", tool_name: "Bash", tool_input: { command: "rm -rf /" } } },
        { id: 4, event: { type: "tool_result", card_id: "t1", tool_name: "Bash", result: "Permission denied", is_error: true } },
        { id: 5, event: { type: "text_start", card_id: "c2" } },
        { id: 6, event: { type: "text_delta", card_id: "c2", text: "Tool failed, trying another approach" } },
        { id: 7, event: { type: "text_end", card_id: "c2" } },
        { id: 8, event: { type: "complete", result: "Recovered", attachments: [] } },
      ]);

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:tool-error`,
      );
      const detail = await res.json();

      expect(detail.status).toBe("completed");
      const toolResult = detail.events.find(
        (e: any) => e.event.type === "tool_result" && e.event.is_error,
      );
      expect(toolResult).toBeDefined();
      expect(toolResult.event.result).toBe("Permission denied");
    });

    it("Soul 서버 다운 시 세션 생성 실패", async () => {
      const res = await fetch(`http://localhost:${dashPort}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: "Test" }),
      });

      expect(res.status).toBeGreaterThanOrEqual(500);
    });

    it("빈 JSONL 파일 처리", async () => {
      const dir = join(TEST_DIR, "bot");
      mkdirSync(dir, { recursive: true });
      writeFileSync(join(dir, "empty.jsonl"), "", "utf-8");

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:empty`,
      );
      expect(res.status).toBe(404);
    });

    it("손상된 JSONL 줄이 포함된 세션", async () => {
      const dir = join(TEST_DIR, "bot");
      mkdirSync(dir, { recursive: true });
      const content = [
        JSON.stringify({ id: 1, event: { type: "progress", text: "Start" } }),
        "CORRUPTED LINE {{{",
        JSON.stringify({ id: 2, event: { type: "complete", result: "Done", attachments: [] } }),
        "",
      ].join("\n");
      writeFileSync(join(dir, "corrupt.jsonl"), content, "utf-8");

      const res = await fetch(
        `http://localhost:${dashPort}/api/sessions/bot:corrupt`,
      );
      expect(res.ok).toBe(true);

      const detail = await res.json();
      expect(detail.events).toHaveLength(2);
      expect(detail.status).toBe("completed");
    });
  });
});
