/**
 * dashboard-store 테스트
 *
 * Zustand 스토어의 이벤트 처리 로직을 검증합니다.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useDashboardStore } from "../../../src/soul-dashboard/client/stores/dashboard-store";
import type {
  TextStartEvent,
  TextDeltaEvent,
  TextEndEvent,
  ToolStartEvent,
  ToolResultEvent,
  CompleteEvent,
  SessionSummary,
} from "../../../src/soul-dashboard/shared/types";

describe("dashboard-store", () => {
  beforeEach(() => {
    useDashboardStore.getState().reset();
  });

  // === 세션 관리 ===

  describe("sessions", () => {
    it("should set sessions", () => {
      const sessions: SessionSummary[] = [
        {
          clientId: "c1",
          requestId: "r1",
          status: "running",
          eventCount: 5,
          createdAt: "2026-01-01T00:00:00Z",
        },
      ];
      useDashboardStore.getState().setSessions(sessions);
      expect(useDashboardStore.getState().sessions).toEqual(sessions);
      expect(useDashboardStore.getState().sessionsError).toBeNull();
    });

    it("should set loading state", () => {
      useDashboardStore.getState().setSessionsLoading(true);
      expect(useDashboardStore.getState().sessionsLoading).toBe(true);
    });

    it("should set error and clear loading", () => {
      useDashboardStore.getState().setSessionsLoading(true);
      useDashboardStore.getState().setSessionsError("Network error");
      expect(useDashboardStore.getState().sessionsError).toBe("Network error");
      expect(useDashboardStore.getState().sessionsLoading).toBe(false);
    });
  });

  // === 활성 세션 ===

  describe("active session", () => {
    it("should set active session and clear cards", () => {
      // 먼저 카드를 추가
      const textStart: TextStartEvent = { type: "text_start", card_id: "abc" };
      useDashboardStore.getState().processEvent(textStart, 1);
      expect(useDashboardStore.getState().cards.length).toBe(1);

      // 활성 세션 변경 시 카드 초기화
      useDashboardStore.getState().setActiveSession("c1:r1");
      expect(useDashboardStore.getState().activeSessionKey).toBe("c1:r1");
      expect(useDashboardStore.getState().cards).toEqual([]);
      expect(useDashboardStore.getState().lastEventId).toBe(0);
      expect(useDashboardStore.getState().selectedCardId).toBeNull();
    });

    it("should clear active session when set to null", () => {
      useDashboardStore.getState().setActiveSession("c1:r1");
      useDashboardStore.getState().setActiveSession(null);
      expect(useDashboardStore.getState().activeSessionKey).toBeNull();
    });
  });

  // === 카드 선택 ===

  describe("selectCard", () => {
    it("should select and deselect card", () => {
      useDashboardStore.getState().selectCard("card-1");
      expect(useDashboardStore.getState().selectedCardId).toBe("card-1");

      useDashboardStore.getState().selectCard(null);
      expect(useDashboardStore.getState().selectedCardId).toBeNull();
    });
  });

  // === SSE 이벤트 처리: 텍스트 카드 ===

  describe("processEvent - text card lifecycle", () => {
    it("should create text card on text_start", () => {
      const event: TextStartEvent = { type: "text_start", card_id: "abc123" };
      useDashboardStore.getState().processEvent(event, 1);

      const cards = useDashboardStore.getState().cards;
      expect(cards).toHaveLength(1);
      expect(cards[0]).toEqual({
        cardId: "abc123",
        type: "text",
        content: "",
        completed: false,
      });
      expect(useDashboardStore.getState().lastEventId).toBe(1);
    });

    it("should accumulate text on text_delta", () => {
      const start: TextStartEvent = { type: "text_start", card_id: "abc" };
      const delta1: TextDeltaEvent = { type: "text_delta", card_id: "abc", text: "Hello " };
      const delta2: TextDeltaEvent = { type: "text_delta", card_id: "abc", text: "World" };

      const { processEvent } = useDashboardStore.getState();
      processEvent(start, 1);
      processEvent(delta1, 2);
      processEvent(delta2, 3);

      const cards = useDashboardStore.getState().cards;
      expect(cards[0].content).toBe("Hello World");
      expect(cards[0].completed).toBe(false);
    });

    it("should mark completed on text_end", () => {
      const start: TextStartEvent = { type: "text_start", card_id: "abc" };
      const delta: TextDeltaEvent = { type: "text_delta", card_id: "abc", text: "Done" };
      const end: TextEndEvent = { type: "text_end", card_id: "abc" };

      const { processEvent } = useDashboardStore.getState();
      processEvent(start, 1);
      processEvent(delta, 2);
      processEvent(end, 3);

      const cards = useDashboardStore.getState().cards;
      expect(cards[0].content).toBe("Done");
      expect(cards[0].completed).toBe(true);
      expect(useDashboardStore.getState().lastEventId).toBe(3);
    });
  });

  // === SSE 이벤트 처리: 도구 카드 ===

  describe("processEvent - tool card lifecycle", () => {
    it("should create tool card on tool_start", () => {
      const event: ToolStartEvent = {
        type: "tool_start",
        card_id: "tool-1",
        tool_name: "Read",
        tool_input: { file_path: "/test.ts" },
      };
      useDashboardStore.getState().processEvent(event, 10);

      const cards = useDashboardStore.getState().cards;
      expect(cards).toHaveLength(1);
      expect(cards[0]).toEqual({
        cardId: "tool-1",
        type: "tool",
        content: "",
        toolName: "Read",
        toolInput: { file_path: "/test.ts" },
        completed: false,
      });
    });

    it("should complete tool card on tool_result", () => {
      const start: ToolStartEvent = {
        type: "tool_start",
        card_id: "tool-1",
        tool_name: "Bash",
        tool_input: { command: "ls" },
      };
      const result: ToolResultEvent = {
        type: "tool_result",
        card_id: "tool-1",
        tool_name: "Bash",
        result: "file1.txt\nfile2.txt",
        is_error: false,
      };

      const { processEvent } = useDashboardStore.getState();
      processEvent(start, 1);
      processEvent(result, 2);

      const cards = useDashboardStore.getState().cards;
      expect(cards[0].toolResult).toBe("file1.txt\nfile2.txt");
      expect(cards[0].isError).toBe(false);
      expect(cards[0].completed).toBe(true);
    });

    it("should handle tool error", () => {
      const start: ToolStartEvent = {
        type: "tool_start",
        card_id: "tool-2",
        tool_name: "Bash",
        tool_input: { command: "invalid" },
      };
      const result: ToolResultEvent = {
        type: "tool_result",
        card_id: "tool-2",
        tool_name: "Bash",
        result: "command not found",
        is_error: true,
      };

      const { processEvent } = useDashboardStore.getState();
      processEvent(start, 1);
      processEvent(result, 2);

      const cards = useDashboardStore.getState().cards;
      expect(cards[0].isError).toBe(true);
      expect(cards[0].completed).toBe(true);
    });

    it("should use fallback cardId when card_id is undefined", () => {
      const start: ToolStartEvent = {
        type: "tool_start",
        tool_name: "Read",
        tool_input: {},
      };
      useDashboardStore.getState().processEvent(start, 42);

      const cards = useDashboardStore.getState().cards;
      expect(cards[0].cardId).toBe("tool-42");
    });

    it("should match tool_result by tool_name when both card_ids are undefined", () => {
      const start: ToolStartEvent = {
        type: "tool_start",
        tool_name: "Bash",
        tool_input: { command: "echo hello" },
      };
      const result: ToolResultEvent = {
        type: "tool_result",
        tool_name: "Bash",
        result: "hello",
        is_error: false,
      };

      const { processEvent } = useDashboardStore.getState();
      processEvent(start, 10);
      processEvent(result, 11);

      const cards = useDashboardStore.getState().cards;
      expect(cards).toHaveLength(1);
      expect(cards[0].toolResult).toBe("hello");
      expect(cards[0].completed).toBe(true);
    });

    it("should match tool_result to the last uncompleted tool with matching name", () => {
      const { processEvent } = useDashboardStore.getState();

      // Tool 1 (completed)
      processEvent({
        type: "tool_start",
        card_id: "t1",
        tool_name: "Bash",
        tool_input: {},
      } as ToolStartEvent, 1);
      processEvent({
        type: "tool_result",
        card_id: "t1",
        tool_name: "Bash",
        result: "done",
        is_error: false,
      } as ToolResultEvent, 2);

      // Tool 2 (uncompleted, no card_id)
      processEvent({
        type: "tool_start",
        tool_name: "Bash",
        tool_input: {},
      } as ToolStartEvent, 3);

      // Result without card_id should match Tool 2
      processEvent({
        type: "tool_result",
        tool_name: "Bash",
        result: "second",
        is_error: false,
      } as ToolResultEvent, 4);

      const cards = useDashboardStore.getState().cards;
      expect(cards).toHaveLength(2);
      expect(cards[0].completed).toBe(true);
      expect(cards[0].toolResult).toBe("done");
      expect(cards[1].completed).toBe(true);
      expect(cards[1].toolResult).toBe("second");
    });
  });

  // === 무시되는 이벤트 ===

  describe("processEvent - ignored events", () => {
    it("should update lastEventId for unhandled event types", () => {
      const event: CompleteEvent = {
        type: "complete",
        result: "done",
        attachments: [],
      };
      useDashboardStore.getState().processEvent(event, 99);

      expect(useDashboardStore.getState().cards).toEqual([]);
      expect(useDashboardStore.getState().lastEventId).toBe(99);
    });
  });

  // === 복합 시나리오 ===

  describe("mixed card sequence", () => {
    it("should handle interleaved text and tool cards", () => {
      const { processEvent } = useDashboardStore.getState();

      // Text card 1
      processEvent({ type: "text_start", card_id: "t1" }, 1);
      processEvent({ type: "text_delta", card_id: "t1", text: "Analyzing..." } as TextDeltaEvent, 2);
      processEvent({ type: "text_end", card_id: "t1" }, 3);

      // Tool card
      processEvent({
        type: "tool_start",
        card_id: "tool-1",
        tool_name: "Bash",
        tool_input: { command: "ls" },
      } as ToolStartEvent, 4);
      processEvent({
        type: "tool_result",
        card_id: "tool-1",
        tool_name: "Bash",
        result: "ok",
        is_error: false,
      } as ToolResultEvent, 5);

      // Text card 2
      processEvent({ type: "text_start", card_id: "t2" }, 6);
      processEvent({ type: "text_delta", card_id: "t2", text: "Done!" } as TextDeltaEvent, 7);

      const cards = useDashboardStore.getState().cards;
      expect(cards).toHaveLength(3);
      expect(cards[0].cardId).toBe("t1");
      expect(cards[0].completed).toBe(true);
      expect(cards[1].cardId).toBe("tool-1");
      expect(cards[1].completed).toBe(true);
      expect(cards[2].cardId).toBe("t2");
      expect(cards[2].completed).toBe(false); // text_end 미수신
    });
  });

  // === 초기화 ===

  describe("reset", () => {
    it("should reset all state to initial values", () => {
      const { processEvent, setSessions, setActiveSession, selectCard } =
        useDashboardStore.getState();

      setSessions([
        { clientId: "c", requestId: "r", status: "running", eventCount: 1 },
      ]);
      setActiveSession("c:r");
      processEvent({ type: "text_start", card_id: "x" }, 1);
      selectCard("x");

      useDashboardStore.getState().reset();
      const state = useDashboardStore.getState();

      expect(state.sessions).toEqual([]);
      expect(state.activeSessionKey).toBeNull();
      expect(state.cards).toEqual([]);
      expect(state.selectedCardId).toBeNull();
      expect(state.lastEventId).toBe(0);
    });
  });
});
