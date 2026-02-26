/**
 * NodeGraph - React Flow 기반 노드 그래프 패널
 *
 * Soul 실행 이벤트를 노드 기반 그래프로 시각화합니다.
 * thinking-tool-result 관계를 React Flow로 표현하며
 * 스트리밍 실시간 업데이트와 서브에이전트 중첩 구조를 지원합니다.
 */

import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useDashboardStore } from "../stores/dashboard-store";
import { nodeTypes } from "../nodes";
import {
  buildGraph,
  type GraphNode,
  type GraphEdge,
} from "../lib/layout-engine";

/** 그래프 재구성 디바운스 간격 (ms) - 고빈도 text_delta 이벤트 대응 */
const REBUILD_DEBOUNCE_MS = 100;

// === Inner Graph (needs ReactFlow context) ===

function NodeGraphInner() {
  const cards = useDashboardStore((s) => s.cards);
  const graphEvents = useDashboardStore((s) => s.graphEvents);
  const collapsedGroups = useDashboardStore((s) => s.collapsedGroups);
  const selectedCardId = useDashboardStore((s) => s.selectedCardId);
  const selectCard = useDashboardStore((s) => s.selectCard);
  const selectEventNode = useDashboardStore((s) => s.selectEventNode);
  const activeSessionKey = useDashboardStore((s) => s.activeSessionKey);

  const { fitView } = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState<GraphNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<GraphEdge>([]);

  // 노드 수 추적 (fitView 트리거용)
  const prevNodeCountRef = useRef(0);

  // 카드/이벤트가 변경되면 그래프 재구성 (디바운스 적용)
  useEffect(() => {
    if (!activeSessionKey) {
      setNodes([]);
      setEdges([]);
      prevNodeCountRef.current = 0;
      return;
    }

    let rafId: number | undefined;

    const timer = setTimeout(() => {
      const { nodes: newNodes, edges: newEdges } = buildGraph(
        cards,
        graphEvents,
        collapsedGroups,
      );

      // 선택된 카드 반영
      const nodesWithSelection = newNodes.map((n) => ({
        ...n,
        selected: n.data.cardId === selectedCardId,
      }));

      setNodes(nodesWithSelection);
      setEdges(newEdges);

      // 새 노드가 추가되면 fitView (rAF로 레이아웃 후 실행)
      if (newNodes.length !== prevNodeCountRef.current) {
        prevNodeCountRef.current = newNodes.length;
        rafId = requestAnimationFrame(() => {
          fitView({ padding: 0.2, duration: 300 });
        });
      }
    }, REBUILD_DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      if (rafId !== undefined) cancelAnimationFrame(rafId);
    };
  }, [
    cards,
    graphEvents,
    collapsedGroups,
    activeSessionKey,
    selectedCardId,
    setNodes,
    setEdges,
    fitView,
  ]);

  // 노드 선택 → 카드 선택 또는 이벤트 노드 선택 동기화
  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes }: OnSelectionChangeParams) => {
      if (selectedNodes.length === 1) {
        const nodeData = selectedNodes[0].data;
        const cardId = nodeData?.cardId as string | undefined;
        if (cardId) {
          selectCard(cardId);
          return;
        }

        // user/intervention 등 카드 기반이 아닌 노드 → 이벤트 노드 데이터 저장
        const nodeType = nodeData?.nodeType as string | undefined;
        if (nodeType === "user" || nodeType === "intervention") {
          selectEventNode({
            nodeType,
            label: (nodeData?.label as string) ?? "",
            content: (nodeData?.fullContent as string) ?? (nodeData?.content as string) ?? "",
          });
          return;
        }
      }
      // 선택 해제, 다중 선택, 또는 처리되지 않은 노드 타입 → 선택 해제
      selectCard(null);
    },
    [selectCard, selectEventNode],
  );

  // 빈 상태
  if (!activeSessionKey) {
    return (
      <div style={emptyStateStyle}>
        <div style={{ color: "#6b7280", fontSize: 13 }}>Select a session</div>
      </div>
    );
  }

  if (cards.length === 0) {
    return (
      <div style={emptyStateStyle}>
        <div style={{ color: "#6b7280", fontSize: 13 }}>
          <span
            style={{
              display: "inline-block",
              width: 6,
              height: 6,
              borderRadius: "50%",
              backgroundColor: "#22c55e",
              animation: "pulse 2s infinite",
              marginRight: 8,
              verticalAlign: "middle",
            }}
          />
          Waiting for events...
        </div>
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onSelectionChange={onSelectionChange}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.1}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
      colorMode="dark"
      defaultEdgeOptions={{
        type: "smoothstep",
        style: { stroke: "#4b5563", strokeWidth: 1.5 },
      }}
      style={{ width: "100%", height: "100%" }}
    >
      <Background color="#1f2937" gap={20} size={1} />
      <Controls
        showInteractive={false}
        style={{
          borderRadius: 6,
          border: "1px solid rgba(255,255,255,0.08)",
          boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
        }}
      />
    </ReactFlow>
  );
}

// === NodeGraph (with ReactFlowProvider wrapper) ===

export function NodeGraph() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <GraphHeader />

      {/* React Flow Canvas */}
      <div style={{ flex: 1, overflow: "hidden" }}>
        <ReactFlowProvider>
          <NodeGraphInner />
        </ReactFlowProvider>
      </div>
    </div>
  );
}

// === Header Component ===

function GraphHeader() {
  const cards = useDashboardStore((s) => s.cards);
  const streamingCount = useMemo(
    () => cards.filter((c) => !c.completed).length,
    [cards],
  );

  return (
    <div
      style={{
        padding: "12px 14px",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        fontSize: "12px",
        fontWeight: 600,
        color: "#9ca3af",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      <span>Execution Flow</span>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {streamingCount > 0 && (
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              color: "#22c55e",
              fontWeight: 400,
              fontSize: 11,
              textTransform: "none",
            }}
          >
            <span
              style={{
                width: 5,
                height: 5,
                borderRadius: "50%",
                backgroundColor: "#22c55e",
                animation: "pulse 2s infinite",
              }}
            />
            {streamingCount} active
          </span>
        )}
        <span style={{ color: "#6b7280", fontWeight: 400 }}>
          {cards.length}
        </span>
      </div>
    </div>
  );
}

// === Styles ===

const emptyStateStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  height: "100%",
};
