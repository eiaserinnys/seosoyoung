/**
 * 통합 테스트: JSONL 픽스처 기반 시나리오 검증
 *
 * Phase 1~5 핵심 기능을 JSONL 픽스처 → store.processEvent → buildGraph 파이프라인으로 검증합니다.
 *
 * 시나리오:
 * - basic-flow: thinking → response → complete (기본 플로우)
 * - tree-layout: thinking → tool_call → thinking → tool_call → response (트리 분기)
 * - intervention-flow: 중간에 사용자 개입 포함
 * - multi-tool: 다중 tool 호출 + result (running 상태 해제)
 * - complete-flow: 세션 완료 시 마지막 카드가 response 노드로 변환
 */

import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

import { useDashboardStore } from "../../../src/soul-dashboard/client/stores/dashboard-store.js";
import {
  buildGraph,
  type GraphNode,
} from "../../../src/soul-dashboard/client/lib/layout-engine.js";
import type { SoulSSEEvent, EventRecord } from "../../../src/soul-dashboard/shared/types.js";

// === Fixture Loader ===

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = join(__dirname, "..", "fixtures");

function loadFixture(name: string): EventRecord[] {
  const content = readFileSync(join(FIXTURES_DIR, `${name}.jsonl`), "utf-8");
  return content
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as EventRecord);
}

/**
 * 픽스처의 이벤트를 store.processEvent로 순차 재생합니다.
 * 재생 후 store의 cards, graphEvents를 반환합니다.
 */
function replayFixture(name: string) {
  const records = loadFixture(name);
  const { processEvent } = useDashboardStore.getState();

  // 활성 세션 설정 (store가 동작하려면 필요)
  useDashboardStore.getState().setActiveSession("test:fixture");

  for (const record of records) {
    processEvent(record.event as unknown as SoulSSEEvent, record.id);
  }

  const state = useDashboardStore.getState();
  return {
    cards: state.cards,
    graphEvents: state.graphEvents,
    lastEventId: state.lastEventId,
    records,
  };
}

// === Test Suites ===

describe("JSONL Fixture Integration Tests", () => {
  beforeEach(() => {
    useDashboardStore.getState().reset();
  });

  // === basic-flow: thinking → response → complete ===

  describe("basic-flow: 기본 텍스트 플로우", () => {
    it("텍스트 카드 2개가 생성된다", () => {
      const { cards } = replayFixture("basic-flow");
      expect(cards).toHaveLength(2);
      expect(cards[0].type).toBe("text");
      expect(cards[1].type).toBe("text");
    });

    it("모든 텍스트 카드가 completed 상태이다", () => {
      const { cards } = replayFixture("basic-flow");
      expect(cards.every((c) => c.completed)).toBe(true);
    });

    it("텍스트 델타가 올바르게 누적된다", () => {
      const { cards } = replayFixture("basic-flow");
      expect(cards[0].content).toContain("Let me analyze the code...");
      expect(cards[0].content).toContain("React component");
      expect(cards[1].content).toContain("three panels");
    });

    it("complete 이벤트가 graphEvents에 포함된다", () => {
      const { graphEvents } = replayFixture("basic-flow");
      expect(graphEvents.some((e) => e.type === "complete")).toBe(true);
    });

    it("buildGraph에서 마지막 텍스트 카드가 response 노드가 된다", () => {
      const { cards, graphEvents } = replayFixture("basic-flow");
      const { nodes } = buildGraph(cards, graphEvents);

      // user → system(session) → thinking → response → system(complete)
      const responseNodes = nodes.filter((n) => n.type === "response");
      expect(responseNodes).toHaveLength(1);
      expect(responseNodes[0].data.content).toContain("three panels");
    });

    it("buildGraph에서 user_message가 user 노드로 생성된다", () => {
      const { cards, graphEvents } = replayFixture("basic-flow");
      const { nodes } = buildGraph(cards, graphEvents);

      const userNodes = nodes.filter((n) => n.type === "user");
      expect(userNodes).toHaveLength(1);
      expect(userNodes[0].data.content).toContain("Analyze this code");
    });

    it("buildGraph에서 session과 complete system 노드가 생성된다", () => {
      const { cards, graphEvents } = replayFixture("basic-flow");
      const { nodes } = buildGraph(cards, graphEvents);

      const systemNodes = nodes.filter((n) => n.type === "system");
      expect(systemNodes).toHaveLength(2); // session + complete
      expect(systemNodes.map((n) => n.data.label)).toContain("Session Started");
      expect(systemNodes.map((n) => n.data.label)).toContain("Complete");
    });

    it("buildGraph에서 엣지가 노드를 올바르게 연결한다", () => {
      const { cards, graphEvents } = replayFixture("basic-flow");
      const { nodes, edges } = buildGraph(cards, graphEvents);

      // 노드 수 검증: user + session + thinking + response + complete
      expect(nodes.length).toBeGreaterThanOrEqual(5);
      // 엣지는 노드 수 - 1 이상 (직선 체인)
      expect(edges.length).toBeGreaterThanOrEqual(nodes.length - 2);
    });
  });

  // === tree-layout: thinking → tool → thinking → tool → response ===

  describe("tree-layout: 트리 분기 레이아웃", () => {
    it("텍스트 3개 + 도구 2개 카드가 생성된다", () => {
      const { cards } = replayFixture("tree-layout");
      const textCards = cards.filter((c) => c.type === "text");
      const toolCards = cards.filter((c) => c.type === "tool");
      expect(textCards).toHaveLength(3);
      expect(toolCards).toHaveLength(2);
    });

    it("도구 카드에 toolName과 toolResult가 올바르게 설정된다", () => {
      const { cards } = replayFixture("tree-layout");
      const toolCards = cards.filter((c) => c.type === "tool");
      expect(toolCards[0].toolName).toBe("Read");
      expect(toolCards[0].toolResult).toContain("App()");
      expect(toolCards[0].completed).toBe(true);
      expect(toolCards[1].toolName).toBe("Read");
      expect(toolCards[1].toolResult).toContain("import { App }");
    });

    it("buildGraph에서 tool_call + tool_result 쌍이 생성된다", () => {
      const { cards, graphEvents } = replayFixture("tree-layout");
      const { nodes } = buildGraph(cards, graphEvents);

      const toolCallNodes = nodes.filter((n) => n.type === "tool_call");
      const toolResultNodes = nodes.filter((n) => n.type === "tool_result");
      expect(toolCallNodes).toHaveLength(2);
      expect(toolResultNodes).toHaveLength(2);
    });

    it("buildGraph에서 tool_call→tool_result 수직 엣지가 생성된다", () => {
      const { cards, graphEvents } = replayFixture("tree-layout");
      const { edges, nodes } = buildGraph(cards, graphEvents);

      // 각 tool_call 노드에서 tool_result로 향하는 엣지 확인
      for (const callNode of nodes.filter((n) => n.type === "tool_call")) {
        const resultNodeId = callNode.id.replace("-call", "-result");
        const edge = edges.find(
          (e) => e.source === callNode.id && e.target === resultNodeId,
        );
        expect(edge).toBeDefined();
      }
    });

    it("buildGraph에서 tool 노드는 메인 흐름에서 수평 분기한다", () => {
      const { cards, graphEvents } = replayFixture("tree-layout");
      const { edges, nodes } = buildGraph(cards, graphEvents);

      // thinking 또는 메인 흐름 노드에서 tool_call로의 엣지에 sourceHandle="right" 확인
      const toolCallEdges = edges.filter((e) =>
        nodes.find((n) => n.id === e.target && n.type === "tool_call"),
      );
      expect(toolCallEdges.length).toBeGreaterThanOrEqual(1);
      // 수평 분기 엣지는 right→left handle 사용
      const horizontalEdges = toolCallEdges.filter(
        (e) => e.sourceHandle === "right" || e.targetHandle === "left",
      );
      expect(horizontalEdges.length).toBeGreaterThanOrEqual(1);
    });
  });

  // === intervention-flow: 중간 개입 포함 ===

  describe("intervention-flow: 사용자 개입 시나리오", () => {
    it("개입 이벤트가 graphEvents에 포함된다", () => {
      const { graphEvents } = replayFixture("intervention-flow");
      expect(
        graphEvents.some((e) => e.type === "intervention_sent"),
      ).toBe(true);
    });

    it("개입 전후의 카드가 모두 존재한다", () => {
      const { cards } = replayFixture("intervention-flow");
      // 개입 전: t1 + tool1 + t2 / 개입 후: t3 + tool2 + t4
      expect(cards).toHaveLength(6);
    });

    it("buildGraph에서 intervention 노드가 생성된다", () => {
      const { cards, graphEvents } = replayFixture("intervention-flow");
      const { nodes } = buildGraph(cards, graphEvents);

      const interventionNodes = nodes.filter((n) => n.type === "intervention");
      expect(interventionNodes).toHaveLength(1);
      expect(interventionNodes[0].data.content).toContain("src/client");
    });

    it("buildGraph에서 intervention 노드가 메인 흐름에 삽입된다", () => {
      const { cards, graphEvents } = replayFixture("intervention-flow");
      const { edges, nodes } = buildGraph(cards, graphEvents);

      // intervention 노드에 target/source 엣지가 있어야 함
      const interventionNode = nodes.find((n) => n.type === "intervention");
      expect(interventionNode).toBeDefined();

      const incomingEdges = edges.filter(
        (e) => e.target === interventionNode!.id,
      );
      const outgoingEdges = edges.filter(
        (e) => e.source === interventionNode!.id,
      );
      expect(incomingEdges.length).toBeGreaterThanOrEqual(1);
      expect(outgoingEdges.length).toBeGreaterThanOrEqual(1);
    });
  });

  // === multi-tool: 다중 도구 호출 + running 상태 해제 ===

  describe("multi-tool: 다중 도구 호출", () => {
    it("4개의 도구 카드가 생성된다", () => {
      const { cards } = replayFixture("multi-tool");
      const toolCards = cards.filter((c) => c.type === "tool");
      expect(toolCards).toHaveLength(4);
    });

    it("모든 도구 카드가 completed + toolResult을 갖는다", () => {
      const { cards } = replayFixture("multi-tool");
      const toolCards = cards.filter((c) => c.type === "tool");
      for (const card of toolCards) {
        expect(card.completed).toBe(true);
        expect(card.toolResult).toBeDefined();
      }
    });

    it("도구 카드의 streaming 상태가 모두 해제된다 (buildGraph)", () => {
      const { cards, graphEvents } = replayFixture("multi-tool");
      const { nodes } = buildGraph(cards, graphEvents);

      const toolCallNodes = nodes.filter((n) => n.type === "tool_call");
      for (const node of toolCallNodes) {
        expect(node.data.streaming).toBe(false);
      }
    });

    it("연속 tool 호출이 트리뷰로 thinking에서 분기된다", () => {
      const { cards, graphEvents } = replayFixture("multi-tool");
      const { edges, nodes } = buildGraph(cards, graphEvents);

      // 트리뷰: 모든 tool_call은 thinking 노드에서 right→left로 분기
      const toolCallNodes = nodes.filter((n) => n.type === "tool_call");
      const thinkingNodes = nodes.filter((n) => n.type === "thinking");

      // tool_call→tool_call 직접 연결은 없어야 함
      const chainEdges = edges.filter((e) => {
        const source = nodes.find((n) => n.id === e.source);
        const target = nodes.find((n) => n.id === e.target);
        return source?.type === "tool_call" && target?.type === "tool_call";
      });
      expect(chainEdges.length).toBe(0);

      // 대신 thinking→tool_call 엣지가 tool 개수만큼 있어야 함
      const branchEdges = edges.filter((e) => {
        const source = nodes.find((n) => n.id === e.source);
        const target = nodes.find((n) => n.id === e.target);
        return (source?.type === "thinking" || source?.type === "response") && target?.type === "tool_call";
      });
      expect(branchEdges.length).toBeGreaterThanOrEqual(toolCallNodes.length);
    });

    it("lastEventId가 마지막 이벤트 ID와 일치한다", () => {
      const { lastEventId, records } = replayFixture("multi-tool");
      expect(lastEventId).toBe(records[records.length - 1].id);
    });
  });

  // === complete-flow: complete 카드 + response 노드 중앙 정렬 ===

  describe("complete-flow: 세션 완료 + response 노드", () => {
    it("마지막 텍스트 카드가 response 노드로 변환된다", () => {
      const { cards, graphEvents } = replayFixture("complete-flow");
      const { nodes } = buildGraph(cards, graphEvents);

      const responseNodes = nodes.filter((n) => n.type === "response");
      expect(responseNodes).toHaveLength(1);
      expect(responseNodes[0].data.content).toContain("hello world function");
    });

    it("response 노드는 streaming=false 이다", () => {
      const { cards, graphEvents } = replayFixture("complete-flow");
      const { nodes } = buildGraph(cards, graphEvents);

      const responseNode = nodes.find((n) => n.type === "response")!;
      expect(responseNode.data.streaming).toBe(false);
    });

    it("complete system 노드가 그래프 끝에 위치한다", () => {
      const { cards, graphEvents } = replayFixture("complete-flow");
      const { nodes, edges } = buildGraph(cards, graphEvents);

      const completeNode = nodes.find(
        (n) => n.type === "system" && n.data.label === "Complete",
      );
      expect(completeNode).toBeDefined();

      // complete 노드에서 나가는 엣지가 없어야 함 (마지막 노드)
      const outgoing = edges.filter((e) => e.source === completeNode!.id);
      expect(outgoing).toHaveLength(0);
    });

    it("response 노드에서 complete 노드로의 엣지가 존재한다", () => {
      const { cards, graphEvents } = replayFixture("complete-flow");
      const { nodes, edges } = buildGraph(cards, graphEvents);

      const responseNode = nodes.find((n) => n.type === "response")!;
      const completeNode = nodes.find(
        (n) => n.type === "system" && n.data.label === "Complete",
      )!;

      const edge = edges.find(
        (e) => e.source === responseNode.id && e.target === completeNode.id,
      );
      expect(edge).toBeDefined();
    });

    it("전체 노드 수가 올바르다 (user + session + thinking + tool_call + tool_result + response + complete)", () => {
      const { cards, graphEvents } = replayFixture("complete-flow");
      const { nodes } = buildGraph(cards, graphEvents);

      // user(1) + session(1) + thinking(1) + tool_call(1) + tool_result(1) + response(1) + complete(1) = 7
      expect(nodes).toHaveLength(7);
    });

    it("dagre 레이아웃이 적용되어 모든 노드에 position이 설정된다", () => {
      const { cards, graphEvents } = replayFixture("complete-flow");
      const { nodes } = buildGraph(cards, graphEvents);

      for (const node of nodes) {
        expect(node.position).toBeDefined();
        expect(typeof node.position.x).toBe("number");
        expect(typeof node.position.y).toBe("number");
      }
    });
  });

  // === 공통 검증: 모든 픽스처 ===

  describe("공통: 모든 픽스처에 대한 기본 검증", () => {
    const fixtures = [
      "basic-flow",
      "tree-layout",
      "intervention-flow",
      "multi-tool",
      "complete-flow",
    ];

    for (const name of fixtures) {
      it(`${name}: buildGraph가 에러 없이 실행된다`, () => {
        useDashboardStore.getState().reset();
        const { cards, graphEvents } = replayFixture(name);
        expect(() => buildGraph(cards, graphEvents)).not.toThrow();
      });

      it(`${name}: 모든 노드에 유효한 id가 있다`, () => {
        useDashboardStore.getState().reset();
        const { cards, graphEvents } = replayFixture(name);
        const { nodes } = buildGraph(cards, graphEvents);
        for (const node of nodes) {
          expect(node.id).toBeTruthy();
          expect(typeof node.id).toBe("string");
        }
      });

      it(`${name}: 모든 엣지의 source/target이 존재하는 노드 ID이다`, () => {
        useDashboardStore.getState().reset();
        const { cards, graphEvents } = replayFixture(name);
        const { nodes, edges } = buildGraph(cards, graphEvents);
        const nodeIds = new Set(nodes.map((n) => n.id));
        for (const edge of edges) {
          expect(nodeIds.has(edge.source)).toBe(true);
          expect(nodeIds.has(edge.target)).toBe(true);
        }
      });

      it(`${name}: 엣지 ID가 고유하다`, () => {
        useDashboardStore.getState().reset();
        const { cards, graphEvents } = replayFixture(name);
        const { edges } = buildGraph(cards, graphEvents);
        const edgeIds = edges.map((e) => e.id);
        expect(new Set(edgeIds).size).toBe(edgeIds.length);
      });
    }
  });
});
