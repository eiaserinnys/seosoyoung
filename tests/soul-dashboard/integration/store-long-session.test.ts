/**
 * 클라이언트 스토어 통합 테스트: 장시간 세션 + 컴팩트 렌더링
 *
 * 체크리스트 항목:
 * - [6] 장시간 세션 (컴팩트 발생) 정상 렌더링
 * - [7] 에러 케이스 정상 표시
 *
 * dashboard-store와 layout-engine의 복합 시나리오를 검증합니다.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useDashboardStore } from "../../../src/soul-dashboard/client/stores/dashboard-store";
import { buildGraph } from "../../../src/soul-dashboard/client/lib/layout-engine";
import type {
  SoulSSEEvent,
  TextStartEvent,
  TextDeltaEvent,
  TextEndEvent,
  ToolStartEvent,
  ToolResultEvent,
  CompactEvent,
  ContextUsageEvent,
  ErrorEvent,
  CompleteEvent,
} from "../../../src/soul-dashboard/shared/types";

describe("Store + Layout: Long Session Rendering", () => {
  beforeEach(() => {
    useDashboardStore.getState().reset();
  });

  // === [6] 장시간 세션 ===

  describe("[체크리스트 6] 장시간 세션 정상 렌더링", () => {
    it("100개 카드 처리 후 스토어 상태 일관성", () => {
      const { processEvent } = useDashboardStore.getState();
      let eventId = 1;

      // 50개의 text + 50개의 tool 카드 생성
      for (let i = 0; i < 50; i++) {
        const textId = `text-${i}`;
        processEvent({ type: "text_start", card_id: textId } as TextStartEvent, eventId++);
        processEvent({ type: "text_delta", card_id: textId, text: `Content ${i}` } as TextDeltaEvent, eventId++);
        processEvent({ type: "text_end", card_id: textId } as TextEndEvent, eventId++);

        const toolId = `tool-${i}`;
        processEvent({
          type: "tool_start",
          card_id: toolId,
          tool_name: "Bash",
          tool_input: { command: `echo ${i}` },
        } as ToolStartEvent, eventId++);
        processEvent({
          type: "tool_result",
          card_id: toolId,
          tool_name: "Bash",
          result: `output ${i}`,
          is_error: false,
        } as ToolResultEvent, eventId++);
      }

      const state = useDashboardStore.getState();

      // 100개 카드가 정확히 생성되었는지
      expect(state.cards).toHaveLength(100);

      // 모든 카드가 완료 상태
      expect(state.cards.every((c) => c.completed)).toBe(true);

      // lastEventId가 정확한지
      expect(state.lastEventId).toBe(eventId - 1);

      // 카드 타입 비율 확인
      const textCards = state.cards.filter((c) => c.type === "text");
      const toolCards = state.cards.filter((c) => c.type === "tool");
      expect(textCards).toHaveLength(50);
      expect(toolCards).toHaveLength(50);
    });

    it("100개 카드에서 그래프 노드/엣지 생성 성능", () => {
      const { processEvent } = useDashboardStore.getState();
      let eventId = 1;

      for (let i = 0; i < 50; i++) {
        const textId = `text-${i}`;
        processEvent({ type: "text_start", card_id: textId } as TextStartEvent, eventId++);
        processEvent({ type: "text_delta", card_id: textId, text: `Content ${i}` } as TextDeltaEvent, eventId++);
        processEvent({ type: "text_end", card_id: textId } as TextEndEvent, eventId++);

        const toolId = `tool-${i}`;
        processEvent({
          type: "tool_start",
          card_id: toolId,
          tool_name: "Read",
          tool_input: { file_path: `/path/file${i}.ts` },
        } as ToolStartEvent, eventId++);
        processEvent({
          type: "tool_result",
          card_id: toolId,
          tool_name: "Read",
          result: `content of file${i}`,
          is_error: false,
        } as ToolResultEvent, eventId++);
      }

      const cards = useDashboardStore.getState().cards;
      const events: SoulSSEEvent[] = [
        { type: "complete", result: "Done", attachments: [] },
      ];

      // 그래프 빌드 시간 측정
      const start = performance.now();
      const { nodes, edges } = buildGraph(cards, events);
      const elapsed = performance.now() - start;

      // 노드가 생성되었는지
      expect(nodes.length).toBeGreaterThan(0);
      expect(edges.length).toBeGreaterThan(0);

      // 100개 카드 기준 500ms 이내에 그래프 빌드 완료
      expect(elapsed).toBeLessThan(500);
    });

    it("컴팩트 이벤트 전후로 카드가 정상 누적", () => {
      const { processEvent } = useDashboardStore.getState();
      let eventId = 1;

      // 컴팩트 전 카드
      processEvent({ type: "text_start", card_id: "before-1" } as TextStartEvent, eventId++);
      processEvent({ type: "text_delta", card_id: "before-1", text: "Before compact" } as TextDeltaEvent, eventId++);
      processEvent({ type: "text_end", card_id: "before-1" } as TextEndEvent, eventId++);

      // 컨텍스트 사용량 이벤트
      processEvent({
        type: "context_usage",
        used_tokens: 180000,
        max_tokens: 200000,
        percent: 90,
      } as ContextUsageEvent, eventId++);

      // 컴팩트 이벤트
      processEvent({
        type: "compact",
        trigger: "auto",
        message: "Compacted: 180K → 50K tokens",
      } as CompactEvent, eventId++);

      // 컴팩트 후 카드
      processEvent({ type: "text_start", card_id: "after-1" } as TextStartEvent, eventId++);
      processEvent({ type: "text_delta", card_id: "after-1", text: "After compact" } as TextDeltaEvent, eventId++);
      processEvent({ type: "text_end", card_id: "after-1" } as TextEndEvent, eventId++);

      const state = useDashboardStore.getState();

      // 컴팩트 전후 카드가 모두 존재
      expect(state.cards).toHaveLength(2);
      expect(state.cards[0].cardId).toBe("before-1");
      expect(state.cards[0].content).toBe("Before compact");
      expect(state.cards[1].cardId).toBe("after-1");
      expect(state.cards[1].content).toBe("After compact");
    });

    it("컴팩트 이벤트가 포함된 세션에서 그래프가 정상 빌드됨", () => {
      const cards = [
        { cardId: "c1", type: "text" as const, content: "Before", completed: true },
        { cardId: "c2", type: "text" as const, content: "After", completed: true },
      ];
      const events: SoulSSEEvent[] = [
        { type: "compact", trigger: "auto", message: "Compacted" },
        { type: "complete", result: "Done", attachments: [] },
      ];

      const { nodes, edges } = buildGraph(cards, events);

      // 카드 노드 2개 + complete 시스템 노드가 존재
      expect(nodes.length).toBeGreaterThanOrEqual(2);

      // complete 이벤트는 시스템 노드로 표시됨
      const systemNodes = nodes.filter((n) => n.type === "system");
      const completeNode = systemNodes.find((n) => n.data.label.includes("Complete"));
      expect(completeNode).toBeDefined();

      // compact 이벤트는 현재 노이즈로 분류되어 시스템 노드로 표시되지 않음
      // (context_usage, progress, debug 등과 동일)
      // 향후 컴팩트 시각화가 필요하면 isSignificantSystemEvent에 추가
      const compactNode = systemNodes.find((n) => n.data.label.includes("Compact"));
      expect(compactNode).toBeUndefined();

      // 엣지가 존재 (카드 간 연결)
      expect(edges.length).toBeGreaterThan(0);
    });
  });

  // === [7] 에러 케이스 렌더링 ===

  describe("[체크리스트 7] 에러 케이스 클라이언트 렌더링", () => {
    it("에러 이벤트 처리 후 스토어 상태", () => {
      const { processEvent } = useDashboardStore.getState();

      processEvent({ type: "text_start", card_id: "c1" } as TextStartEvent, 1);
      processEvent({ type: "text_delta", card_id: "c1", text: "Working..." } as TextDeltaEvent, 2);
      processEvent({
        type: "error",
        message: "Rate limit exceeded",
        error_code: "RATE_LIMIT",
      } as ErrorEvent, 3);

      const state = useDashboardStore.getState();

      // 에러 전의 카드는 유지
      expect(state.cards).toHaveLength(1);
      expect(state.cards[0].cardId).toBe("c1");
      // text_end를 받지 못했으므로 미완료
      expect(state.cards[0].completed).toBe(false);
      // lastEventId는 에러 이벤트까지 반영
      expect(state.lastEventId).toBe(3);
    });

    it("에러 이벤트가 그래프에 에러 노드로 표시", () => {
      const cards = [
        { cardId: "c1", type: "text" as const, content: "Partial work", completed: false },
      ];
      const events: SoulSSEEvent[] = [
        { type: "error", message: "Execution failed" },
      ];

      const { nodes } = buildGraph(cards, events);
      const systemNodes = nodes.filter((n) => n.type === "system");

      const errorNode = systemNodes.find((n) => n.data.label.includes("Error"));
      expect(errorNode).toBeDefined();
    });

    it("도구 에러 카드가 정상 렌더링", () => {
      const { processEvent } = useDashboardStore.getState();

      processEvent({
        type: "tool_start",
        card_id: "t1",
        tool_name: "Bash",
        tool_input: { command: "invalid-cmd" },
      } as ToolStartEvent, 1);

      processEvent({
        type: "tool_result",
        card_id: "t1",
        tool_name: "Bash",
        result: "command not found: invalid-cmd",
        is_error: true,
      } as ToolResultEvent, 2);

      const cards = useDashboardStore.getState().cards;
      expect(cards[0].isError).toBe(true);
      expect(cards[0].toolResult).toContain("command not found");

      // 에러 도구 카드가 그래프에 정상 표시
      const events: SoulSSEEvent[] = [];
      const { nodes } = buildGraph(cards, events);

      const toolResultNode = nodes.find((n) => n.type === "tool_result");
      expect(toolResultNode).toBeDefined();
      expect(toolResultNode!.data.isError).toBe(true);
    });

    it("세션 이벤트 순서: progress → cards → error", () => {
      const { processEvent } = useDashboardStore.getState();
      let id = 1;

      processEvent({ type: "text_start", card_id: "c1" } as TextStartEvent, id++);
      processEvent({ type: "text_delta", card_id: "c1", text: "Partial" } as TextDeltaEvent, id++);
      processEvent({ type: "text_end", card_id: "c1" } as TextEndEvent, id++);
      processEvent({
        type: "tool_start",
        card_id: "t1",
        tool_name: "Bash",
        tool_input: { command: "test" },
      } as ToolStartEvent, id++);
      // 타임아웃으로 tool_result 없이 에러
      processEvent({
        type: "error",
        message: "Timed out waiting for tool result",
      } as ErrorEvent, id++);

      const state = useDashboardStore.getState();

      // 텍스트 카드는 완료, 도구 카드는 미완료
      expect(state.cards).toHaveLength(2);
      expect(state.cards[0].completed).toBe(true);
      expect(state.cards[1].completed).toBe(false);
      expect(state.cards[1].type).toBe("tool");
    });
  });
});
