/**
 * DetailView - 선택된 카드의 상세 정보 패널
 *
 * 카드 타입에 따라 적절한 상세 컴포넌트를 라우팅합니다.
 * - text 카드 → ThinkingDetail
 * - tool 카드 (Task) → SubAgentDetail
 * - tool 카드 (에러) → ErrorDetail
 * - tool 카드 (일반) → ToolDetail
 */

import type { DashboardCard } from "@shared/types";
import { useDashboardStore } from "../stores/dashboard-store";
import { ThinkingDetail } from "./detail/ThinkingDetail";
import { ToolDetail } from "./detail/ToolDetail";
import { SubAgentDetail } from "./detail/SubAgentDetail";
import { ErrorDetail } from "./detail/ErrorDetail";

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

// === DetailView ===

export function DetailView() {
  const selectedCardId = useDashboardStore((s) => s.selectedCardId);
  const cards = useDashboardStore((s) => s.cards);

  const selectedCard = selectedCardId
    ? cards.find((c) => c.cardId === selectedCardId) ?? null
    : null;

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
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {!selectedCard && (
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
      </div>
    </div>
  );
}
