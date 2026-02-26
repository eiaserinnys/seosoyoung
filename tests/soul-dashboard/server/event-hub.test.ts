/**
 * EventHub 테스트
 *
 * SSE 클라이언트 관리와 브로드캐스트를 검증합니다.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { EventHub } from "../../../src/soul-dashboard/server/event-hub.js";
import type { SoulSSEEvent } from "../../../src/soul-dashboard/shared/types.js";

/** Express Response 목업 */
function createMockResponse() {
  const written: string[] = [];
  let ended = false;
  const onHandlers: Record<string, Function> = {};

  const res = {
    writeHead: vi.fn(),
    write: vi.fn((data: string) => {
      if (ended) throw new Error("Write after end");
      written.push(data);
      return true;
    }),
    end: vi.fn(() => {
      ended = true;
    }),
    on: vi.fn((event: string, handler: Function) => {
      onHandlers[event] = handler;
    }),
    get writableEnded() {
      return ended;
    },
    // 테스트 헬퍼
    _written: written,
    _triggerClose: () => {
      if (onHandlers.close) onHandlers.close();
    },
  };

  return res as any;
}

describe("EventHub", () => {
  let hub: EventHub;

  beforeEach(() => {
    hub = new EventHub();
  });

  describe("addClient / removeClient", () => {
    it("should register a client and set SSE headers", () => {
      const res = createMockResponse();
      const clientId = hub.addClient("bot:req-1", res);

      expect(clientId).toMatch(/^dash-/);
      expect(res.writeHead).toHaveBeenCalledWith(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      });
      expect(hub.getTotalClientCount()).toBe(1);
      expect(hub.getClientCount("bot:req-1")).toBe(1);
    });

    it("should send connected event on registration", () => {
      const res = createMockResponse();
      const clientId = hub.addClient("bot:req-1", res);

      expect(res._written.length).toBeGreaterThan(0);
      expect(res._written[0]).toContain("event: connected");
      expect(res._written[0]).toContain(clientId);
    });

    it("should remove client", () => {
      const res = createMockResponse();
      const clientId = hub.addClient("bot:req-1", res);

      hub.removeClient(clientId);

      expect(hub.getTotalClientCount()).toBe(0);
      expect(hub.getClientCount("bot:req-1")).toBe(0);
    });

    it("should auto-remove on connection close", () => {
      const res = createMockResponse();
      hub.addClient("bot:req-1", res);

      expect(hub.getTotalClientCount()).toBe(1);

      // 연결 종료 시뮬레이션
      res._triggerClose();

      expect(hub.getTotalClientCount()).toBe(0);
    });

    it("should support multiple clients per session", () => {
      const res1 = createMockResponse();
      const res2 = createMockResponse();

      hub.addClient("bot:req-1", res1);
      hub.addClient("bot:req-1", res2);

      expect(hub.getClientCount("bot:req-1")).toBe(2);
      expect(hub.getTotalClientCount()).toBe(2);
    });
  });

  describe("broadcast", () => {
    it("should send event to all clients of a session", () => {
      const res1 = createMockResponse();
      const res2 = createMockResponse();

      hub.addClient("bot:req-1", res1);
      hub.addClient("bot:req-1", res2);

      const event: SoulSSEEvent = { type: "progress", text: "Working..." };
      hub.broadcast("bot:req-1", 1, event);

      // 각 response에 SSE 형식으로 전송되었는지 확인
      // res1._written[0]은 connected 이벤트이므로 [1]이 broadcast
      const msg1 = res1._written[1];
      const msg2 = res2._written[1];

      expect(msg1).toContain("id: 1");
      expect(msg1).toContain("event: progress");
      expect(msg1).toContain('"text":"Working..."');

      expect(msg2).toEqual(msg1);
    });

    it("should not send to clients of other sessions", () => {
      const res1 = createMockResponse();
      const res2 = createMockResponse();

      hub.addClient("bot:req-1", res1);
      hub.addClient("bot:req-2", res2);

      const event: SoulSSEEvent = { type: "progress", text: "Only req-1" };
      hub.broadcast("bot:req-1", 1, event);

      // res1은 connected + broadcast = 2 writes
      expect(res1._written).toHaveLength(2);
      // res2는 connected만 = 1 write
      expect(res2._written).toHaveLength(1);
    });

    it("should clean up dead connections during broadcast", () => {
      const res1 = createMockResponse();
      const res2 = createMockResponse();

      hub.addClient("bot:req-1", res1);
      hub.addClient("bot:req-1", res2);

      // res1을 수동으로 종료 (writableEnded = true)
      res1.end();

      const event: SoulSSEEvent = {
        type: "complete",
        result: "Done",
        attachments: [],
      };
      hub.broadcast("bot:req-1", 2, event);

      // dead connection이 정리되어 1개만 남아야 함
      expect(hub.getClientCount("bot:req-1")).toBe(1);
    });
  });

  describe("replayEvents", () => {
    it("should send events in order to specific client", () => {
      const res = createMockResponse();
      const clientId = hub.addClient("bot:req-1", res);

      const events = [
        { id: 1, event: { type: "progress", text: "Step 1" } },
        { id: 2, event: { type: "progress", text: "Step 2" } },
        { id: 3, event: { type: "complete", result: "Done" } },
      ];

      hub.replayEvents(clientId, events);

      // connected(1) + replay(3) = 4 writes
      expect(res._written).toHaveLength(4);
      expect(res._written[1]).toContain("id: 1");
      expect(res._written[2]).toContain("id: 2");
      expect(res._written[3]).toContain("id: 3");
    });
  });

  describe("sendKeepalive", () => {
    it("should send keepalive comment to all clients", () => {
      const res1 = createMockResponse();
      const res2 = createMockResponse();

      hub.addClient("bot:req-1", res1);
      hub.addClient("bot:req-2", res2);

      hub.sendKeepalive();

      // 마지막 write가 keepalive 코멘트인지 확인
      const last1 = res1._written[res1._written.length - 1];
      const last2 = res2._written[res2._written.length - 1];

      expect(last1).toContain(": keepalive");
      expect(last2).toContain(": keepalive");
    });
  });

  describe("getStats", () => {
    it("should return per-session client counts", () => {
      const res1 = createMockResponse();
      const res2 = createMockResponse();
      const res3 = createMockResponse();

      hub.addClient("bot:req-1", res1);
      hub.addClient("bot:req-1", res2);
      hub.addClient("bot:req-2", res3);

      const stats = hub.getStats();
      expect(stats).toEqual({
        "bot:req-1": 2,
        "bot:req-2": 1,
      });
    });
  });
});
