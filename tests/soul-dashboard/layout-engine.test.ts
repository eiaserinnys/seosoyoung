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

    // Should have horizontal edge from call to result
    const horizontalEdge = edges.find(
      (e) => e.sourceHandle === "right" && e.targetHandle === "left",
    );
    expect(horizontalEdge).toBeDefined();
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

    // Should have vertical edges connecting the sequence
    // t1 -> tool_call -> tool_result -> t2
    expect(edges.length).toBeGreaterThanOrEqual(3);
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
