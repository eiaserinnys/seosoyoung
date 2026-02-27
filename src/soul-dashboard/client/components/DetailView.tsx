/**
 * DetailView - 선택된 카드/노드의 상세 정보 패널
 *
 * 카드 타입에 따라 적절한 상세 컴포넌트를 라우팅합니다.
 * - text 카드 → ThinkingDetail
 * - tool 카드 (Task) → SubAgentDetail
 * - tool 카드 (에러) → ErrorDetail
 * - tool 카드 (일반) → ToolDetail
 * - user/intervention 이벤트 노드 → EventNodeDetail
 */

import type { DashboardCard } from "@shared/types";
import { useDashboardStore } from "../stores/dashboard-store";
import { ThinkingDetail } from "./detail/ThinkingDetail";
import { ToolDetail } from "./detail/ToolDetail";
import { SubAgentDetail } from "./detail/SubAgentDetail";
import { ErrorDetail } from "./detail/ErrorDetail";
import { ToolGroupDetail, type ToolGroupData } from "./detail/ToolGroupDetail";
import { SectionLabel, CodeBlock } from "./detail/shared";

// === Detail Router ===

/**
 * 카드 타입에 따라 적절한 상세 컴포넌트를 선택합니다.
 *
 * 우선순위:
 * 1. tool + toolName === "Task" → SubAgentDetail
 * 2. tool + isError === true → ErrorDetail
 * 3. tool → ToolDetail
 * 4. text → ThinkingDetail
 */
function CardDetail({ card }: { card: DashboardCard }) {
  if (card.type === "tool") {
    if (card.toolName === "Task") {
      return <SubAgentDetail card={card} />;
    }
    if (card.isError) {
      return <ErrorDetail card={card} />;
    }
    return <ToolDetail card={card} />;
  }

  return <ThinkingDetail card={card} />;
}

// === Event Node Detail ===

/**
 * user/intervention 이벤트 노드의 상세 뷰.
 * 전체 메시지 텍스트를 표시합니다.
 */
function EventNodeDetail({
  data,
}: {
  data: { nodeType: string; label: string; content: string };
}) {
  const isUser = data.nodeType === "user";
  const accent = isUser ? "#3b82f6" : "#f97316";
  const icon = isUser ? "\u{1F464}" : "\u270B";
  const typeLabel = isUser ? "User Message" : "Intervention";

  return (
    <div style={{ padding: "16px" }}>
      {/* Type badge */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          marginBottom: "12px",
        }}
      >
        <span style={{ fontSize: "14px" }}>{icon}</span>
        <span
          style={{
            fontSize: "11px",
            color: accent,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          {typeLabel}
        </span>
      </div>

      {/* Label */}
      <div style={{ marginBottom: "12px" }}>
        <SectionLabel>From</SectionLabel>
        <div
          style={{
            fontSize: "13px",
            color: "#d1d5db",
            fontWeight: 500,
          }}
        >
          {data.label}
        </div>
      </div>

      {/* Full content */}
      <div>
        <SectionLabel>Message</SectionLabel>
        <CodeBlock maxHeight={500}>{data.content || "(empty)"}</CodeBlock>
      </div>
    </div>
  );
}

// === DetailView ===

export function DetailView() {
  const selectedCardId = useDashboardStore((s) => s.selectedCardId);
  const selectedEventNodeData = useDashboardStore(
    (s) => s.selectedEventNodeData,
  );
  const cards = useDashboardStore((s) => s.cards);

  const selectedCard = selectedCardId
    ? cards.find((c) => c.cardId === selectedCardId) ?? null
    : null;

  const hasSelection = selectedCard || selectedEventNodeData;

  return (
    <div
      data-testid="detail-view"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Header */}
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
        <span>Detail</span>
        {selectedCard && (
          <span
            style={{
              fontSize: "10px",
              color: "#4b5563",
              fontWeight: 400,
              textTransform: "none",
              fontFamily: "'Cascadia Code', 'Fira Code', monospace",
            }}
          >
            {selectedCard.cardId}
          </span>
        )}
        {selectedEventNodeData && !selectedCard && (
          <span
            style={{
              fontSize: "10px",
              color: "#4b5563",
              fontWeight: 400,
              textTransform: "none",
            }}
          >
            {selectedEventNodeData.nodeType}
          </span>
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {!hasSelection && (
          <div
            style={{
              padding: "20px",
              textAlign: "center",
              color: "#6b7280",
              fontSize: "13px",
            }}
          >
            Select a node to view details
          </div>
        )}

        {selectedCard && <CardDetail card={selectedCard} />}
        {selectedEventNodeData && !selectedCard && selectedEventNodeData.nodeType === "tool_group" && (
          <ToolGroupDetail data={selectedEventNodeData as ToolGroupData} />
        )}
        {selectedEventNodeData && !selectedCard && selectedEventNodeData.nodeType !== "tool_group" && (
          <EventNodeDetail data={selectedEventNodeData} />
        )}
      </div>
    </div>
  );
}
