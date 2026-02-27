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

/** 최소 줌 비율 (ReactFlow minZoom과 동기화) */
const MIN_ZOOM = 0.1;

/** 뷰포트 가장자리와 새 노드 사이의 최소 마진 (px) */
const PAN_MARGIN = 80;

/**
 * 특정 노드가 뷰포트에 보이도록 하기 위해 필요한 pan(dx, dy)을 계산합니다.
 * 줌은 절대 변경하지 않습니다. 이미 보이면 { dx: 0, dy: 0 }을 반환합니다.
 */
function calcPanToNode(
  node: GraphNode,
  viewport: { x: number; y: number; zoom: number },
  vpW: number,
  vpH: number,
): { dx: number; dy: number } {
  const dims = getNodeDimensions(node.data.nodeType);
  const { zoom } = viewport;
  const screenX = node.position.x * zoom + viewport.x;
  const screenY = node.position.y * zoom + viewport.y;
  const nodeW = dims.width * zoom;
  const nodeH = dims.height * zoom;

  // 뷰포트 안에 있는지 체크 (마진 포함)
  if (
    screenX + nodeW > PAN_MARGIN &&
    screenX < vpW - PAN_MARGIN &&
    screenY + nodeH > PAN_MARGIN &&
    screenY < vpH - PAN_MARGIN
  ) {
    return { dx: 0, dy: 0 };
  }

  let dx = 0;
  let dy = 0;

  // X축: 노드가 뷰포트 좌측으로 벗어난 경우
  // 좌측 가장자리를 마진에 맞춤 (오버사이즈 노드도 동일 처리: 좌측 우선)
  if (screenX + nodeW <= PAN_MARGIN) {
    dx = PAN_MARGIN - screenX;
  }
  // X축: 노드가 뷰포트 우측으로 벗어난 경우
  else if (screenX >= vpW - PAN_MARGIN) {
    dx = vpW - PAN_MARGIN - nodeW - screenX;
    // 노드가 뷰포트보다 클 때: 좌측 가장자리가 보이도록 클램프
    if (nodeW > vpW - 2 * PAN_MARGIN) {
      dx = PAN_MARGIN - screenX;
    }
  }

  // Y축: 노드가 뷰포트 상단으로 벗어난 경우
  // 상단 가장자리를 마진에 맞춤 (오버사이즈 노드도 동일 처리: 상단 우선)
  if (screenY + nodeH <= PAN_MARGIN) {
    dy = PAN_MARGIN - screenY;
  }
  // Y축: 노드가 뷰포트 하단으로 벗어난 경우
  else if (screenY >= vpH - PAN_MARGIN) {
    dy = vpH - PAN_MARGIN - nodeH - screenY;
    // 노드가 뷰포트보다 클 때: 상단 가장자리가 보이도록 클램프
    if (nodeH > vpH - 2 * PAN_MARGIN) {
      dy = PAN_MARGIN - screenY;
    }
  }

  return { dx, dy };
}

// === Inner Graph (needs ReactFlow context) ===

function NodeGraphInner() {
  const cards = useDashboardStore((s) => s.cards);
  const graphEvents = useDashboardStore((s) => s.graphEvents);
  const collapsedGroups = useDashboardStore((s) => s.collapsedGroups);
  const selectedCardId = useDashboardStore((s) => s.selectedCardId);
  const selectCard = useDashboardStore((s) => s.selectCard);
  const selectEventNode = useDashboardStore((s) => s.selectEventNode);
  const activeSessionKey = useDashboardStore((s) => s.activeSessionKey);

  const { getViewport, setViewport } = useReactFlow();
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
          const { width: vpW, height: vpH } = store.getState();
          if (vpW === 0 || vpH === 0) return;

          if (isFirstLoad) {
            // === 세션 변경(첫 로드): 줌 허용 1회 ===
            // 1. 전체 노드의 바운딩 박스 계산
            let minX = Infinity;
            let minY = Infinity;
            let maxX = -Infinity;
            let maxY = -Infinity;
            for (const n of nodesWithSelection) {
              const d = getNodeDimensions(n.data.nodeType);
              minX = Math.min(minX, n.position.x);
              minY = Math.min(minY, n.position.y);
              maxX = Math.max(maxX, n.position.x + d.width);
              maxY = Math.max(maxY, n.position.y + d.height);
            }

            // 2. 바운딩 박스와 뷰포트 비교하여 적절한 줌 계산
            const graphW = maxX - minX;
            const graphH = maxY - minY;
            const INIT_PADDING = 0.3;
            let zoom = FIXED_ZOOM;
            if (graphW > 0 && graphH > 0) {
              const fitZoomX = vpW / (graphW * (1 + INIT_PADDING));
              const fitZoomY = vpH / (graphH * (1 + INIT_PADDING));
              zoom = Math.min(fitZoomX, fitZoomY, FIXED_ZOOM);
              zoom = Math.max(zoom, MIN_ZOOM);
            }

            // 3. 가장 최근(마지막) 노드가 화면 중앙에 오도록 viewport 설정
            // NOTE: 줌은 전체 그래프 기준이지만 center는 마지막 노드 기준이므로,
            // 그래프가 클 경우 초기 노드들이 뷰포트 밖에 위치할 수 있음 (의도된 동작)
            const lastNode = nodesWithSelection[nodesWithSelection.length - 1];
            if (!lastNode) return;
            const lastDims = getNodeDimensions(lastNode.data.nodeType);
            const centerX = lastNode.position.x + lastDims.width / 2;
            const centerY = lastNode.position.y + lastDims.height / 2;

            setViewport(
              {
                x: vpW / 2 - centerX * zoom,
                y: vpH / 2 - centerY * zoom,
                zoom,
              },
              { duration: 300 },
            );
            return;
          }

          // === 스트리밍 노드 추가: 줌 절대 변경 금지, pan만 수행 ===
          const viewport = getViewport();
          // 가장 최근 추가된 노드를 대상으로 pan 계산
          const targetNode = addedNodes[addedNodes.length - 1];
          const { dx, dy } = calcPanToNode(targetNode, viewport, vpW, vpH);

          if (dx === 0 && dy === 0) return;

          // zoom은 현재 viewport의 값을 그대로 유지 (방어적 고정)
          setViewport(
            { x: viewport.x + dx, y: viewport.y + dy, zoom: viewport.zoom },
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
    getViewport,
    setViewport,
    store,
  ]);

  // 노드 선택 → 카드 선택 또는 이벤트 노드 선택 동기화
  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes }: OnSelectionChangeParams) => {
      if (selectedNodes.length === 1) {
        const nodeData = selectedNodes[0].data;
        const nodeType = nodeData?.nodeType as string | undefined;

        // tool_group 노드 → groupedCardIds 포함하여 이벤트 노드 데이터로 저장
        if (nodeType === "tool_group") {
          selectEventNode({
            nodeType,
            label: (nodeData?.label as string) ?? "",
            content: (nodeData?.content as string) ?? "",
            groupedCardIds: (nodeData?.groupedCardIds as string[]) ?? [],
            toolName: (nodeData?.toolName as string) ?? undefined,
            groupCount: (nodeData?.groupCount as number) ?? undefined,
          });
          return;
        }

        const cardId = nodeData?.cardId as string | undefined;
        if (cardId) {
          selectCard(cardId);
          return;
        }

        // user/intervention 등 카드 기반이 아닌 노드 → 이벤트 노드 데이터 저장
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
      minZoom={MIN_ZOOM}
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
