/**
 * SessionStore 테스트
 *
 * JSONL 파일 읽기 기능을 검증합니다.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdirSync, writeFileSync, rmSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";
import { SessionStore } from "../../../src/soul-dashboard/server/session-store.js";

const TEST_DIR = join(tmpdir(), "soul-dashboard-test-" + Date.now());

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

describe("SessionStore", () => {
  let store: SessionStore;

  beforeEach(() => {
    mkdirSync(TEST_DIR, { recursive: true });
    store = new SessionStore({ baseDir: TEST_DIR });
  });

  afterEach(() => {
    rmSync(TEST_DIR, { recursive: true, force: true });
  });

  describe("listSessions", () => {
    it("should return empty array when no sessions exist", async () => {
      const sessions = await store.listSessions();
      expect(sessions).toEqual([]);
    });

    it("should return empty array when baseDir does not exist", async () => {
      const missingStore = new SessionStore({
        baseDir: join(TEST_DIR, "nonexistent"),
      });
      const sessions = await missingStore.listSessions();
      expect(sessions).toEqual([]);
    });

    it("should list sessions from JSONL files", async () => {
      createTestJsonl("bot", "req-1", [
        { id: 1, event: { type: "progress", text: "Starting..." } },
        { id: 2, event: { type: "complete", result: "Done" } },
      ]);
      createTestJsonl("bot", "req-2", [
        { id: 1, event: { type: "progress", text: "Working..." } },
      ]);

      const sessions = await store.listSessions();
      expect(sessions).toHaveLength(2);

      const req1 = sessions.find((s) => s.requestId === "req-1");
      const req2 = sessions.find((s) => s.requestId === "req-2");

      expect(req1).toBeDefined();
      expect(req1!.clientId).toBe("bot");
      expect(req1!.eventCount).toBe(2);
      expect(req1!.lastEventType).toBe("complete");
      expect(req1!.status).toBe("completed");

      expect(req2).toBeDefined();
      expect(req2!.eventCount).toBe(1);
      expect(req2!.lastEventType).toBe("progress");
      expect(req2!.status).toBe("running");
    });

    it("should list sessions from multiple clients", async () => {
      createTestJsonl("client-a", "req-1", [
        { id: 1, event: { type: "progress", text: "A" } },
      ]);
      createTestJsonl("client-b", "req-1", [
        { id: 1, event: { type: "error", message: "Failed" } },
      ]);

      const sessions = await store.listSessions();
      expect(sessions).toHaveLength(2);

      const clientA = sessions.find((s) => s.clientId === "client-a");
      const clientB = sessions.find((s) => s.clientId === "client-b");

      expect(clientA!.status).toBe("running");
      expect(clientB!.status).toBe("error");
    });
  });

  describe("readEvents", () => {
    it("should return empty array for nonexistent session", async () => {
      const events = await store.readEvents("ghost", "phantom");
      expect(events).toEqual([]);
    });

    it("should read all events from JSONL file", async () => {
      createTestJsonl("bot", "req-1", [
        { id: 1, event: { type: "progress", text: "Step 1" } },
        { id: 2, event: { type: "text_start", card_id: "abc12345" } },
        {
          id: 3,
          event: {
            type: "text_delta",
            card_id: "abc12345",
            text: "Hello",
          },
        },
        { id: 4, event: { type: "text_end", card_id: "abc12345" } },
        { id: 5, event: { type: "complete", result: "Done" } },
      ]);

      const events = await store.readEvents("bot", "req-1");
      expect(events).toHaveLength(5);
      expect(events[0].id).toBe(1);
      expect(events[0].event.type).toBe("progress");
      expect(events[4].id).toBe(5);
      expect(events[4].event.type).toBe("complete");
    });

    it("should skip corrupted lines", async () => {
      const dir = join(TEST_DIR, "bot");
      mkdirSync(dir, { recursive: true });
      const content = [
        JSON.stringify({ id: 1, event: { type: "progress", text: "OK" } }),
        "THIS IS NOT VALID JSON",
        JSON.stringify({
          id: 2,
          event: { type: "complete", result: "Done" },
        }),
      ].join("\n");
      writeFileSync(join(dir, "req-corrupt.jsonl"), content, "utf-8");

      const events = await store.readEvents("bot", "req-corrupt");
      expect(events).toHaveLength(2);
      expect(events[0].id).toBe(1);
      expect(events[1].id).toBe(2);
    });
  });

  describe("readEventsSince", () => {
    it("should return events after given ID", async () => {
      createTestJsonl("bot", "req-1", [
        { id: 1, event: { type: "progress", text: "Step 1" } },
        { id: 2, event: { type: "progress", text: "Step 2" } },
        { id: 3, event: { type: "progress", text: "Step 3" } },
        { id: 4, event: { type: "complete", result: "Done" } },
      ]);

      const events = await store.readEventsSince("bot", "req-1", 2);
      expect(events).toHaveLength(2);
      expect(events[0].id).toBe(3);
      expect(events[1].id).toBe(4);
    });

    it("should return all events when afterId is 0", async () => {
      createTestJsonl("bot", "req-1", [
        { id: 1, event: { type: "progress", text: "Step 1" } },
        { id: 2, event: { type: "complete", result: "Done" } },
      ]);

      const events = await store.readEventsSince("bot", "req-1", 0);
      expect(events).toHaveLength(2);
    });

    it("should return empty when afterId is beyond last event", async () => {
      createTestJsonl("bot", "req-1", [
        { id: 1, event: { type: "progress", text: "Step 1" } },
      ]);

      const events = await store.readEventsSince("bot", "req-1", 100);
      expect(events).toEqual([]);
    });
  });

  describe("inferStatus", () => {
    it("should infer 'completed' for complete event", () => {
      expect(store.inferStatus("complete")).toBe("completed");
    });

    it("should infer 'completed' for result event", () => {
      expect(store.inferStatus("result")).toBe("completed");
    });

    it("should infer 'error' for error event", () => {
      expect(store.inferStatus("error")).toBe("error");
    });

    it("should infer 'running' for progress event", () => {
      expect(store.inferStatus("progress")).toBe("running");
    });

    it("should infer 'running' for text_delta event", () => {
      expect(store.inferStatus("text_delta")).toBe("running");
    });

    it("should infer 'unknown' for undefined", () => {
      expect(store.inferStatus(undefined)).toBe("unknown");
    });
  });

  describe("path safety", () => {
    it("should sanitize path components to prevent traversal", async () => {
      // "../" in clientId should be sanitized to ".._"
      createTestJsonl(".._", "req-1", [
        { id: 1, event: { type: "progress", text: "Sanitized" } },
      ]);

      const events = await store.readEvents("../", "req-1");
      // Should read the sanitized path, not traverse
      expect(events).toHaveLength(1);
    });
  });
});
