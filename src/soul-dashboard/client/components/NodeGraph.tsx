/**
 * NodeGraph - 노드 그래프 패널 (Phase 6-B에서 구현 예정)
 *
 * 현재는 placeholder로, 카드 목록을 간단한 리스트로 표시합니다.
 * Phase 6-B에서 실제 노드 그래프 시각화로 교체됩니다.
 */

import type { DashboardCard } from "@shared/types";
import { useDashboardStore } from "../stores/dashboard-store";

// === Card Node (간이 표시) ===

interface CardNodeProps {
  card: DashboardCard;
  isSelected: boolean;
  onClick: () => void;
}

function CardNode({ card, isSelected, onClick }: CardNodeProps) {
  const isText = card.type === "text";

  return (
    <button
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        width: "100%",
        padding: "8px 12px",
        border: isSelected ? "1px solid #3b82f6" : "1px solid rgba(255,255,255,0.08)",
        borderRadius: "6px",
        background: isSelected
          ? "rgba(59, 130, 246, 0.1)"
          : "rgba(255,255,255,0.03)",
        cursor: "pointer",
        textAlign: "left",
        transition: "all 0.15s",
        marginBottom: "4px",
      }}
    >
      {/* Type icon */}
      <span
        style={{
          fontSize: "14px",
          width: "20px",
          textAlign: "center",
          flexShrink: 0,
        }}
      >
        {isText ? "\u{1F4DD}" : "\u{1F527}"}
      </span>

      {/* Card summary */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "12px",
            color: "#d1d5db",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {isText
            ? card.content.slice(0, 60) || "(empty)"
            : card.toolName ?? "tool"}
        </div>
      </div>

      {/* Status */}
      <span
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          backgroundColor: card.completed
            ? card.isError
              ? "#ef4444"
              : "#6b7280"
            : "#22c55e",
          flexShrink: 0,
          animation: card.completed ? "none" : "pulse 2s infinite",
        }}
      />
    </button>
  );
}

// === NodeGraph ===

export function NodeGraph() {
  const cards = useDashboardStore((s) => s.cards);
  const selectedCardId = useDashboardStore((s) => s.selectedCardId);
  const selectCard = useDashboardStore((s) => s.selectCard);
  const activeSessionKey = useDashboardStore((s) => s.activeSessionKey);

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
        <span>Execution Flow</span>
        <span style={{ color: "#6b7280", fontWeight: 400 }}>
          {cards.length}
        </span>
      </div>

      {/* Content */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "8px",
        }}
      >
        {!activeSessionKey && (
          <div
            style={{
              padding: "20px",
              textAlign: "center",
              color: "#6b7280",
              fontSize: "13px",
            }}
          >
            Select a session
          </div>
        )}

        {activeSessionKey && cards.length === 0 && (
          <div
            style={{
              padding: "20px",
              textAlign: "center",
              color: "#6b7280",
              fontSize: "13px",
            }}
          >
            Waiting for events...
          </div>
        )}

        {cards.map((card) => (
          <CardNode
            key={card.cardId}
            card={card}
            isSelected={selectedCardId === card.cardId}
            onClick={() =>
              selectCard(selectedCardId === card.cardId ? null : card.cardId)
            }
          />
        ))}
      </div>
    </div>
  );
}
