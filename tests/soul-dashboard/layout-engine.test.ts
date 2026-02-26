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
  type GraphNode,
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
  };
}

// === Tests ===

describe("getNodeDimensions", () => {
  it("returns correct dimensions for each node type", () => {
    expect(getNodeDimensions("thinking")).toEqual({ width: 280, height: 60 });
    expect(getNodeDimensions("tool_call")).toEqual({ width: 280, height: 80 });
    expect(getNodeDimensions("system")).toEqual({ width: 280, height: 40 });
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

      // toolA→toolB: vertical chain (bottom→top, from toolA-call)
      const aToB = edges.find(
        (e) => e.source === "node-toolA-call" && e.target === "node-toolB-call",
      );
      expect(aToB).toBeDefined();
      expect(aToB!.sourceHandle).toBe("bottom");
      expect(aToB!.targetHandle).toBe("top");

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
