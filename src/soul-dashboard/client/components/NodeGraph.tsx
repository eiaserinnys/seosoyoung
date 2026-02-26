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
  useStoreApi,
  ReactFlowProvider,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useDashboardStore } from "../stores/dashboard-store";
import { nodeTypes } from "../nodes";
import {
  buildGraph,
  getNodeDimensions,
  type GraphNode,
  type GraphEdge,
} from "../lib/layout-engine";

/** 그래프 재구성 디바운스 간격 (ms) - 고빈도 text_delta 이벤트 대응 */
const REBUILD_DEBOUNCE_MS = 100;

/** 고정 줌 비율 (Complete 상태 기준) */
const FIXED_ZOOM = 0.75;

/** 뷰포트 가장자리와 새 노드 사이의 최소 마진 (px) */
const PAN_MARGIN = 80;

// === Inner Graph (needs ReactFlow context) ===

function NodeGraphInner() {
  const cards = useDashboardStore((s) => s.cards);
  const graphEvents = useDashboardStore((s) => s.graphEvents);
  const collapsedGroups = useDashboardStore((s) => s.collapsedGroups);
  const selectedCardId = useDashboardStore((s) => s.selectedCardId);
  const selectCard = useDashboardStore((s) => s.selectCard);
  const selectEventNode = useDashboardStore((s) => s.selectEventNode);
  const activeSessionKey = useDashboardStore((s) => s.activeSessionKey);

  const { fitView, getViewport, setViewport } = useReactFlow();
  const store = useStoreApi();

  const [nodes, setNodes, onNodesChange] = useNodesState<GraphNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<GraphEdge>([]);

  // 신규 노드 감지를 위한 ID 추적
  const prevNodeIdsRef = useRef<Set<string>>(new Set());
  // 첫 로드 판별 플래그
  const hasInitializedRef = useRef(false);

  // 카드/이벤트가 변경되면 그래프 재구성 (디바운스 적용)
  useEffect(() => {
    if (!activeSessionKey) {
      setNodes([]);
      setEdges([]);
      prevNodeIdsRef.current = new Set();
      hasInitializedRef.current = false;
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

      // 신규 노드 감지: 이전에 없던 ID가 추가되었는지 확인
      const currentIds = new Set(nodesWithSelection.map((n) => n.id));
      const addedNodes = nodesWithSelection.filter(
        (n) => !prevNodeIdsRef.current.has(n.id),
      );
      prevNodeIdsRef.current = currentIds;

      if (addedNodes.length > 0) {
        const isFirstLoad = !hasInitializedRef.current;
        hasInitializedRef.current = true;

        rafId = requestAnimationFrame(() => {
          if (isFirstLoad) {
            // 첫 로드: 고정 줌 비율로 중앙 배치
            fitView({
              padding: 0.3,
              duration: 300,
              maxZoom: FIXED_ZOOM,
              minZoom: FIXED_ZOOM,
            });
            return;
          }

          // 이후 노드 추가: 줌 유지, 필요 시 최소 pan만 수행
          const viewport = getViewport();
          const { width: vpW, height: vpH } = store.getState();
          if (vpW === 0 || vpH === 0) return;

          // 추가된 노드 중 가장 아래쪽과 가장 오른쪽 노드를 추적
          // (tool 노드는 수평 분기되므로 우측 노드도 확인 필요)
          const zoom = viewport.zoom;
          let maxBottom = -Infinity;
          let maxRight = -Infinity;
          let bottomNode = addedNodes[0];
          let rightNode = addedNodes[0];

          for (const n of addedNodes) {
            const d = getNodeDimensions(n.data.nodeType);
            const bottom = n.position.y + d.height;
            const right = n.position.x + d.width;
            if (bottom > maxBottom) {
              maxBottom = bottom;
              bottomNode = n;
            }
            if (right > maxRight) {
              maxRight = right;
              rightNode = n;
            }
          }

          // 두 타겟 노드의 화면 좌표를 계산하여 dx, dy를 합산
          let dx = 0;
          let dy = 0;

          for (const targetNode of [bottomNode, rightNode]) {
            const dims = getNodeDimensions(targetNode.data.nodeType);
            const screenX = targetNode.position.x * zoom + viewport.x;
            const screenY = targetNode.position.y * zoom + viewport.y;
            const nodeW = dims.width * zoom;
            const nodeH = dims.height * zoom;

            // 뷰포트 안에 있는지 체크 (마진 포함)
            const isVisible =
              screenX + nodeW > PAN_MARGIN &&
              screenX < vpW - PAN_MARGIN &&
              screenY + nodeH > PAN_MARGIN &&
              screenY < vpH - PAN_MARGIN;

            if (isVisible) continue;

            // 최소 pan 계산 (노드가 뷰포트보다 클 때를 방어적으로 클램프)
            if (screenX + nodeW <= PAN_MARGIN) {
              dx = Math.max(dx, PAN_MARGIN - screenX);
            } else if (screenX >= vpW - PAN_MARGIN) {
              const idealDx = vpW - PAN_MARGIN - nodeW - screenX;
              dx = Math.min(dx, Math.max(idealDx, PAN_MARGIN - screenX));
            }

            if (screenY + nodeH <= PAN_MARGIN) {
              dy = Math.max(dy, PAN_MARGIN - screenY);
            } else if (screenY >= vpH - PAN_MARGIN) {
              const idealDy = vpH - PAN_MARGIN - nodeH - screenY;
              dy = Math.min(dy, Math.max(idealDy, PAN_MARGIN - screenY));
            }
          }

          if (dx === 0 && dy === 0) return;

          setViewport(
            { x: viewport.x + dx, y: viewport.y + dy, zoom },
            { duration: 300 },
          );
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
    getViewport,
    setViewport,
    store,
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
      defaultViewport={{ x: 0, y: 0, zoom: FIXED_ZOOM }}
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
      data-testid="node-graph"
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
