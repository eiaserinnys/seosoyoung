/**
 * Soul Dashboard - Layout Engine
 *
 * DashboardCard[] 및 SSE 이벤트를 React Flow 노드/엣지로 변환하는 레이아웃 엔진.
 * 원점 기반 고정 열(A/B/C) 배치 + 순차 Y 누적 방식으로 레이아웃을 적용합니다.
 */

import type { Node, Edge } from "@xyflow/react";
import type { DashboardCard, SoulSSEEvent } from "@shared/types";

// === Graph Node Types ===

/** 노드 그래프에 표시되는 커스텀 노드 타입 */
export type GraphNodeType =
  | "user"
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "tool_group"
  | "response"
  | "system"
  | "intervention";

/** React Flow 노드의 data 필드 */
export interface GraphNodeData extends Record<string, unknown> {
  nodeType: GraphNodeType;
  cardId?: string;
  label: string;
  content: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  toolResult?: string;
  isError?: boolean;
  streaming: boolean;
  subAgentId?: string;
  collapsed?: boolean;
  /** 플랜 모드 관련 플래그 */
  isPlanMode?: boolean;
  isPlanModeEntry?: boolean;
  isPlanModeExit?: boolean;
  /** 전체 텍스트 (user/intervention 노드의 상세 뷰용) */
  fullContent?: string;
  /** 도구 그룹 노드: 그룹에 포함된 카드 ID 목록 */
  groupedCardIds?: string[];
  /** 도구 그룹 노드: 그룹 내 도구 개수 */
  groupCount?: number;
}

export type GraphNode = Node<GraphNodeData>;
export type GraphEdge = Edge;

// === Sub-Agent Grouping ===

/** Task 도구 호출로 감지된 서브 에이전트 그룹 */
export interface SubAgentGroup {
  /** 그룹 고유 ID */
  groupId: string;
  /** Task tool_call 카드 ID */
  taskCardId: string;
  /** 그룹에 포함된 카드 ID 목록 (Task 카드 자체 포함) */
  cardIds: string[];
  /** 그룹 레이블 (Task 입력에서 추출) */
  label: string;
  /** 접힌 상태 여부 */
  collapsed: boolean;
}

// === Tool Branch Mapping ===

/** thinking 노드에 연결된 tool 체인 */
export interface ToolChainEntry {
  /** tool_call 노드 ID */
  callId: string;
  /** tool_result 노드 ID (있으면) */
  resultId?: string;
}

/** thinking 노드별 tool 분기 정보 */
export type ToolBranches = Map<string, ToolChainEntry[]>;

// === Node Dimensions ===

/** 노드 타입별 기본 크기 (그리드 레이아웃에 사용) */
const NODE_DIMENSIONS: Record<GraphNodeType | "group", { width: number; height: number }> = {
  user: { width: 260, height: 84 },
  thinking: { width: 260, height: 84 },
  tool_call: { width: 260, height: 84 },
  tool_result: { width: 260, height: 84 },
  tool_group: { width: 260, height: 84 },
  response: { width: 260, height: 84 },
  system: { width: 260, height: 84 },
  intervention: { width: 260, height: 84 },
  group: { width: 320, height: 100 },
};

/**
 * 노드 타입에 대한 크기를 반환합니다.
 */
export function getNodeDimensions(
  nodeType: GraphNodeType | "group",
): { width: number; height: number } {
  return NODE_DIMENSIONS[nodeType] ?? { width: 260, height: 84 };
}

// === Edge Creation ===

/**
 * React Flow 엣지를 생성합니다.
 *
 * 결정론적 ID를 사용합니다 (source, target, handle 조합으로 유일성 보장).
 * 모듈 레벨 상태를 사용하지 않아 동시 호출에 안전합니다.
 *
 * @param source - 소스 노드 ID
 * @param target - 타겟 노드 ID
 * @param animated - 애니메이션 여부 (스트리밍 중인 연결에 사용)
 * @param sourceHandle - 소스 핸들 (수평 연결 시 "right")
 * @param targetHandle - 타겟 핸들 (수평 연결 시 "left")
 */
export function createEdge(
  source: string,
  target: string,
  animated = false,
  sourceHandle?: string,
  targetHandle?: string,
): GraphEdge {
  const handleSuffix = sourceHandle || targetHandle
    ? `-${sourceHandle ?? "d"}-${targetHandle ?? "d"}`
    : "";
  return {
    id: `e-${source}-${target}${handleSuffix}`,
    source,
    target,
    animated,
    sourceHandle,
    targetHandle,
    style: { stroke: animated ? "#3b82f6" : "#4b5563", strokeWidth: 1.5 },
  };
}

// === Sub-Agent Detection ===

/**
 * DashboardCard 배열에서 Task 도구 호출을 감지하여 서브 에이전트 그룹을 추출합니다.
 *
 * Task 도구의 tool_call과 tool_result 사이에 있는 모든 카드를
 * 하나의 서브 에이전트 그룹으로 묶습니다.
 */
export function detectSubAgents(cards: DashboardCard[]): SubAgentGroup[] {
  const groups: SubAgentGroup[] = [];
  let groupCounter = 0;

  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];

    // Task 도구 호출 감지
    if (card.type === "tool" && card.toolName === "Task") {
      groupCounter += 1;
      const groupId = `subagent-${groupCounter}`;
      const groupCardIds: string[] = [card.cardId];

      // Task 카드의 입력에서 레이블 추출
      const taskDescription =
        (card.toolInput?.description as string) ??
        (card.toolInput?.prompt as string) ??
        "Sub-agent Task";
      const label =
        taskDescription.length > 50
          ? taskDescription.slice(0, 47) + "..."
          : taskDescription;

      // Task 카드 이후부터 해당 Task의 결과(completed)까지의 카드를 수집
      // Task 카드 자체가 completed이면 그 사이의 카드가 없으므로 Task 카드만 포함
      if (!card.completed) {
        // 아직 실행 중인 Task: 이후 모든 카드를 그룹에 포함
        for (let j = i + 1; j < cards.length; j++) {
          groupCardIds.push(cards[j].cardId);
        }
      } else {
        // 완료된 Task: tool_result가 도착한 시점까지 중간 카드를 찾아야 하지만,
        // DashboardCard 구조에서는 Task 카드 자체에 결과가 포함되므로
        // Task 카드와 그 다음 카드들 중 다음 Task 시작 전까지를 그룹에 포함
        for (let j = i + 1; j < cards.length; j++) {
          const next = cards[j];
          // 다음 Task 도구 호출을 만나면 중단
          if (next.type === "tool" && next.toolName === "Task") {
            break;
          }
          groupCardIds.push(next.cardId);
        }
      }

      groups.push({
        groupId,
        taskCardId: card.cardId,
        cardIds: groupCardIds,
        label,
        collapsed: false,
      });
    }
  }

  return groups;
}

// === Node Creation Helpers ===

/**
 * 텍스트 카드를 thinking 또는 response 노드로 변환합니다.
 *
 * 세션이 완료된 상태에서 마지막 텍스트 카드는 response 타입으로 생성됩니다.
 */
function createTextNode(
  card: DashboardCard,
  isLastText: boolean,
  isSessionComplete: boolean,
  planFlags?: { isPlanMode?: boolean },
): GraphNode {
  const nodeType: GraphNodeType =
    isLastText && isSessionComplete ? "response" : "thinking";
  const label = nodeType === "response" ? "Response" : "Thinking";

  return {
    id: `node-${card.cardId}`,
    type: nodeType,
    position: { x: 0, y: 0 },
    data: {
      nodeType,
      cardId: card.cardId,
      label,
      content:
        card.content.length > 120
          ? card.content.slice(0, 117) + "..."
          : card.content || "(streaming...)",
      streaming: !card.completed,
      isPlanMode: planFlags?.isPlanMode,
    },
  };
}

/**
 * 도구 카드를 tool_call 노드로 변환합니다.
 */
function createToolCallNode(
  card: DashboardCard,
  planFlags?: { isPlanMode?: boolean; isPlanModeEntry?: boolean; isPlanModeExit?: boolean },
): GraphNode {
  return {
    id: `node-${card.cardId}-call`,
    type: "tool_call",
    position: { x: 0, y: 0 },
    data: {
      nodeType: "tool_call",
      cardId: card.cardId,
      label: card.toolName ?? "Tool",
      content: formatToolInput(card.toolInput),
      toolName: card.toolName,
      toolInput: card.toolInput,
      streaming: !card.completed && !card.toolResult,
      isPlanMode: planFlags?.isPlanMode,
      isPlanModeEntry: planFlags?.isPlanModeEntry,
      isPlanModeExit: planFlags?.isPlanModeExit,
    },
  };
}

/**
 * 도구 카드의 결과를 tool_result 노드로 변환합니다.
 * tool_result가 있을 때만 생성됩니다.
 */
function createToolResultNode(card: DashboardCard): GraphNode | null {
  if (card.toolResult === undefined && card.completed) {
    // 결과 없이 완료된 경우 (빈 결과)
    return {
      id: `node-${card.cardId}-result`,
      type: "tool_result",
      position: { x: 0, y: 0 },
      data: {
        nodeType: "tool_result",
        cardId: card.cardId,
        label: `${card.toolName ?? "Tool"} Result`,
        content: "(no output)",
        toolName: card.toolName,
        toolResult: "",
        isError: card.isError,
        streaming: false,
      },
    };
  }

  if (card.toolResult === undefined) {
    // 아직 결과가 도착하지 않음 — 스트리밍 플레이스홀더 반환
    return {
      id: `node-${card.cardId}-result`,
      type: "tool_result",
      position: { x: 0, y: 0 },
      data: {
        nodeType: "tool_result",
        cardId: card.cardId,
        label: `${card.toolName ?? "Tool"} Result`,
        content: "(waiting...)",
        toolName: card.toolName,
        streaming: true,
      },
    };
  }

  const resultPreview =
    card.toolResult.length > 120
      ? card.toolResult.slice(0, 117) + "..."
      : card.toolResult;

  return {
    id: `node-${card.cardId}-result`,
    type: "tool_result",
    position: { x: 0, y: 0 },
    data: {
      nodeType: "tool_result",
      cardId: card.cardId,
      label: `${card.toolName ?? "Tool"} Result`,
      content: resultPreview,
      toolName: card.toolName,
      toolResult: card.toolResult,
      isError: card.isError,
      streaming: false,
    },
  };
}

/**
 * user_message 이벤트를 user 노드로 변환합니다.
 * 세션 시작 시 사용자의 원본 프롬프트를 표시합니다.
 */
function createUserMessageNode(
  event: Extract<SoulSSEEvent, { type: "user_message" }>,
  index: number,
): GraphNode {
  return {
    id: `node-user-${index}`,
    type: "user",
    position: { x: 0, y: 0 },
    data: {
      nodeType: "user",
      label: `User (${event.user})`,
      content: event.text.length > 120 ? event.text.slice(0, 117) + "..." : event.text,
      streaming: false,
      /** 전체 텍스트 (상세 뷰에서 사용) */
      fullContent: event.text,
    },
  };
}

/**
 * intervention_sent 이벤트를 intervention 노드로 변환합니다.
 */
function createInterventionNode(
  event: Extract<SoulSSEEvent, { type: "intervention_sent" }>,
  index: number,
): GraphNode {
  return {
    id: `node-intervention-${index}`,
    type: "intervention",
    position: { x: 0, y: 0 },
    data: {
      nodeType: "intervention",
      label: `Intervention (${event.user})`,
      content: event.text.length > 120 ? event.text.slice(0, 117) + "..." : event.text,
      streaming: false,
      /** 전체 텍스트 (상세 뷰에서 사용) */
      fullContent: event.text,
    },
  };
}

/**
 * 시스템 이벤트(session, complete, error)를 system 노드로 변환합니다.
 */
function createSystemNode(
  event: SoulSSEEvent,
  index: number,
): GraphNode {
  let label: string;
  let content: string;

  switch (event.type) {
    case "session":
      label = "Session Started";
      content = `Session ID: ${event.session_id}`;
      break;
    case "complete":
      label = "Complete";
      content = event.result
        ? event.result.length > 100
          ? event.result.slice(0, 97) + "..."
          : event.result
        : "Session completed";
      break;
    case "error":
      label = "Error";
      content = event.message;
      break;
    default:
      label = event.type;
      content = "";
  }

  return {
    id: `node-system-${event.type}-${index}`,
    type: "system",
    position: { x: 0, y: 0 },
    data: {
      nodeType: "system",
      label,
      content,
      isError: event.type === "error",
      streaming: false,
    },
  };
}

// === Utility ===

/**
 * 도구 입력을 읽기 쉬운 문자열로 변환합니다.
 */
function formatToolInput(input?: Record<string, unknown>): string {
  if (!input) return "(no input)";

  const keys = Object.keys(input);
  if (keys.length === 0) return "(no input)";

  // 주요 필드만 간략히 표시
  const parts: string[] = [];
  for (const key of keys.slice(0, 3)) {
    const val = input[key];
    const str = typeof val === "string" ? val : JSON.stringify(val);
    const truncated = str && str.length > 50 ? str.slice(0, 47) + "..." : str;
    parts.push(`${key}: ${truncated}`);
  }

  if (keys.length > 3) {
    parts.push(`+${keys.length - 3} more`);
  }

  return parts.join("\n");
}

/**
 * 이벤트가 그래프에 system 노드로 표시할 만큼 중요한지 판단합니다.
 * progress, debug, memory, context_usage 등 노이즈성 이벤트는 제외합니다.
 */
function isSignificantSystemEvent(event: SoulSSEEvent): boolean {
  return event.type === "session" || event.type === "complete" || event.type === "error";
}

// === Plan Mode Detection ===

/** EnterPlanMode ~ ExitPlanMode 범위 */
export interface PlanModeRange {
  enterIdx: number;
  exitIdx: number;
  /** ExitPlanMode가 명시적으로 발견되었는지 여부 */
  closed: boolean;
}

/**
 * DashboardCard 배열에서 EnterPlanMode / ExitPlanMode 도구 호출을 감지하여
 * 플랜 모드 구간의 인덱스 범위를 반환합니다.
 *
 * EnterPlanMode 없이 ExitPlanMode만 있는 경우는 무시합니다.
 * ExitPlanMode 없이 EnterPlanMode만 있으면 마지막 카드까지를 범위로 합니다 (closed=false).
 */
export function detectPlanModeRanges(cards: DashboardCard[]): PlanModeRange[] {
  const ranges: PlanModeRange[] = [];
  let enterIdx: number | null = null;

  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];
    if (card.type !== "tool") continue;

    if (card.toolName === "EnterPlanMode") {
      enterIdx = i;
    } else if (card.toolName === "ExitPlanMode" && enterIdx !== null) {
      ranges.push({ enterIdx, exitIdx: i, closed: true });
      enterIdx = null;
    }
  }

  // 아직 ExitPlanMode가 오지 않은 경우 (현재 플랜 모드 진행 중)
  if (enterIdx !== null) {
    ranges.push({ enterIdx, exitIdx: cards.length - 1, closed: false });
  }

  return ranges;
}

// === Main Build Function ===

/**
 * DashboardCard 배열과 SSE 이벤트를 React Flow 노드/엣지로 변환합니다.
 *
 * 변환 규칙:
 * - text 카드 -> thinking 노드 (마지막 text 카드 + 세션 완료 시 response 노드)
 * - tool 카드 -> tool_call 노드 + tool_result 노드 (결과 존재 시)
 * - intervention_sent 이벤트 -> intervention 노드
 * - session/complete/error 이벤트 -> system 노드
 *
 * 레이아웃 규칙:
 * - text 카드는 메인 수직 흐름을 형성 (thinking → thinking → response)
 * - tool 카드는 메인 흐름에서 수평으로 분기 (thinking →right→ tool_call)
 * - tool_call → tool_result는 수직 연결 (아래로)
 * - 연속된 tool 카드는 수평으로 체이닝 (tool_call →right→ tool_call)
 *
 * @param cards - 현재 세션의 DashboardCard 배열
 * @param events - 원본 SSE 이벤트 배열 (시스템/개입 노드 생성용)
 * @returns 그리드 레이아웃이 적용된 노드와 엣지
 */

/**
 * tool 노드의 부모를 결정하는 헬퍼.
 * parentCardId → currentToolParentId → lastThinkingNodeId → prevMainFlowNodeId 순서로 폴백.
 */
function resolveToolParent(
  card: DashboardCard,
  nodes: GraphNode[],
  currentToolParentId: string | null,
  lastThinkingNodeId: string | null,
  prevMainFlowNodeId: string | null,
): string | null {
  const fallback = currentToolParentId ?? lastThinkingNodeId ?? prevMainFlowNodeId;
  if (card.parentCardId) {
    const parentNodeId = `node-${card.parentCardId}`;
    if (nodes.some((n) => n.id === parentNodeId)) {
      return parentNodeId;
    }
  }
  return fallback;
}

export function buildGraph(
  cards: DashboardCard[],
  events: SoulSSEEvent[],
  collapsedGroups?: Set<string>,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];

  // 세션 완료 여부: complete 또는 error 이벤트가 있는지 확인
  const isSessionComplete = events.some(
    (e) => e.type === "complete" || e.type === "error",
  );

  // 마지막 텍스트 카드 인덱스 (response 노드 판정용)
  let lastTextCardIndex = -1;
  for (let i = cards.length - 1; i >= 0; i--) {
    if (cards[i].type === "text") {
      lastTextCardIndex = i;
      break;
    }
  }

  // 플랜 모드 감지: EnterPlanMode ~ ExitPlanMode 사이의 카드 인덱스를 추적
  const planModeRanges = detectPlanModeRanges(cards);
  const planModeCardIds = new Set<string>();
  const planModeEntryCardIds = new Set<string>();
  const planModeExitCardIds = new Set<string>();

  for (const range of planModeRanges) {
    planModeEntryCardIds.add(cards[range.enterIdx].cardId);
    for (let i = range.enterIdx; i <= range.exitIdx; i++) {
      planModeCardIds.add(cards[i].cardId);
    }
    // 명시적 ExitPlanMode가 있는 경우에만 종료 노드 표시
    if (range.closed) {
      planModeExitCardIds.add(cards[range.exitIdx].cardId);
    }
  }

  // 서브 에이전트 그룹 감지 (collapsedGroups가 있으면 그룹 접힘 상태 반영)
  const subAgentGroups = detectSubAgents(cards);
  if (collapsedGroups) {
    for (const group of subAgentGroups) {
      group.collapsed = collapsedGroups.has(group.groupId);
    }
  }
  const cardToGroup = new Map<string, SubAgentGroup>();
  for (const group of subAgentGroups) {
    for (const cardId of group.cardIds) {
      cardToGroup.set(cardId, group);
    }
  }

  // 그룹 노드 생성 (접힌 상태가 아닌 경우에만 내부 노드 표시)
  const createdGroups = new Set<string>();

  // === Phase 2: 도구 그룹핑 전처리 ===
  // 같은 parentCardId + 같은 toolName인 도구 카드를 그룹으로 묶는다.
  // 그룹 임계값: 2개 이상이면 그룹화, 1개면 개별 노드 유지.
  const toolGroupMap = new Map<string, DashboardCard[]>(); // key → cards
  for (const card of cards) {
    if (card.type !== "tool") continue;
    const parentKey = card.parentCardId ?? "__orphan__";
    const key = `${parentKey}:${card.toolName ?? "unknown"}`;
    if (!toolGroupMap.has(key)) toolGroupMap.set(key, []);
    toolGroupMap.get(key)!.push(card);
  }

  // 그룹화 대상: ≥2개인 도구 카드 그룹
  const skipCardIds = new Set<string>(); // 개별 노드 생성을 건너뛸 카드
  const groupRepresentatives = new Map<string, { cards: DashboardCard[]; toolName: string; count: number }>();

  for (const [, groupCards] of toolGroupMap) {
    if (groupCards.length < 2) continue;
    // 첫 번째 카드가 대표 카드
    const representative = groupCards[0];
    groupRepresentatives.set(representative.cardId, {
      cards: groupCards,
      toolName: representative.toolName ?? "unknown",
      count: groupCards.length,
    });
    // 대표 이외의 카드는 skipSet에 등록
    for (let gi = 1; gi < groupCards.length; gi++) {
      skipCardIds.add(groupCards[gi].cardId);
    }
  }

  // === Phase 4: 가상 thinking 노드 필요 여부 판정 ===
  // 첫 번째 text 카드 이전에 tool 카드가 있으면 가상 thinking 노드가 필요
  let needsVirtualThinking = false;
  for (const card of cards) {
    if (card.type === "text") break;
    if (card.type === "tool") {
      needsVirtualThinking = true;
      break;
    }
  }

  // user_message / intervention 이벤트 추적
  const userMessageEvents: Array<{
    event: Extract<SoulSSEEvent, { type: "user_message" }>;
    index: number;
  }> = [];
  const interventionEvents: Array<{
    event: Extract<SoulSSEEvent, { type: "intervention_sent" }>;
    index: number;
  }> = [];
  const systemEvents: Array<{ event: SoulSSEEvent; index: number }> = [];

  events.forEach((event, idx) => {
    if (event.type === "user_message") {
      userMessageEvents.push({ event, index: idx });
    } else if (event.type === "intervention_sent") {
      interventionEvents.push({ event, index: idx });
    } else if (isSignificantSystemEvent(event)) {
      systemEvents.push({ event, index: idx });
    }
  });

  // 메인 수직 흐름의 마지막 노드 ID (user, thinking, response, intervention, system)
  // tool 노드는 이 체인에 포함되지 않고 수평으로 분기됩니다.
  let prevMainFlowNodeId: string | null = null;

  // Phase 3: 고아 노드 연결용 — 마지막 thinking/response 노드 ID
  let lastThinkingNodeId: string | null = null;

  // user_message 이벤트가 있으면 맨 앞에 user 노드 추가 (세션 시작 메시지)
  // 현재는 첫 번째 user_message만 표시 (세션 시작 프롬프트).
  // TODO: 멀티턴 세션에서 복수 user_message 지원
  if (userMessageEvents.length > 0) {
    const userMsg = userMessageEvents[0];
    const userNode = createUserMessageNode(userMsg.event, userMsg.index);
    nodes.push(userNode);
    prevMainFlowNodeId = userNode.id;
  }

  // session 이벤트가 있으면 user 노드 다음에 system 노드 추가
  const sessionEvent = systemEvents.find((s) => s.event.type === "session");
  if (sessionEvent) {
    const sysNode = createSystemNode(sessionEvent.event, sessionEvent.index);
    nodes.push(sysNode);

    if (prevMainFlowNodeId) {
      edges.push(createEdge(prevMainFlowNodeId, sysNode.id));
    }
    prevMainFlowNodeId = sysNode.id;
  }

  // 메인 노드 시퀀스에 삽입된 intervention 인덱스를 추적
  let interventionIdx = 0;

  // 현재 수평 tool 분기의 마지막 노드 ID
  // 새로운 text 카드가 나타나면 null로 리셋됩니다.
  let prevToolBranchNodeId: string | null = null;

  // thinking→tool 분기 매핑: 레이아웃 엔진에 전달하여 수동 배치에 사용
  const toolBranches: ToolBranches = new Map();
  // 현재 tool 체인이 연결된 메인 플로우 노드 ID
  let currentToolParentId: string | null = null;

  // Phase 4: 가상 thinking 노드 삽입
  if (needsVirtualThinking) {
    const virtualNode: GraphNode = {
      id: "node-virtual-init",
      type: "thinking",
      position: { x: 0, y: 0 },
      data: {
        nodeType: "thinking",
        label: "Initial Tools",
        content: "(tools invoked before first thinking)",
        streaming: false,
      },
    };
    nodes.push(virtualNode);

    if (prevMainFlowNodeId) {
      edges.push(createEdge(prevMainFlowNodeId, virtualNode.id));
    }
    prevMainFlowNodeId = virtualNode.id;
    lastThinkingNodeId = virtualNode.id;
    currentToolParentId = virtualNode.id;
  }

  // 카드를 순회하며 노드 생성
  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];
    const group = cardToGroup.get(card.cardId);

    // Phase 2: 그룹핑으로 건너뛸 카드
    if (skipCardIds.has(card.cardId)) continue;

    // 그룹 노드가 필요하고 아직 생성되지 않았으면 추가
    if (group && !createdGroups.has(group.groupId)) {
      createdGroups.add(group.groupId);

      const groupNode: GraphNode = {
        id: group.groupId,
        type: "group",
        position: { x: 0, y: 0 },
        data: {
          nodeType: "tool_call",
          label: `Sub-agent: ${group.label}`,
          content: "",
          streaming: !cards.find((c) => c.cardId === group.taskCardId)?.completed,
          subAgentId: group.groupId,
          collapsed: group.collapsed,
        },
        style: {
          backgroundColor: "rgba(59, 130, 246, 0.05)",
          borderColor: "rgba(59, 130, 246, 0.3)",
          borderWidth: 1,
          borderRadius: 8,
          padding: 16,
        },
      };
      nodes.push(groupNode);
    }

    // 접힌 그룹 내부의 노드는 건너뜀 (Task 카드 자체는 제외)
    if (group?.collapsed && card.cardId !== group.taskCardId) {
      continue;
    }

    // intervention 이벤트를 카드 사이에 삽입 (이벤트 순서 기준 근사 배치)
    // 간단한 휴리스틱: 카드 인덱스 비례로 intervention 삽입
    while (
      interventionIdx < interventionEvents.length &&
      interventionEvents[interventionIdx].index <= i * (events.length / Math.max(cards.length, 1))
    ) {
      const intv = interventionEvents[interventionIdx];
      const intvNode = createInterventionNode(intv.event, intv.index);
      nodes.push(intvNode);

      if (prevMainFlowNodeId) {
        edges.push(createEdge(prevMainFlowNodeId, intvNode.id));
      }
      prevMainFlowNodeId = intvNode.id;
      prevToolBranchNodeId = null; // 메인 흐름 변경 시 tool 분기 리셋
      interventionIdx++;
    }

    if (card.type === "text") {
      // 텍스트 카드 -> thinking 또는 response 노드
      const isLast = i === lastTextCardIndex;
      const textNode = createTextNode(card, isLast, isSessionComplete, {
        isPlanMode: planModeCardIds.has(card.cardId),
      });

      // 그룹 내부 노드의 경우 parentId 설정
      if (group && !group.collapsed) {
        textNode.parentId = group.groupId;
        textNode.extent = "parent";
      }

      nodes.push(textNode);

      // 이전 메인 흐름 노드와 수직 연결
      if (prevMainFlowNodeId) {
        edges.push(createEdge(prevMainFlowNodeId, textNode.id, !card.completed));
      }
      prevMainFlowNodeId = textNode.id;
      prevToolBranchNodeId = null; // 새 text 노드가 나타나면 tool 분기 리셋
      currentToolParentId = textNode.id; // 이후 tool 노드는 이 thinking에 연결
      lastThinkingNodeId = textNode.id; // Phase 3: 고아 노드 연결용 갱신
    } else if (card.type === "tool") {
      // Phase 2: 그룹 대표 카드인지 확인
      const toolGroupInfo = groupRepresentatives.get(card.cardId);

      if (toolGroupInfo) {
        // === 도구 그룹 노드 생성 ===
        const toolGroupNode: GraphNode = {
          id: `node-${card.cardId}-group`,
          type: "tool_group",
          position: { x: 0, y: 0 },
          data: {
            nodeType: "tool_group",
            cardId: card.cardId,
            label: `${toolGroupInfo.toolName} ×${toolGroupInfo.count}`,
            content: `${toolGroupInfo.count} calls`,
            toolName: toolGroupInfo.toolName,
            streaming: toolGroupInfo.cards.some((c) => !c.completed),
            groupedCardIds: toolGroupInfo.cards.map((c) => c.cardId),
            groupCount: toolGroupInfo.count,
          },
        };

        if (group && !group.collapsed) {
          toolGroupNode.parentId = group.groupId;
          toolGroupNode.extent = "parent";
        }

        nodes.push(toolGroupNode);

        const resolvedParentId = resolveToolParent(
          card, nodes, currentToolParentId, lastThinkingNodeId, prevMainFlowNodeId,
        );

        if (resolvedParentId) {
          edges.push(
            createEdge(resolvedParentId, toolGroupNode.id, toolGroupNode.data.streaming, "right", "left"),
          );
        }

        // toolBranches에 기록 (그룹 노드는 결과 없음)
        if (resolvedParentId) {
          if (!toolBranches.has(resolvedParentId)) {
            toolBranches.set(resolvedParentId, []);
          }
          toolBranches.get(resolvedParentId)!.push({
            callId: toolGroupNode.id,
            resultId: undefined,
          });
        }

        prevToolBranchNodeId = toolGroupNode.id;
      } else {
        // === 개별 도구 노드 (기존 로직) ===
        const callNode = createToolCallNode(card, {
          isPlanMode: planModeCardIds.has(card.cardId),
          isPlanModeEntry: planModeEntryCardIds.has(card.cardId),
          isPlanModeExit: planModeExitCardIds.has(card.cardId),
        });

        if (group && !group.collapsed) {
          callNode.parentId = group.groupId;
          callNode.extent = "parent";
        }

        nodes.push(callNode);

        const resolvedParentId = resolveToolParent(
          card, nodes, currentToolParentId, lastThinkingNodeId, prevMainFlowNodeId,
        );

        if (resolvedParentId) {
          edges.push(
            createEdge(resolvedParentId, callNode.id, !card.completed && !card.toolResult, "right", "left"),
          );
        }

        // tool_result 노드 생성 (결과 대기 중이면 스트리밍 플레이스홀더)
        const resultNode = createToolResultNode(card);

        // toolBranches에 기록 (레이아웃 엔진에서 수동 배치 시 사용)
        if (resolvedParentId) {
          if (!toolBranches.has(resolvedParentId)) {
            toolBranches.set(resolvedParentId, []);
          }
          toolBranches.get(resolvedParentId)!.push({
            callId: callNode.id,
            resultId: resultNode?.id,
          });
        }

        if (resultNode) {
          if (group && !group.collapsed) {
            resultNode.parentId = group.groupId;
            resultNode.extent = "parent";
          }

          nodes.push(resultNode);

          // tool_call -> tool_result: 수평 엣지 (스트리밍 중이면 animated)
          const isResultStreaming = resultNode.data.streaming;
          edges.push(createEdge(callNode.id, resultNode.id, isResultStreaming, "right", "left"));

          prevToolBranchNodeId = callNode.id;
        } else {
          prevToolBranchNodeId = callNode.id;
        }
      }
      // prevMainFlowNodeId는 변경하지 않음 (tool은 메인 흐름에 영향 없음)
    }
  }

  // 남은 intervention 이벤트 추가
  while (interventionIdx < interventionEvents.length) {
    const intv = interventionEvents[interventionIdx];
    const intvNode = createInterventionNode(intv.event, intv.index);
    nodes.push(intvNode);

    if (prevMainFlowNodeId) {
      edges.push(createEdge(prevMainFlowNodeId, intvNode.id));
    }
    prevMainFlowNodeId = intvNode.id;
    prevToolBranchNodeId = null; // 메인 흐름 변경 시 tool 분기 리셋
    interventionIdx++;
  }

  // complete/error 시스템 노드를 맨 끝에 추가
  const terminalEvents = systemEvents.filter(
    (s) => s.event.type === "complete" || s.event.type === "error",
  );
  for (const sysEvt of terminalEvents) {
    const sysNode = createSystemNode(sysEvt.event, sysEvt.index);
    nodes.push(sysNode);

    if (prevMainFlowNodeId) {
      edges.push(createEdge(prevMainFlowNodeId, sysNode.id));
    }
    prevMainFlowNodeId = sysNode.id;
  }

  // 그리드 레이아웃 적용 (tool 분기 정보 전달하여 수동 배치)
  return applyDagreLayout(nodes, edges, "TB", toolBranches);
}

// === Grid Layout ===

/** tool 체인이 부모 노드 우측에 배치될 때의 수평 간격 */
const TOOL_BRANCH_H_GAP = 120;
const V_GAP = 16;

/**
 * 부모 노드에 연결된 tool 체인이 차지하는 공간(가로+세로)을 계산합니다.
 * 부모 노드의 유효 높이를 계산할 때 사용합니다.
 *
 * width: TOOL_BRANCH_H_GAP + tool_call_width (+ TOOL_BRANCH_H_GAP + tool_result_width)
 * height: 각 tool entry를 세로로 쌓은 합
 */
export function calcToolChainBounds(chain: ToolChainEntry[]): { width: number; height: number } {
  if (chain.length === 0) return { width: 0, height: 0 };

  let maxWidth = 0;
  let totalHeight = 0;

  for (let i = 0; i < chain.length; i++) {
    // tool_group 노드인지 확인 (ID에 '-group' 접미사)
    const isGroupNode = chain[i].callId.endsWith("-group");
    const callDims = isGroupNode
      ? getNodeDimensions("tool_group")
      : getNodeDimensions("tool_call");

    // 가로: gap + call (+ gap + result)
    let rowWidth = TOOL_BRANCH_H_GAP + callDims.width;
    let rowHeight = callDims.height;

    if (chain[i].resultId) {
      const resultDims = getNodeDimensions("tool_result");
      rowWidth += TOOL_BRANCH_H_GAP + resultDims.width;
      rowHeight = Math.max(callDims.height, resultDims.height);
    }

    maxWidth = Math.max(maxWidth, rowWidth);
    totalHeight += rowHeight;

    // 다음 tool과의 간격 (마지막 제외)
    if (i < chain.length - 1) {
      totalHeight += V_GAP;
    }
  }

  return { width: maxWidth, height: totalHeight };
}

/**
 * 원점 기반 고정 열(Grid) 레이아웃을 적용합니다.
 *
 * dagre 없이 순수 그리드 배치:
 * 1. 메인 플로우 노드는 배열 순서대로 A열에 수직 배치
 *    - tool 체인이 있는 노드는 유효 높이를 확장하여 수직 공간 확보
 * 2. 고정 열(COL_A/B/C) 방식으로 X 좌표 결정
 *    - A열: 메인 플로우 (user, thinking, response, system, intervention)
 *    - B열: tool_call / tool_group
 *    - C열: tool_result
 * 3. tool 노드를 B/C열 고정 X + 순차 Y로 배치
 *
 * @param nodes - 위치가 미지정인 노드 배열 (buildGraph가 결정한 순서)
 * @param edges - 엣지 배열
 * @param direction - 레이아웃 방향 (TB: 위→아래) — 현재 TB만 지원
 * @param toolBranches - thinking→tool 분기 매핑 (수동 배치용)
 * @returns 위치가 계산된 노드와 엣지
 */
export function applyDagreLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  direction: "TB" | "LR" = "TB",
  toolBranches?: ToolBranches,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  if (nodes.length === 0) {
    return { nodes, edges };
  }

  // tool 노드 ID 집합 (메인 플로우에서 제외)
  const toolNodeIds = new Set<string>();
  if (toolBranches) {
    for (const chain of toolBranches.values()) {
      for (const entry of chain) {
        toolNodeIds.add(entry.callId);
        if (entry.resultId) {
          toolNodeIds.add(entry.resultId);
        }
      }
    }
  }

  // 노드를 분류
  const topLevelNodes = nodes.filter((n) => !n.parentId);
  const childNodes = nodes.filter((n) => n.parentId);

  // 메인 플로우 노드: 배열 순서 유지 (buildGraph가 이미 올바른 순서로 생성)
  const mainFlowOrder = topLevelNodes.filter((n) => !toolNodeIds.has(n.id));

  // 유효 높이 계산: tool 체인이 있는 노드는 높이 확장
  const effectiveHeights = new Map<string, number>();
  for (const node of mainFlowOrder) {
    const nodeType = node.data.nodeType;
    const dims =
      node.type === "group"
        ? getNodeDimensions("group")
        : getNodeDimensions(nodeType);

    let height = dims.height;
    if (toolBranches?.has(node.id)) {
      const chainBounds = calcToolChainBounds(toolBranches.get(node.id)!);
      height = Math.max(height, chainBounds.height);
    }
    effectiveHeights.set(node.id, height);
  }

  // === 고정 열 X 좌표 (원점 기반) ===
  const NODE_WIDTH = getNodeDimensions("thinking").width; // 260
  const MARGIN = 20;
  const COL_A = MARGIN;
  const COL_B = COL_A + NODE_WIDTH + TOOL_BRANCH_H_GAP;
  const COL_C = COL_B + NODE_WIDTH + TOOL_BRANCH_H_GAP;

  // === 순차 Y 좌표 (원점부터 누적) ===
  const MAIN_FLOW_V_GAP = 60;
  const sequentialTopY = new Map<string, number>();
  let currentTopY = MARGIN;
  for (const node of mainFlowOrder) {
    sequentialTopY.set(node.id, currentTopY);
    const effH = effectiveHeights.get(node.id) ?? 84;
    currentTopY += effH + MAIN_FLOW_V_GAP;
  }

  // 노드 위치 반영
  const nodePositions = new Map<string, { x: number; y: number }>();

  const positionedNodes = nodes.map((node) => {
    if (node.parentId) {
      // 그룹 내부 노드: 부모 기준 상대 위치 (간단한 세로 정렬)
      const siblings = childNodes.filter((n) => n.parentId === node.parentId);
      const siblingIndex = siblings.findIndex((n) => n.id === node.id);
      const dims = getNodeDimensions(node.data.nodeType);
      const pos = { x: 20, y: 40 + siblingIndex * (dims.height + 16) };
      nodePositions.set(node.id, pos);
      return { ...node, position: pos };
    }

    // tool 노드는 나중에 수동 배치
    if (toolNodeIds.has(node.id)) {
      return node; // 아직 위치 미지정
    }

    // 메인 플로우 노드: COL_A, 순차 Y
    const pos = {
      x: COL_A,
      y: sequentialTopY.get(node.id) ?? MARGIN,
    };
    nodePositions.set(node.id, pos);
    return { ...node, position: pos };
  });

  // tool 노드 수동 배치 (고정 열 B/C 사용)
  if (toolBranches) {
    for (const [parentId, chain] of toolBranches) {
      const parentPos = nodePositions.get(parentId);
      if (!parentPos) continue;

      let toolY = parentPos.y; // tool[0]의 y는 parent의 y와 같음

      for (let i = 0; i < chain.length; i++) {
        const entry = chain[i];
        const isGroupNode = entry.callId.endsWith("-group");
        const callDims = isGroupNode
          ? getNodeDimensions("tool_group")
          : getNodeDimensions("tool_call");

        // tool_call/tool_group: 고정 B열에 배치
        const callPos = { x: COL_B, y: toolY };

        const callIdx = positionedNodes.findIndex((n) => n.id === entry.callId);
        if (callIdx !== -1) {
          positionedNodes[callIdx] = { ...positionedNodes[callIdx], position: callPos };
          nodePositions.set(entry.callId, callPos);
        }

        // tool_result: 고정 C열에 배치
        if (entry.resultId) {
          const resultDims = getNodeDimensions("tool_result");
          const resultPos = { x: COL_C, y: toolY };

          const resultIdx = positionedNodes.findIndex((n) => n.id === entry.resultId);
          if (resultIdx !== -1) {
            positionedNodes[resultIdx] = { ...positionedNodes[resultIdx], position: resultPos };
            nodePositions.set(entry.resultId, resultPos);
          }

          // 다음 tool의 y: max(call bottom, result bottom) + v_gap
          const callBottom = toolY + callDims.height;
          const resultBottom = toolY + resultDims.height;
          toolY = Math.max(callBottom, resultBottom) + V_GAP;
        } else {
          // result가 없으면 call 아래에 다음 tool 배치
          toolY = toolY + callDims.height + V_GAP;
        }
      }
    }
  }

  return { nodes: positionedNodes, edges };
}
