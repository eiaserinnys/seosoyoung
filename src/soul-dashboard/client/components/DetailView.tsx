/**
 * DetailView - 카드 상세 뷰 (Phase 6-C에서 확장 예정)
 *
 * 선택된 카드의 상세 정보를 표시합니다.
 * 텍스트 카드: 전체 텍스트 내용
 * 도구 카드: 도구명, 입력, 결과
 */

import type { DashboardCard } from "@shared/types";
import { useDashboardStore } from "../stores/dashboard-store";

// === Detail Content Renderers ===

function TextCardDetail({ card }: { card: DashboardCard }) {
  return (
    <div style={{ padding: "16px" }}>
      <div
        style={{
          fontSize: "11px",
          color: "#6b7280",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          marginBottom: "8px",
        }}
      >
        Text Output
      </div>
      <pre
        style={{
          fontSize: "13px",
          color: "#d1d5db",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          lineHeight: "1.6",
          margin: 0,
          fontFamily: "'Cascadia Code', 'Fira Code', monospace",
        }}
      >
        {card.content || "(empty)"}
      </pre>
    </div>
  );
}

function ToolCardDetail({ card }: { card: DashboardCard }) {
  return (
    <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* Tool name */}
      <div>
        <div
          style={{
            fontSize: "11px",
            color: "#6b7280",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            marginBottom: "4px",
          }}
        >
          Tool
        </div>
        <div
          style={{
            fontSize: "14px",
            color: "#e5e7eb",
            fontWeight: 600,
          }}
        >
          {card.toolName ?? "unknown"}
        </div>
      </div>

      {/* Tool input */}
      {card.toolInput && (
        <div>
          <div
            style={{
              fontSize: "11px",
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "4px",
            }}
          >
            Input
          </div>
          <pre
            style={{
              fontSize: "12px",
              color: "#9ca3af",
              backgroundColor: "rgba(0,0,0,0.3)",
              padding: "10px",
              borderRadius: "6px",
              overflow: "auto",
              maxHeight: "200px",
              margin: 0,
              fontFamily: "'Cascadia Code', 'Fira Code', monospace",
            }}
          >
            {JSON.stringify(card.toolInput, null, 2)}
          </pre>
        </div>
      )}

      {/* Tool result */}
      {card.toolResult !== undefined && (
        <div>
          <div
            style={{
              fontSize: "11px",
              color: card.isError ? "#ef4444" : "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "4px",
            }}
          >
            {card.isError ? "Error" : "Result"}
          </div>
          <pre
            style={{
              fontSize: "12px",
              color: card.isError ? "#fca5a5" : "#9ca3af",
              backgroundColor: card.isError
                ? "rgba(239, 68, 68, 0.08)"
                : "rgba(0,0,0,0.3)",
              padding: "10px",
              borderRadius: "6px",
              overflow: "auto",
              maxHeight: "300px",
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: "'Cascadia Code', 'Fira Code', monospace",
            }}
          >
            {card.toolResult}
          </pre>
        </div>
      )}

      {/* Status indicator */}
      {!card.completed && (
        <div
          style={{
            fontSize: "12px",
            color: "#22c55e",
            display: "flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          <span
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              backgroundColor: "#22c55e",
              animation: "pulse 2s infinite",
            }}
          />
          Running...
        </div>
      )}
    </div>
  );
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
        }}
      >
        Detail
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
            Select a card to view details
          </div>
        )}

        {selectedCard &&
          (selectedCard.type === "text" ? (
            <TextCardDetail card={selectedCard} />
          ) : (
            <ToolCardDetail card={selectedCard} />
          ))}
      </div>
    </div>
  );
}
