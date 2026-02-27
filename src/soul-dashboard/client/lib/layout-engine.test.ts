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
  parentCardId?: string,
): DashboardCard {
  return {
    cardId: id,
    type: "tool",
    content: "",
    toolName,
    toolInput: { prompt: "test" },
    toolResult,
    completed,
    parentCardId,
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

  describe("도구 그룹핑 (Phase 2)", () => {
    it("같은 parent + 같은 toolName 5개 → 1개 그룹 노드", () => {
      const cards: DashboardCard[] = [
        makeTextCard("t1", "Thinking"),
        makeToolCard("r1", "Read", true, "content1", "t1"),
        makeToolCard("r2", "Read", true, "content2", "t1"),
        makeToolCard("r3", "Read", true, "content3", "t1"),
        makeToolCard("r4", "Read", true, "content4", "t1"),
        makeToolCard("r5", "Read", true, "content5", "t1"),
      ];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "s1" },
      ];

      const { nodes } = buildGraph(cards, events);

      // tool_group 노드가 1개 생성되어야 함
      const groupNodes = nodes.filter((n) => n.type === "tool_group");
      expect(groupNodes).toHaveLength(1);

      // 그룹 노드의 label에 횟수가 포함
      expect(groupNodes[0].data.label).toContain("Read");
      expect(groupNodes[0].data.label).toContain("5");

      // groupedCardIds에 5개 카드 ID가 포함
      expect(groupNodes[0].data.groupedCardIds).toHaveLength(5);
      expect(groupNodes[0].data.groupedCardIds).toContain("r1");
      expect(groupNodes[0].data.groupedCardIds).toContain("r5");
      expect(groupNodes[0].data.groupCount).toBe(5);

      // 개별 tool_call 노드는 없어야 함
      const callNodes = nodes.filter((n) => n.type === "tool_call");
      expect(callNodes).toHaveLength(0);

      // tool_result 노드도 없어야 함
      const resultNodes = nodes.filter((n) => n.type === "tool_result");
      expect(resultNodes).toHaveLength(0);
    });

    it("1개 도구는 그룹화하지 않고 개별 노드 유지", () => {
      const cards: DashboardCard[] = [
        makeTextCard("t1", "Thinking"),
        makeToolCard("r1", "Read", true, "content1", "t1"),
      ];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "s1" },
      ];

      const { nodes } = buildGraph(cards, events);

      // tool_group 노드 없음
      expect(nodes.filter((n) => n.type === "tool_group")).toHaveLength(0);
      // 개별 tool_call 노드 1개
      expect(nodes.filter((n) => n.type === "tool_call")).toHaveLength(1);
    });

    it("다른 toolName은 별도 그룹으로 분리", () => {
      const cards: DashboardCard[] = [
        makeTextCard("t1", "Thinking"),
        makeToolCard("r1", "Read", true, "c1", "t1"),
        makeToolCard("r2", "Read", true, "c2", "t1"),
        makeToolCard("b1", "Bash", true, "c3", "t1"),
        makeToolCard("b2", "Bash", true, "c4", "t1"),
        makeToolCard("s1", "Skill", true, "c5", "t1"), // 1개 → 개별 노드
      ];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "s1" },
      ];

      const { nodes } = buildGraph(cards, events);

      const groupNodes = nodes.filter((n) => n.type === "tool_group");
      expect(groupNodes).toHaveLength(2); // Read×2, Bash×2

      const callNodes = nodes.filter((n) => n.type === "tool_call");
      expect(callNodes).toHaveLength(1); // Skill×1
    });

    it("그룹 노드의 groupedCardIds가 원본 카드 ID를 모두 포함", () => {
      const cards: DashboardCard[] = [
        makeTextCard("t1", "Thinking"),
        makeToolCard("r1", "Read", true, "c1", "t1"),
        makeToolCard("r2", "Read", true, "c2", "t1"),
        makeToolCard("r3", "Read", true, "c3", "t1"),
      ];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "s1" },
      ];

      const { nodes } = buildGraph(cards, events);

      const groupNode = nodes.find((n) => n.type === "tool_group");
      expect(groupNode).toBeDefined();
      expect(groupNode!.data.groupedCardIds).toEqual(["r1", "r2", "r3"]);
    });
  });

  describe("고아 노드 연결 (Phase 3)", () => {
    it("parentCardId 없는 도구가 lastThinkingNodeId에 연결", () => {
      const cards: DashboardCard[] = [
        makeTextCard("t1", "Thinking"),
        makeToolCard("tool1", "Read", true, "content"),
        // parentCardId 없음 → lastThinkingNodeId(t1)에 연결
      ];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "s1" },
      ];

      const { edges } = buildGraph(cards, events);

      // tool_call이 thinking 노드에 연결되어 있는지
      const thinkingToTool = edges.find(
        (e) => e.source === "node-t1" && e.target === "node-tool1-call",
      );
      expect(thinkingToTool).toBeDefined();
    });
  });

  describe("가상 thinking 노드 (Phase 4)", () => {
    it("첫 text 카드 전에 tool 카드가 있으면 가상 thinking 노드 삽입", () => {
      const cards: DashboardCard[] = [
        makeToolCard("tool1", "Read", true, "content1"),
        makeToolCard("tool2", "Bash", true, "content2"),
        makeTextCard("t1", "Now thinking"),
      ];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "s1" },
      ];

      const { nodes, edges } = buildGraph(cards, events);

      // 가상 thinking 노드가 생성되어야 함
      const virtualNode = nodes.find((n) => n.id === "node-virtual-init");
      expect(virtualNode).toBeDefined();
      expect(virtualNode!.type).toBe("thinking");
      expect(virtualNode!.data.label).toBe("Initial Tools");

      // 가상 thinking 노드가 메인 플로우에 연결
      const sessionToVirtual = edges.find(
        (e) => e.target === "node-virtual-init",
      );
      expect(sessionToVirtual).toBeDefined();

      // 도구 노드가 가상 thinking에 연결
      const virtualToTool = edges.find(
        (e) => e.source === "node-virtual-init",
      );
      expect(virtualToTool).toBeDefined();
    });

    it("첫 카드가 text이면 가상 thinking 노드 없음", () => {
      const cards: DashboardCard[] = [
        makeTextCard("t1", "Thinking first"),
        makeToolCard("tool1", "Read", true, "content"),
      ];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "s1" },
      ];

      const { nodes } = buildGraph(cards, events);

      const virtualNode = nodes.find((n) => n.id === "node-virtual-init");
      expect(virtualNode).toBeUndefined();
    });

    it("고아 도구 그룹이 가상 thinking에 연결", () => {
      const cards: DashboardCard[] = [
        // 3개 orphan Read → 그룹 노드
        makeToolCard("r1", "Read", true, "c1"),
        makeToolCard("r2", "Read", true, "c2"),
        makeToolCard("r3", "Read", true, "c3"),
        makeTextCard("t1", "Now thinking"),
      ];
      const events: SoulSSEEvent[] = [
        { type: "session", session_id: "s1" },
      ];

      const { nodes, edges } = buildGraph(cards, events);

      // 가상 thinking 노드
      const virtualNode = nodes.find((n) => n.id === "node-virtual-init");
      expect(virtualNode).toBeDefined();

      // 그룹 노드
      const groupNode = nodes.find((n) => n.type === "tool_group");
      expect(groupNode).toBeDefined();
      expect(groupNode!.data.groupCount).toBe(3);

      // 가상 thinking → 그룹 노드 엣지
      const virtualToGroup = edges.find(
        (e) => e.source === "node-virtual-init" && e.target === groupNode!.id,
      );
      expect(virtualToGroup).toBeDefined();
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
