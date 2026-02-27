/**
 * layout-engine 테스트
 *
 * buildGraph, applyDagreLayout, detectSubAgents, createEdge 함수를 테스트합니다.
 */

import { describe, it, expect } from "vitest";
import type { DashboardCard, SoulSSEEvent } from "@shared/types";
import {
  buildGraph,
  applyDagreLayout,
  detectSubAgents,
  createEdge,
  getNodeDimensions,
  calcToolChainBounds,
  type GraphNode,
  type ToolChainEntry,
} from "../../src/soul-dashboard/client/lib/layout-engine";

// === Helper: 카드 팩토리 ===

function textCard(
  cardId: string,
  content: string,
  completed = true,
): DashboardCard {
  return { cardId, type: "text", content, completed };
}

function toolCard(
  cardId: string,
  toolName: string,
  opts: Partial<DashboardCard> = {},
): DashboardCard {
  return {
    cardId,
    type: "tool",
    content: "",
    toolName,
    toolInput: opts.toolInput ?? { command: "test" },
    toolResult: opts.toolResult,
    isError: opts.isError,
    completed: opts.completed ?? true,
    parentCardId: opts.parentCardId,
  };
}

// === Tests ===

describe("getNodeDimensions", () => {
  it("returns correct dimensions for each node type", () => {
    expect(getNodeDimensions("thinking")).toEqual({ width: 260, height: 84 });
    expect(getNodeDimensions("tool_call")).toEqual({ width: 260, height: 84 });
    expect(getNodeDimensions("system")).toEqual({ width: 260, height: 84 });
    expect(getNodeDimensions("group")).toEqual({ width: 320, height: 100 });
  });
});

describe("createEdge", () => {
  it("creates an edge with correct source and target", () => {
    const edge = createEdge("a", "b");
    expect(edge.source).toBe("a");
    expect(edge.target).toBe("b");
    expect(edge.animated).toBe(false);
    expect(edge.id).toContain("e-a-b");
  });

  it("supports animated edges", () => {
    const edge = createEdge("a", "b", true);
    expect(edge.animated).toBe(true);
  });

  it("supports custom handle IDs", () => {
    const edge = createEdge("a", "b", false, "right", "left");
    expect(edge.sourceHandle).toBe("right");
    expect(edge.targetHandle).toBe("left");
  });

  it("generates deterministic unique IDs (no module-level counter)", () => {
    const e1 = createEdge("a", "b");
    const e2 = createEdge("a", "b");
    // Same source/target without handles → same ID (deterministic)
    expect(e1.id).toBe(e2.id);

    // Different handles → different ID
    const e3 = createEdge("a", "b", false, "right", "left");
    expect(e3.id).not.toBe(e1.id);
  });
});

describe("detectSubAgents", () => {
  it("returns empty array when no Task tools", () => {
    const cards = [
      textCard("t1", "hello"),
      toolCard("tool1", "Bash"),
    ];
    expect(detectSubAgents(cards)).toEqual([]);
  });

  it("detects a single sub-agent group from Task tool", () => {
    const cards = [
      textCard("t1", "start"),
      toolCard("task1", "Task", {
        toolInput: { description: "Explore codebase", prompt: "..." },
        completed: true,
      }),
      textCard("t2", "after task"),
    ];

    const groups = detectSubAgents(cards);
    expect(groups).toHaveLength(1);
    expect(groups[0].taskCardId).toBe("task1");
    expect(groups[0].cardIds).toContain("task1");
    // After a completed Task, the next card before another Task is included
    expect(groups[0].cardIds).toContain("t2");
    expect(groups[0].label).toContain("Explore codebase");
  });

  it("detects running (incomplete) Task as sub-agent group", () => {
    const cards = [
      toolCard("task1", "Task", {
        toolInput: { description: "Long running task" },
        completed: false,
      }),
      textCard("t1", "child1", false),
      toolCard("tool1", "Bash", { completed: false }),
    ];

    const groups = detectSubAgents(cards);
    expect(groups).toHaveLength(1);
    // Running Task includes all subsequent cards
    expect(groups[0].cardIds).toEqual(["task1", "t1", "tool1"]);
  });

  it("truncates long task descriptions", () => {
    const longDesc = "A".repeat(100);
    const cards = [
      toolCard("task1", "Task", {
        toolInput: { description: longDesc },
        completed: true,
      }),
    ];

    const groups = detectSubAgents(cards);
    expect(groups[0].label.length).toBeLessThanOrEqual(50);
    expect(groups[0].label).toContain("...");
  });
});

describe("buildGraph", () => {
  it("returns empty graph for empty inputs", () => {
    const result = buildGraph([], []);
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
  });

  it("creates thinking node for text card", () => {
    const cards = [textCard("t1", "Hello world")];
    const events: SoulSSEEvent[] = [];

    const { nodes, edges } = buildGraph(cards, events);

    // Should have one thinking node (not response, since no complete event)
    const thinkingNodes = nodes.filter((n) => n.type === "thinking");
    expect(thinkingNodes).toHaveLength(1);
    expect(thinkingNodes[0].data.content).toContain("Hello world");
    expect(thinkingNodes[0].data.cardId).toBe("t1");
  });

  it("creates response node for last text card when session is complete", () => {
    const cards = [
      textCard("t1", "Thinking..."),
      textCard("t2", "Final response"),
    ];
    const events: SoulSSEEvent[] = [
      { type: "complete", result: "done", attachments: [] },
    ];

    const { nodes } = buildGraph(cards, events);

    const responseNodes = nodes.filter((n) => n.type === "response");
    expect(responseNodes).toHaveLength(1);
    expect(responseNodes[0].data.cardId).toBe("t2");

    const thinkingNodes = nodes.filter((n) => n.type === "thinking");
    expect(thinkingNodes).toHaveLength(1);
    expect(thinkingNodes[0].data.cardId).toBe("t1");
  });

  it("creates tool_call and tool_result nodes for tool card", () => {
    const cards = [
      toolCard("tool1", "Bash", {
        toolInput: { command: "ls" },
        toolResult: "file1.txt\nfile2.txt",
        completed: true,
      }),
    ];
    const events: SoulSSEEvent[] = [];

    const { nodes, edges } = buildGraph(cards, events);

    const callNodes = nodes.filter((n) => n.type === "tool_call");
    expect(callNodes).toHaveLength(1);
    expect(callNodes[0].data.toolName).toBe("Bash");

    const resultNodes = nodes.filter((n) => n.type === "tool_result");
    expect(resultNodes).toHaveLength(1);
    expect(resultNodes[0].data.toolResult).toContain("file1.txt");

    // Should have horizontal edge from call to result (right→left)
    const callToResult = edges.find(
      (e) => e.source === "node-tool1-call" && e.target === "node-tool1-result",
    );
    expect(callToResult).toBeDefined();
    expect(callToResult!.sourceHandle).toBe("right");
    expect(callToResult!.targetHandle).toBe("left");
  });

  it("tool_result node includes cardId for DetailView selection", () => {
    const cards = [
      toolCard("tool1", "Bash", {
        toolInput: { command: "ls" },
        toolResult: "output",
        completed: true,
      }),
    ];
    const events: SoulSSEEvent[] = [];

    const { nodes } = buildGraph(cards, events);

    const resultNode = nodes.find((n) => n.type === "tool_result");
    expect(resultNode).toBeDefined();
    expect(resultNode!.data.cardId).toBe("tool1");
  });

  it("empty tool_result node includes cardId for DetailView selection", () => {
    // 결과 없이 완료된 경우 (빈 결과)
    const cards = [
      toolCard("tool1", "Bash", {
        toolInput: { command: "echo" },
        toolResult: undefined,
        completed: true,
      }),
    ];
    const events: SoulSSEEvent[] = [];

    const { nodes } = buildGraph(cards, events);

    const resultNode = nodes.find((n) => n.type === "tool_result");
    expect(resultNode).toBeDefined();
    expect(resultNode!.data.cardId).toBe("tool1");
  });

  it("creates system nodes for session and complete events", () => {
    const cards = [textCard("t1", "hello")];
    const events: SoulSSEEvent[] = [
      { type: "session", session_id: "test-session-123" },
      { type: "complete", result: "done", attachments: [] },
    ];

    const { nodes } = buildGraph(cards, events);

    const systemNodes = nodes.filter((n) => n.type === "system");
    expect(systemNodes).toHaveLength(2);

    const sessionNode = systemNodes.find((n) =>
      n.data.label.includes("Session"),
    );
    expect(sessionNode).toBeDefined();

    const completeNode = systemNodes.find((n) =>
      n.data.label.includes("Complete"),
    );
    expect(completeNode).toBeDefined();
  });

  it("creates intervention nodes from intervention_sent events", () => {
    const cards = [textCard("t1", "before"), textCard("t2", "after")];
    const events: SoulSSEEvent[] = [
      { type: "intervention_sent", user: "test_user", text: "stop that" },
    ];

    const { nodes } = buildGraph(cards, events);

    const interventionNodes = nodes.filter((n) => n.type === "intervention");
    expect(interventionNodes).toHaveLength(1);
    expect(interventionNodes[0].data.content).toContain("stop that");
  });

  it("marks streaming nodes correctly", () => {
    const cards = [
      textCard("t1", "partial", false), // not completed = streaming
      toolCard("tool1", "Read", { completed: false }), // not completed = streaming
    ];
    const events: SoulSSEEvent[] = [];

    const { nodes } = buildGraph(cards, events);

    const textNode = nodes.find((n) => n.data.cardId === "t1");
    expect(textNode?.data.streaming).toBe(true);

    const toolNode = nodes.find(
      (n) => n.data.cardId === "tool1" && n.type === "tool_call",
    );
    expect(toolNode?.data.streaming).toBe(true);
  });

  it("creates sequential edges between nodes", () => {
    const cards = [
      textCard("t1", "first"),
      toolCard("tool1", "Bash", {
        toolResult: "ok",
        completed: true,
      }),
      textCard("t2", "last"),
    ];
    const events: SoulSSEEvent[] = [];

    const { edges } = buildGraph(cards, events);

    // Tree layout: t1 -horizontal-> tool_call, tool_call -> tool_result, t1 -vertical-> t2
    expect(edges.length).toBeGreaterThanOrEqual(3);
  });

  // === 트리 뷰 레이아웃 구조 검증 ===

  describe("tree view layout (thinking→tool horizontal branch)", () => {
    it("thinking→tool_call uses horizontal edge (right→left)", () => {
      const cards = [
        textCard("t1", "thinking about tools"),
        toolCard("tool1", "Bash", {
          toolResult: "ok",
          completed: true,
        }),
      ];
      const events: SoulSSEEvent[] = [];

      const { edges } = buildGraph(cards, events);

      // thinking→tool_call should use right→left handles
      const thinkingToTool = edges.find(
        (e) => e.source === "node-t1" && e.target === "node-tool1-call",
      );
      expect(thinkingToTool).toBeDefined();
      expect(thinkingToTool!.sourceHandle).toBe("right");
      expect(thinkingToTool!.targetHandle).toBe("left");
    });

    it("thinking→thinking uses vertical edge (no handles)", () => {
      const cards = [
        textCard("t1", "first thinking"),
        toolCard("tool1", "Bash", {
          toolResult: "ok",
          completed: true,
        }),
        textCard("t2", "second thinking"),
      ];
      const events: SoulSSEEvent[] = [];

      const { edges } = buildGraph(cards, events);

      // t1→t2 should be vertical (no handles / default)
      const thinkingToThinking = edges.find(
        (e) => e.source === "node-t1" && e.target === "node-t2",
      );
      expect(thinkingToThinking).toBeDefined();
      expect(thinkingToThinking!.sourceHandle).toBeUndefined();
      expect(thinkingToThinking!.targetHandle).toBeUndefined();
    });

    it("tool nodes do NOT participate in main vertical chain", () => {
      // Scenario: thinking → tool → thinking → response
      // Main flow: t1 → t2 (vertical)
      // Tool branch: t1 → tool1 (horizontal)
      const cards = [
        textCard("t1", "first"),
        toolCard("tool1", "Bash", {
          toolResult: "ok",
          completed: true,
        }),
        textCard("t2", "second"),
      ];
      const events: SoulSSEEvent[] = [];

      const { edges } = buildGraph(cards, events);

      // NO vertical edge from tool_result to t2
      const resultToThinking = edges.find(
        (e) => e.source === "node-tool1-result" && e.target === "node-t2",
      );
      expect(resultToThinking).toBeUndefined();

      // Instead, t1→t2 should be directly connected vertically
      const t1ToT2 = edges.find(
        (e) => e.source === "node-t1" && e.target === "node-t2",
      );
      expect(t1ToT2).toBeDefined();
    });

    it("multiple tools from same thinking chain horizontally", () => {
      // thinking → toolA → toolB
      // t1 -right→ toolA -right→ toolB
      const cards = [
        textCard("t1", "thinking"),
        toolCard("toolA", "Bash", {
          toolResult: "ok",
          completed: true,
        }),
        toolCard("toolB", "Read", {
          toolResult: "content",
          completed: true,
        }),
        textCard("t2", "next"),
      ];
      const events: SoulSSEEvent[] = [];

      const { edges } = buildGraph(cards, events);

      // t1→toolA: horizontal
      const t1ToA = edges.find(
        (e) => e.source === "node-t1" && e.target === "node-toolA-call",
      );
      expect(t1ToA).toBeDefined();
      expect(t1ToA!.sourceHandle).toBe("right");

      // toolB도 thinking(t1)에서 수평 분기 (트리뷰: right→left)
      const t1ToB = edges.find(
        (e) => e.source === "node-t1" && e.target === "node-toolB-call",
      );
      expect(t1ToB).toBeDefined();
      expect(t1ToB!.sourceHandle).toBe("right");
      expect(t1ToB!.targetHandle).toBe("left");

      // t1→t2: vertical (main flow)
      const t1ToT2 = edges.find(
        (e) => e.source === "node-t1" && e.target === "node-t2",
      );
      expect(t1ToT2).toBeDefined();
      expect(t1ToT2!.sourceHandle).toBeUndefined();
    });

    it("tool_call→tool_result uses horizontal edge (right→left)", () => {
      const cards = [
        textCard("t1", "thinking"),
        toolCard("tool1", "Bash", {
          toolResult: "ok",
          completed: true,
        }),
      ];
      const events: SoulSSEEvent[] = [];

      const { edges } = buildGraph(cards, events);

      // tool_call→tool_result should be horizontal (right→left)
      const callToResult = edges.find(
        (e) => e.source === "node-tool1-call" && e.target === "node-tool1-result",
      );
      expect(callToResult).toBeDefined();
      expect(callToResult!.sourceHandle).toBe("right");
      expect(callToResult!.targetHandle).toBe("left");
    });

    it("complex scenario: thinking→tool→thinking→tool→response", () => {
      // Full tree:
      //   [t1]  ──→  [toolA-call]
      //    │              │
      //    │         [toolA-result]
      //    ▼
      //   [t2]  ──→  [toolB-call]
      //    │              │
      //    │         [toolB-result]
      //    ▼
      //   [t3] (response)
      const cards = [
        textCard("t1", "first thinking"),
        toolCard("toolA", "Bash", { toolResult: "ok", completed: true }),
        textCard("t2", "second thinking"),
        toolCard("toolB", "Read", { toolResult: "file", completed: true }),
        textCard("t3", "final response"),
      ];
      const events: SoulSSEEvent[] = [
        { type: "complete", result: "done", attachments: [] },
      ];

      const { nodes, edges } = buildGraph(cards, events);

      // Main vertical chain: t1 → t2 → t3
      expect(edges.find((e) => e.source === "node-t1" && e.target === "node-t2")).toBeDefined();
      expect(edges.find((e) => e.source === "node-t2" && e.target === "node-t3")).toBeDefined();

      // Horizontal branches: t1→toolA, t2→toolB
      const t1ToA = edges.find((e) => e.source === "node-t1" && e.target === "node-toolA-call");
      expect(t1ToA).toBeDefined();
      expect(t1ToA!.sourceHandle).toBe("right");

      const t2ToB = edges.find((e) => e.source === "node-t2" && e.target === "node-toolB-call");
      expect(t2ToB).toBeDefined();
      expect(t2ToB!.sourceHandle).toBe("right");

      // Horizontal tool results (right→left)
      const aResult = edges.find((e) => e.source === "node-toolA-call" && e.target === "node-toolA-result");
      expect(aResult).toBeDefined();
      expect(aResult!.sourceHandle).toBe("right");
      expect(aResult!.targetHandle).toBe("left");

      const bResult = edges.find((e) => e.source === "node-toolB-call" && e.target === "node-toolB-result");
      expect(bResult).toBeDefined();
      expect(bResult!.sourceHandle).toBe("right");
      expect(bResult!.targetHandle).toBe("left");

      // t3 should be response node
      const responseNode = nodes.find((n) => n.id === "node-t3");
      expect(responseNode?.type).toBe("response");

      // No tool→thinking vertical edges
      expect(edges.find((e) => e.source === "node-toolA-result" && e.target === "node-t2")).toBeUndefined();
      expect(edges.find((e) => e.source === "node-toolB-result" && e.target === "node-t3")).toBeUndefined();
    });

    it("tool without preceding thinking attaches to prevMainNode", () => {
      // Edge case: first card is a tool (no thinking before it)
      const cards = [
        toolCard("tool1", "Bash", { toolResult: "ok", completed: true }),
        textCard("t1", "after tool"),
      ];
      const events: SoulSSEEvent[] = [];

      const { edges } = buildGraph(cards, events);

      // No tool→thinking vertical connection
      const toolToThinking = edges.find(
        (e) => e.source === "node-tool1-result" && e.target === "node-t1",
      );
      expect(toolToThinking).toBeUndefined();
    });

    it("streaming tool (no result yet) still branches horizontally", () => {
      const cards = [
        textCard("t1", "thinking"),
        toolCard("tool1", "Bash", { completed: false }),
      ];
      const events: SoulSSEEvent[] = [];

      const { edges } = buildGraph(cards, events);

      // t1→tool1-call horizontal
      const t1ToTool = edges.find(
        (e) => e.source === "node-t1" && e.target === "node-tool1-call",
      );
      expect(t1ToTool).toBeDefined();
      expect(t1ToTool!.sourceHandle).toBe("right");
    });
  });

  it("ignores noise events (progress, debug, memory)", () => {
    const cards = [textCard("t1", "hello")];
    const events: SoulSSEEvent[] = [
      { type: "progress", text: "Loading..." },
      { type: "debug", message: "Debug info" },
      { type: "memory", used_gb: 4, total_gb: 16, percent: 25 },
    ];

    const { nodes } = buildGraph(cards, events);

    const systemNodes = nodes.filter((n) => n.type === "system");
    expect(systemNodes).toHaveLength(0);
  });
});

describe("buildGraph layout: tool nodes positioned to the right of thinking", () => {
  it("tool_call node is positioned to the right of its parent thinking node", () => {
    const cards = [
      textCard("t1", "thinking about tools"),
      toolCard("tool1", "Bash", {
        toolResult: "ok",
        completed: true,
      }),
      textCard("t2", "next thinking"),
    ];
    const events: SoulSSEEvent[] = [];

    const { nodes } = buildGraph(cards, events);

    const thinkingNode = nodes.find((n) => n.id === "node-t1")!;
    const toolCallNode = nodes.find((n) => n.id === "node-tool1-call")!;

    // tool_call should be to the right of thinking
    expect(toolCallNode.position.x).toBeGreaterThan(thinkingNode.position.x);
  });

  it("tool_result is to the right of its tool_call (same y)", () => {
    const cards = [
      textCard("t1", "thinking"),
      toolCard("tool1", "Bash", {
        toolResult: "output",
        completed: true,
      }),
    ];
    const events: SoulSSEEvent[] = [];

    const { nodes } = buildGraph(cards, events);

    const toolCallNode = nodes.find((n) => n.id === "node-tool1-call")!;
    const toolResultNode = nodes.find((n) => n.id === "node-tool1-result")!;

    // result should be to the right of call (same y, greater x)
    expect(toolResultNode.position.x).toBeGreaterThan(toolCallNode.position.x);
    expect(toolResultNode.position.y).toBe(toolCallNode.position.y);
  });

  it("second thinking node is below first thinking node (not pushed down by tools)", () => {
    const cards = [
      textCard("t1", "first"),
      toolCard("tool1", "Bash", { toolResult: "ok", completed: true }),
      toolCard("tool2", "Read", { toolResult: "content", completed: true }),
      textCard("t2", "second"),
    ];
    const events: SoulSSEEvent[] = [];

    const { nodes } = buildGraph(cards, events);

    const t1 = nodes.find((n) => n.id === "node-t1")!;
    const t2 = nodes.find((n) => n.id === "node-t2")!;

    // t2 should be below t1
    expect(t2.position.y).toBeGreaterThan(t1.position.y);
  });

  it("multiple tool chains are stacked vertically to the right", () => {
    // thinking → toolA → toolB (chained)
    // Each tool_call is at the same x as the first, but stacked vertically
    const cards = [
      textCard("t1", "thinking"),
      toolCard("toolA", "Bash", { toolResult: "ok", completed: true }),
      toolCard("toolB", "Read", { toolResult: "content", completed: true }),
      textCard("t2", "next"),
    ];
    const events: SoulSSEEvent[] = [];

    const { nodes } = buildGraph(cards, events);

    const t1 = nodes.find((n) => n.id === "node-t1")!;
    const toolA = nodes.find((n) => n.id === "node-toolA-call")!;
    const toolB = nodes.find((n) => n.id === "node-toolB-call")!;

    // Both tools should be to the right of thinking
    expect(toolA.position.x).toBeGreaterThan(t1.position.x);
    expect(toolB.position.x).toBeGreaterThan(t1.position.x);

    // toolB should be below toolA (vertical stacking)
    expect(toolB.position.y).toBeGreaterThan(toolA.position.y);
  });

  it("thinking node dagre height accounts for tool chain height (no overlap)", () => {
    // When thinking has a large tool chain, the next thinking should not overlap with tools
    const cards = [
      textCard("t1", "first"),
      toolCard("toolA", "Bash", { toolResult: "ok", completed: true }),
      toolCard("toolB", "Read", { toolResult: "content", completed: true }),
      toolCard("toolC", "Glob", { toolResult: "files", completed: true }),
      textCard("t2", "second"),
    ];
    const events: SoulSSEEvent[] = [];

    const { nodes } = buildGraph(cards, events);

    const t1 = nodes.find((n) => n.id === "node-t1")!;
    const t2 = nodes.find((n) => n.id === "node-t2")!;

    // t2 should be significantly below t1 (at least the height of 3 tool rows + gaps)
    // 3 tools * 80px + 2 gaps * 16px = 272px minimum vertical separation
    const minSeparation = 3 * 80 + 2 * 16; // 272
    expect(t2.position.y - t1.position.y).toBeGreaterThanOrEqual(minSeparation);
  });
});

// === 도구 그룹핑 / 고아 노드 / 가상 thinking 테스트 ===

describe("tool grouping (Phase 2)", () => {
  it("같은 parent + 같은 toolName 5개 → 1개 tool_group 노드", () => {
    const cards: DashboardCard[] = [
      textCard("t1", "Thinking"),
      toolCard("r1", "Read", { toolResult: "c1", completed: true, parentCardId: "t1" }),
      toolCard("r2", "Read", { toolResult: "c2", completed: true, parentCardId: "t1" }),
      toolCard("r3", "Read", { toolResult: "c3", completed: true, parentCardId: "t1" }),
      toolCard("r4", "Read", { toolResult: "c4", completed: true, parentCardId: "t1" }),
      toolCard("r5", "Read", { toolResult: "c5", completed: true, parentCardId: "t1" }),
    ];
    const events: SoulSSEEvent[] = [{ type: "session", session_id: "s1" }];
    const { nodes } = buildGraph(cards, events);

    const groupNodes = nodes.filter((n) => n.type === "tool_group");
    expect(groupNodes).toHaveLength(1);
    expect(groupNodes[0].data.label).toContain("Read");
    expect(groupNodes[0].data.label).toContain("5");
    expect(groupNodes[0].data.groupedCardIds).toHaveLength(5);
    expect(groupNodes[0].data.groupCount).toBe(5);

    // 개별 tool_call/tool_result 없음
    expect(nodes.filter((n) => n.type === "tool_call")).toHaveLength(0);
    expect(nodes.filter((n) => n.type === "tool_result")).toHaveLength(0);
  });

  it("1개 도구는 그룹화하지 않음", () => {
    const cards: DashboardCard[] = [
      textCard("t1", "Thinking"),
      toolCard("r1", "Read", { toolResult: "c1", completed: true, parentCardId: "t1" }),
    ];
    const events: SoulSSEEvent[] = [{ type: "session", session_id: "s1" }];
    const { nodes } = buildGraph(cards, events);

    expect(nodes.filter((n) => n.type === "tool_group")).toHaveLength(0);
    expect(nodes.filter((n) => n.type === "tool_call")).toHaveLength(1);
  });

  it("다른 toolName은 별도 그룹", () => {
    const cards: DashboardCard[] = [
      textCard("t1", "Thinking"),
      toolCard("r1", "Read", { toolResult: "c1", completed: true, parentCardId: "t1" }),
      toolCard("r2", "Read", { toolResult: "c2", completed: true, parentCardId: "t1" }),
      toolCard("b1", "Bash", { toolResult: "c3", completed: true, parentCardId: "t1" }),
      toolCard("b2", "Bash", { toolResult: "c4", completed: true, parentCardId: "t1" }),
      toolCard("s1", "Skill", { toolResult: "c5", completed: true, parentCardId: "t1" }),
    ];
    const events: SoulSSEEvent[] = [{ type: "session", session_id: "s1" }];
    const { nodes } = buildGraph(cards, events);

    expect(nodes.filter((n) => n.type === "tool_group")).toHaveLength(2); // Read×2, Bash×2
    expect(nodes.filter((n) => n.type === "tool_call")).toHaveLength(1); // Skill×1
  });

  it("groupedCardIds가 원본 카드 ID를 모두 포함", () => {
    const cards: DashboardCard[] = [
      textCard("t1", "Thinking"),
      toolCard("r1", "Read", { toolResult: "c1", completed: true, parentCardId: "t1" }),
      toolCard("r2", "Read", { toolResult: "c2", completed: true, parentCardId: "t1" }),
      toolCard("r3", "Read", { toolResult: "c3", completed: true, parentCardId: "t1" }),
    ];
    const events: SoulSSEEvent[] = [{ type: "session", session_id: "s1" }];
    const { nodes } = buildGraph(cards, events);

    const groupNode = nodes.find((n) => n.type === "tool_group");
    expect(groupNode).toBeDefined();
    expect(groupNode!.data.groupedCardIds).toEqual(["r1", "r2", "r3"]);
  });
});

describe("orphan node connection (Phase 3)", () => {
  it("parentCardId 없는 도구가 lastThinkingNodeId에 연결", () => {
    const cards: DashboardCard[] = [
      textCard("t1", "Thinking"),
      toolCard("tool1", "Read", { toolResult: "content", completed: true }),
    ];
    const events: SoulSSEEvent[] = [{ type: "session", session_id: "s1" }];
    const { edges } = buildGraph(cards, events);

    const thinkingToTool = edges.find(
      (e) => e.source === "node-t1" && e.target === "node-tool1-call",
    );
    expect(thinkingToTool).toBeDefined();
  });
});

describe("virtual thinking node (Phase 4)", () => {
  it("첫 text 카드 전에 tool 카드가 있으면 가상 thinking 삽입", () => {
    const cards: DashboardCard[] = [
      toolCard("tool1", "Read", { toolResult: "c1", completed: true }),
      toolCard("tool2", "Bash", { toolResult: "c2", completed: true }),
      textCard("t1", "Now thinking"),
    ];
    const events: SoulSSEEvent[] = [{ type: "session", session_id: "s1" }];
    const { nodes, edges } = buildGraph(cards, events);

    const virtualNode = nodes.find((n) => n.id === "node-virtual-init");
    expect(virtualNode).toBeDefined();
    expect(virtualNode!.type).toBe("thinking");
    expect(virtualNode!.data.label).toBe("Initial Tools");

    // 메인 플로우에 연결
    const toVirtual = edges.find((e) => e.target === "node-virtual-init");
    expect(toVirtual).toBeDefined();

    // 도구가 가상 thinking에 연결
    const fromVirtual = edges.find((e) => e.source === "node-virtual-init");
    expect(fromVirtual).toBeDefined();
  });

  it("첫 카드가 text이면 가상 thinking 없음", () => {
    const cards: DashboardCard[] = [
      textCard("t1", "First thinking"),
      toolCard("tool1", "Read", { toolResult: "c1", completed: true }),
    ];
    const events: SoulSSEEvent[] = [{ type: "session", session_id: "s1" }];
    const { nodes } = buildGraph(cards, events);

    expect(nodes.find((n) => n.id === "node-virtual-init")).toBeUndefined();
  });

  it("고아 도구 그룹이 가상 thinking에 연결", () => {
    const cards: DashboardCard[] = [
      toolCard("r1", "Read", { toolResult: "c1", completed: true }),
      toolCard("r2", "Read", { toolResult: "c2", completed: true }),
      toolCard("r3", "Read", { toolResult: "c3", completed: true }),
      textCard("t1", "Thinking after tools"),
    ];
    const events: SoulSSEEvent[] = [{ type: "session", session_id: "s1" }];
    const { nodes, edges } = buildGraph(cards, events);

    const virtualNode = nodes.find((n) => n.id === "node-virtual-init");
    expect(virtualNode).toBeDefined();

    const groupNode = nodes.find((n) => n.type === "tool_group");
    expect(groupNode).toBeDefined();
    expect(groupNode!.data.groupCount).toBe(3);

    const virtualToGroup = edges.find(
      (e) => e.source === "node-virtual-init" && e.target === groupNode!.id,
    );
    expect(virtualToGroup).toBeDefined();
  });
});

describe("applyDagreLayout", () => {
  it("positions nodes with non-zero coordinates", () => {
    const nodes: GraphNode[] = [
      {
        id: "n1",
        type: "thinking",
        position: { x: 0, y: 0 },
        data: {
          nodeType: "thinking",
          label: "A",
          content: "",
          streaming: false,
        },
      },
      {
        id: "n2",
        type: "tool_call",
        position: { x: 0, y: 0 },
        data: {
          nodeType: "tool_call",
          label: "B",
          content: "",
          streaming: false,
        },
      },
    ];

    const edges = [createEdge("n1", "n2")];
    const result = applyDagreLayout(nodes, edges);

    // Both nodes should have positions set by dagre
    expect(result.nodes).toHaveLength(2);

    // They should have different Y positions (vertical layout)
    const y1 = result.nodes.find((n) => n.id === "n1")!.position.y;
    const y2 = result.nodes.find((n) => n.id === "n2")!.position.y;
    expect(y1).not.toBe(y2);
    expect(y2).toBeGreaterThan(y1); // n2 should be below n1
  });

  it("returns empty arrays for empty input", () => {
    const result = applyDagreLayout([], []);
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
  });
});

// === calcToolChainBounds 테스트 ===

describe("calcToolChainBounds", () => {
  const TOOL_BRANCH_H_GAP = 120; // layout-engine.ts 상수와 동일
  const callWidth = getNodeDimensions("tool_call").width;   // 260
  const callHeight = getNodeDimensions("tool_call").height; // 84
  const resultWidth = getNodeDimensions("tool_result").width;
  const resultHeight = getNodeDimensions("tool_result").height;
  const V_GAP = 16;

  it("returns zero for empty chain", () => {
    expect(calcToolChainBounds([])).toEqual({ width: 0, height: 0 });
  });

  it("calculates width and height for call + result", () => {
    const chain: ToolChainEntry[] = [
      { callId: "node-t1-call", resultId: "node-t1-result" },
    ];
    const bounds = calcToolChainBounds(chain);

    // width = gap + callWidth + gap + resultWidth
    expect(bounds.width).toBe(TOOL_BRANCH_H_GAP + callWidth + TOOL_BRANCH_H_GAP + resultWidth);
    // height = max(callHeight, resultHeight)
    expect(bounds.height).toBe(Math.max(callHeight, resultHeight));
  });

  it("calculates width for call-only (no result)", () => {
    const chain: ToolChainEntry[] = [
      { callId: "node-t1-call" },
    ];
    const bounds = calcToolChainBounds(chain);

    // width = gap + callWidth
    expect(bounds.width).toBe(TOOL_BRANCH_H_GAP + callWidth);
    expect(bounds.height).toBe(callHeight);
  });

  it("stacks multiple entries vertically with V_GAP", () => {
    const chain: ToolChainEntry[] = [
      { callId: "t1-call", resultId: "t1-result" },
      { callId: "t2-call", resultId: "t2-result" },
      { callId: "t3-call" },
    ];
    const bounds = calcToolChainBounds(chain);

    // height = row1 + gap + row2 + gap + row3
    const row1Height = Math.max(callHeight, resultHeight);
    const row2Height = Math.max(callHeight, resultHeight);
    const row3Height = callHeight;
    const expectedHeight = row1Height + V_GAP + row2Height + V_GAP + row3Height;
    expect(bounds.height).toBe(expectedHeight);

    // width = max of all rows (rows with result are wider)
    const withResult = TOOL_BRANCH_H_GAP + callWidth + TOOL_BRANCH_H_GAP + resultWidth;
    const withoutResult = TOOL_BRANCH_H_GAP + callWidth;
    expect(bounds.width).toBe(Math.max(withResult, withoutResult));
  });

  it("uses tool_group dimensions for group nodes", () => {
    const groupWidth = getNodeDimensions("tool_group").width;
    const groupHeight = getNodeDimensions("tool_group").height;

    const chain: ToolChainEntry[] = [
      { callId: "node-t1-group" }, // '-group' 접미사 → tool_group 크기 사용
    ];
    const bounds = calcToolChainBounds(chain);

    expect(bounds.width).toBe(TOOL_BRANCH_H_GAP + groupWidth);
    expect(bounds.height).toBe(groupHeight);
  });
});

// === applyDagreLayout: tool 체인 너비 확장 테스트 ===

describe("applyDagreLayout tool chain width expansion", () => {
  it("tool nodes are placed to the right of the parent within allocated space", () => {
    // thinking + tool_call + tool_result 시나리오
    const thinkingDims = getNodeDimensions("thinking");
    const callDims = getNodeDimensions("tool_call");

    const nodes: GraphNode[] = [
      {
        id: "n-thinking",
        type: "default",
        data: { nodeType: "thinking", label: "thinking", content: "" },
        position: { x: 0, y: 0 },
      },
      {
        id: "n-tool-call",
        type: "default",
        data: { nodeType: "tool_call", label: "call", content: "" },
        position: { x: 0, y: 0 },
      },
      {
        id: "n-tool-result",
        type: "default",
        data: { nodeType: "tool_result", label: "result", content: "" },
        position: { x: 0, y: 0 },
      },
    ];

    const toolBranches = new Map([
      ["n-thinking", [{ callId: "n-tool-call", resultId: "n-tool-result" }]],
    ]);

    const result = applyDagreLayout(nodes, [], "TB", toolBranches);

    const thinkingNode = result.nodes.find((n) => n.id === "n-thinking")!;
    const callNode = result.nodes.find((n) => n.id === "n-tool-call")!;
    const resultNode = result.nodes.find((n) => n.id === "n-tool-result")!;

    // tool_call은 thinking의 오른쪽에 배치
    expect(callNode.position.x).toBeGreaterThan(thinkingNode.position.x + thinkingDims.width);

    // tool_result는 tool_call의 오른쪽에 배치
    expect(resultNode.position.x).toBeGreaterThan(callNode.position.x + callDims.width);
  });
});

// === Phase 2: tool call 없는 세션 레이아웃 검증 ===

describe("no-tool session layout (Bug #10 regression)", () => {
  it("tool call 없는 세션에서 THINKING → RESPONSE → COMPLETE 세로 배치", () => {
    const cards: DashboardCard[] = [
      textCard("t1", "Thinking about the question..."),
      textCard("t2", "Here is my response."),
    ];
    const events: SoulSSEEvent[] = [
      { type: "session", session_id: "no-tool-session" },
      { type: "complete", result: "done", attachments: [] },
    ];

    const { nodes } = buildGraph(cards, events);

    // 노드: session(system) + thinking + response + complete(system)
    const sessionNode = nodes.find((n) => n.data.label === "Session Started");
    const thinkingNode = nodes.find((n) => n.id === "node-t1");
    const responseNode = nodes.find((n) => n.id === "node-t2");
    const completeNode = nodes.find((n) => n.data.label === "Complete");

    expect(sessionNode).toBeDefined();
    expect(thinkingNode).toBeDefined();
    expect(responseNode).toBeDefined();
    expect(completeNode).toBeDefined();

    // 순서대로 Y가 증가해야 함 (겹치지 않아야 함)
    expect(thinkingNode!.position.y).toBeGreaterThan(sessionNode!.position.y);
    expect(responseNode!.position.y).toBeGreaterThan(thinkingNode!.position.y);
    expect(completeNode!.position.y).toBeGreaterThan(responseNode!.position.y);
  });

  it("tool call 없는 세션에서 모든 노드가 양수 좌표", () => {
    const cards: DashboardCard[] = [
      textCard("t1", "First thinking"),
      textCard("t2", "Response"),
    ];
    const events: SoulSSEEvent[] = [
      { type: "session", session_id: "s1" },
      { type: "complete", result: "ok", attachments: [] },
    ];

    const { nodes } = buildGraph(cards, events);

    for (const node of nodes) {
      expect(node.position.x).toBeGreaterThanOrEqual(0);
      expect(node.position.y).toBeGreaterThanOrEqual(0);
    }
  });

  it("인접 노드 간 겹침 없음 (Y 간격 ≥ 노드 높이)", () => {
    const cards: DashboardCard[] = [
      textCard("t1", "Thinking"),
      textCard("t2", "Response"),
    ];
    const events: SoulSSEEvent[] = [
      { type: "session", session_id: "s1" },
      { type: "complete", result: "ok", attachments: [] },
    ];

    const { nodes } = buildGraph(cards, events);

    // 메인 플로우 노드를 Y 순으로 정렬
    const sorted = [...nodes].sort((a, b) => a.position.y - b.position.y);

    for (let i = 1; i < sorted.length; i++) {
      const prevDims = getNodeDimensions(sorted[i - 1].data.nodeType);
      const gap = sorted[i].position.y - sorted[i - 1].position.y;
      expect(gap).toBeGreaterThanOrEqual(prevDims.height);
    }
  });
});

// === Phase 3: 대규모 세션 레이아웃 검증 ===

describe("large session layout (Bug #14 regression)", () => {
  /** N개 thinking + tool 페어를 생성하는 헬퍼 */
  function generateLargeSession(pairCount: number): {
    cards: DashboardCard[];
    events: SoulSSEEvent[];
  } {
    const cards: DashboardCard[] = [];
    const events: SoulSSEEvent[] = [
      { type: "session", session_id: `large-${pairCount}` },
    ];

    for (let i = 0; i < pairCount; i++) {
      cards.push(textCard(`t${i}`, `Thinking step ${i}`));
      cards.push(
        toolCard(`tool${i}`, i % 3 === 0 ? "Bash" : i % 3 === 1 ? "Read" : "Glob", {
          toolResult: `result ${i}`,
          completed: true,
          parentCardId: `t${i}`,
        }),
      );
    }

    // 마지막 response
    cards.push(textCard(`t-final`, "Final response"));
    events.push({ type: "complete", result: "done", attachments: [] });

    return { cards, events };
  }

  it("25+ 노드 세션: 모든 노드가 양수 좌표 (10번 버그 회귀 방지)", () => {
    const { cards, events } = generateLargeSession(10); // 10 pairs = ~25 nodes

    const { nodes } = buildGraph(cards, events);

    expect(nodes.length).toBeGreaterThanOrEqual(25);

    for (const node of nodes) {
      expect(node.position.x).toBeGreaterThanOrEqual(0);
      expect(node.position.y).toBeGreaterThanOrEqual(0);
    }
  });

  it("50+ 노드 세션: 모든 노드가 양수 좌표 (14번 버그 회귀 방지)", () => {
    const { cards, events } = generateLargeSession(20); // 20 pairs = ~45+ nodes

    const { nodes } = buildGraph(cards, events);

    expect(nodes.length).toBeGreaterThanOrEqual(45);

    for (const node of nodes) {
      expect(node.position.x).toBeGreaterThanOrEqual(0);
      expect(node.position.y).toBeGreaterThanOrEqual(0);
    }
  });

  it("50+ 노드 세션: 메인 플로우 노드 겹침 없음", () => {
    const { cards, events } = generateLargeSession(20);

    const { nodes } = buildGraph(cards, events);

    // 메인 플로우 노드만 추출 (같은 X 좌표를 가진 노드들)
    const mainFlowX = nodes.find((n) => n.data.nodeType === "thinking")?.position.x;
    if (mainFlowX === undefined) return;

    const mainFlowNodes = nodes.filter((n) => n.position.x === mainFlowX);
    const sorted = [...mainFlowNodes].sort((a, b) => a.position.y - b.position.y);

    for (let i = 1; i < sorted.length; i++) {
      const prevDims = getNodeDimensions(sorted[i - 1].data.nodeType);
      const gap = sorted[i].position.y - sorted[i - 1].position.y;
      expect(gap).toBeGreaterThanOrEqual(prevDims.height);
    }
  });

  it("50+ 노드 세션: bounding box가 유한한 범위 내에 있음", () => {
    const { cards, events } = generateLargeSession(20);

    const { nodes } = buildGraph(cards, events);

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    for (const n of nodes) {
      const d = getNodeDimensions(n.data.nodeType);
      minX = Math.min(minX, n.position.x);
      minY = Math.min(minY, n.position.y);
      maxX = Math.max(maxX, n.position.x + d.width);
      maxY = Math.max(maxY, n.position.y + d.height);
    }

    // bounding box 원점이 음수가 아닌지 확인
    expect(minX).toBeGreaterThanOrEqual(0);
    expect(minY).toBeGreaterThanOrEqual(0);

    // bounding box가 합리적인 범위인지 (10만 px 이내)
    expect(maxX - minX).toBeLessThan(100_000);
    expect(maxY - minY).toBeLessThan(100_000);
  });

  it("100+ 노드 세션: 성능 및 좌표 안정성", () => {
    const { cards, events } = generateLargeSession(50); // 50 pairs = ~105 nodes

    const start = performance.now();
    const { nodes } = buildGraph(cards, events);
    const elapsed = performance.now() - start;

    expect(nodes.length).toBeGreaterThanOrEqual(100);

    // 모든 좌표가 양수
    for (const node of nodes) {
      expect(node.position.x).toBeGreaterThanOrEqual(0);
      expect(node.position.y).toBeGreaterThanOrEqual(0);
    }

    // 성능: 100+ 노드 레이아웃이 500ms 이내
    expect(elapsed).toBeLessThan(500);
  });
});
