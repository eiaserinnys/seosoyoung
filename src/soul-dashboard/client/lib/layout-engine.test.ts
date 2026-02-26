/**
 * Layout Engine Tests
 *
 * buildGraph()의 user/intervention 노드 생성 및 배치를 검증합니다.
 */

import { describe, it, expect } from "vitest";
import { buildGraph } from "./layout-engine";
import type { DashboardCard, SoulSSEEvent } from "@shared/types";

// === Helpers ===

function makeTextCard(id: string, content: string, completed = true): DashboardCard {
  return { cardId: id, type: "text", content, completed };
}

function makeToolCard(
  id: string,
  toolName: string,
  completed = true,
  toolResult?: string,
): DashboardCard {
  return {
    cardId: id,
    type: "tool",
    content: "",
    toolName,
    toolInput: { prompt: "test" },
    toolResult,
    completed,
  };
}

// === Tests ===

describe("buildGraph", () => {
  describe("user_message 노드", () => {
    it("user_message 이벤트가 있으면 첫 번째 노드로 배치", () => {
      const cards: DashboardCard[] = [makeTextCard("t1", "Hello")];
      const events: SoulSSEEvent[] = [
        { type: "user_message", user: "dashboard", text: "안녕하세요" },
        { type: "session", session_id: "abc123" },
      ];

      const { nodes, edges } = buildGraph(cards, events);

      // user 노드가 첫 번째
      expect(nodes[0].type).toBe("user");
      expect(nodes[0].data.nodeType).toBe("user");
      expect(nodes[0].data.content).toBe("안녕하세요");
      expect(nodes[0].data.label).toContain("dashboard");

      // session system 노드가 두 번째
      expect(nodes[1].type).toBe("system");
      expect(nodes[1].data.label).toBe("Session Started");

      // user → system 엣지
      const userToSystemEdge = edges.find(
        (e) => e.source === nodes[0].id && e.target === nodes[1].id,
      );
      expect(userToSystemEdge).toBeDefined();
    });

    it("user_message 이벤트가 없으면 user 노드 없이 시작", () => {
      const cards: DashboardCard[] = [makeTextCard("t1", "Hello")];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "abc123" },
      ];

      const { nodes } = buildGraph(cards, events);

      // 첫 번째 노드는 system
      expect(nodes[0].type).toBe("system");
      expect(nodes.find((n) => n.type === "user")).toBeUndefined();
    });

    it("user_message의 긴 텍스트는 120자로 잘림", () => {
      const longText = "a".repeat(200);
      const events: SoulSSEEvent[] = [
        { type: "user_message", user: "test", text: longText },
      ];

      const { nodes } = buildGraph([], events);
      const userNode = nodes.find((n) => n.type === "user");
      expect(userNode).toBeDefined();
      expect(userNode!.data.content).toHaveLength(120);
      expect(userNode!.data.content.endsWith("...")).toBe(true);
      // fullContent는 전체 텍스트
      expect(userNode!.data.fullContent).toBe(longText);
    });

    it("user_message → session → thinking 순서로 연결", () => {
      const cards: DashboardCard[] = [makeTextCard("t1", "Thinking...")];
      const events: SoulSSEEvent[] = [
        { type: "user_message", user: "dashboard", text: "Do something" },
        { type: "session", session_id: "s1" },
      ];

      const { nodes, edges } = buildGraph(cards, events);

      const userNode = nodes.find((n) => n.type === "user")!;
      const sessionNode = nodes.find((n) => n.type === "system")!;
      const thinkingNode = nodes.find((n) => n.type === "thinking" || n.type === "response")!;

      // user → session 엣지
      expect(edges.find((e) => e.source === userNode.id && e.target === sessionNode.id)).toBeDefined();
      // session → thinking 엣지
      expect(edges.find((e) => e.source === sessionNode.id && e.target === thinkingNode.id)).toBeDefined();
    });
  });

  describe("intervention 노드", () => {
    it("intervention_sent 이벤트가 intervention 노드를 생성", () => {
      const cards: DashboardCard[] = [
        makeTextCard("t1", "First thinking"),
        makeTextCard("t2", "Second thinking"),
      ];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "s1" },
        { type: "intervention_sent", user: "human", text: "Stop!" },
      ];

      const { nodes } = buildGraph(cards, events);

      const interventionNode = nodes.find((n) => n.type === "intervention");
      expect(interventionNode).toBeDefined();
      expect(interventionNode!.data.nodeType).toBe("intervention");
      expect(interventionNode!.data.content).toBe("Stop!");
      expect(interventionNode!.data.label).toContain("human");
    });

    it("intervention 노드의 긴 텍스트는 120자로 잘림 + fullContent 보존", () => {
      const longText = "b".repeat(200);
      const events: SoulSSEEvent[] = [
        { type: "intervention_sent", user: "human", text: longText },
      ];

      const { nodes } = buildGraph([], events);
      const intvNode = nodes.find((n) => n.type === "intervention");
      expect(intvNode).toBeDefined();
      expect(intvNode!.data.content).toHaveLength(120);
      expect(intvNode!.data.fullContent).toBe(longText);
    });

    it("intervention 노드는 메인 플로우에 삽입", () => {
      const cards: DashboardCard[] = [makeTextCard("t1", "Thinking")];
      const events: SoulSSEEvent[] = [
        { type: "intervention_sent", user: "human", text: "Hey" },
      ];

      const { nodes, edges } = buildGraph(cards, events);

      const interventionNode = nodes.find((n) => n.type === "intervention")!;

      // intervention이 어떤 노드와 연결되어 있는지 확인
      const connectedEdges = edges.filter(
        (e) => e.source === interventionNode.id || e.target === interventionNode.id,
      );
      expect(connectedEdges.length).toBeGreaterThan(0);
    });
  });

  describe("user_message + intervention 복합 시나리오", () => {
    it("전체 세션 플로우: user → session → thinking → intervention → thinking → complete", () => {
      const cards: DashboardCard[] = [
        makeTextCard("t1", "First response"),
        makeToolCard("tool1", "Read", true, "file contents"),
        makeTextCard("t2", "Final response"),
      ];
      const events: SoulSSEEvent[] = [
        { type: "user_message", user: "dashboard", text: "Analyze this" },
        { type: "session", session_id: "s1" },
        { type: "intervention_sent", user: "dashboard", text: "Also check X" },
        { type: "complete", result: "Done", attachments: [] },
      ];

      const { nodes, edges } = buildGraph(cards, events);

      // 노드 타입 확인
      const nodeTypes = nodes.map((n) => n.type);
      expect(nodeTypes).toContain("user");
      expect(nodeTypes).toContain("system"); // session + complete
      expect(nodeTypes).toContain("intervention");
      expect(nodeTypes).toContain("tool_call");

      // user가 첫 번째
      expect(nodes[0].type).toBe("user");

      // 그래프가 연결되어 있는지 (엣지 수 > 0)
      expect(edges.length).toBeGreaterThan(0);
    });
  });
});
