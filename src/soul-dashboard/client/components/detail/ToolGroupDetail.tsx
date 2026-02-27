/**
 * ToolGroupDetail - 도구 그룹 노드 상세 뷰
 *
 * 그룹 노드를 클릭했을 때 그룹 내 모든 개별 도구 호출을 목록으로 표시합니다.
 * 각 호출의 입력 파라미터 요약과 에러 여부를 보여줍니다.
 */

import type { DashboardCard } from "@shared/types";
import { monoFont, SectionLabel } from "./shared";
import { useDashboardStore } from "../../stores/dashboard-store";

/** ToolGroupDetail에 전달되는 데이터 타입 (스토어의 selectedEventNodeData에서 추출) */
export interface ToolGroupData {
  nodeType: string;
  label: string;
  content: string;
  groupedCardIds: string[];
  toolName?: string;
  groupCount?: number;
}

export function ToolGroupDetail({ data }: { data: ToolGroupData }) {
  const cards = useDashboardStore((s) => s.cards);
  const groupedCardIds = data.groupedCardIds ?? [];
  const groupedCards = groupedCardIds
    .map((id) => cards.find((c) => c.cardId === id))
    .filter((c): c is DashboardCard => c !== undefined);

  const toolName = data.toolName ?? "unknown";
  const count = data.groupCount ?? groupedCards.length;
  const errorCount = groupedCards.filter((c) => c.isError).length;

  return (
    <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <span style={{ fontSize: "16px" }}>📦</span>
        <div
          style={{
            fontSize: "11px",
            color: "#d97706",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            fontWeight: 600,
          }}
        >
          Tool Group
        </div>
        <span
          style={{
            marginLeft: "auto",
            fontSize: "12px",
            color: "#d97706",
            fontWeight: 700,
            padding: "2px 8px",
            borderRadius: 4,
            backgroundColor: "rgba(217, 119, 6, 0.12)",
          }}
        >
          ×{count}
        </span>
      </div>

      {/* Tool name */}
      <div>
        <SectionLabel>Tool</SectionLabel>
        <div
          style={{
            fontSize: "14px",
            color: "#e5e7eb",
            fontWeight: 600,
            fontFamily: monoFont,
          }}
        >
          {toolName}
        </div>
      </div>

      {/* Summary */}
      <div>
        <SectionLabel>Summary</SectionLabel>
        <div style={{ fontSize: "12px", color: "#9ca3af" }}>
          {count} calls
          {errorCount > 0 && (
            <span style={{ color: "#ef4444", marginLeft: "8px" }}>
              ({errorCount} error{errorCount > 1 ? "s" : ""})
            </span>
          )}
        </div>
      </div>

      {/* Individual calls */}
      <div>
        <SectionLabel>Calls ({groupedCards.length})</SectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {groupedCards.map((card, idx) => (
            <div
              key={card.cardId}
              style={{
                background: card.isError
                  ? "rgba(239, 68, 68, 0.08)"
                  : "rgba(0,0,0,0.3)",
                borderRadius: "6px",
                padding: "8px 10px",
                borderLeft: `3px solid ${card.isError ? "#ef4444" : card.completed ? "#22c55e" : "#f59e0b"}`,
              }}
            >
              {/* Call header */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  marginBottom: "4px",
                }}
              >
                <span style={{ fontSize: "10px", color: "#6b7280" }}>
                  #{idx + 1}
                </span>
                <span
                  style={{
                    fontSize: "10px",
                    fontFamily: monoFont,
                    color: "#4b5563",
                  }}
                >
                  {card.cardId}
                </span>
                {card.isError && (
                  <span style={{ fontSize: "10px", color: "#ef4444", marginLeft: "auto" }}>
                    ❌ Error
                  </span>
                )}
                {!card.isError && card.completed && (
                  <span style={{ fontSize: "10px", color: "#22c55e", marginLeft: "auto" }}>
                    ✅
                  </span>
                )}
                {!card.completed && (
                  <span style={{ fontSize: "10px", color: "#f59e0b", marginLeft: "auto" }}>
                    ⏳ running
                  </span>
                )}
              </div>

              {/* Input summary */}
              {card.toolInput && (
                <div
                  style={{
                    fontSize: "11px",
                    color: "#9ca3af",
                    fontFamily: monoFont,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    marginBottom: card.toolResult ? "4px" : 0,
                  }}
                >
                  {summarizeInput(card.toolInput)}
                </div>
              )}

              {/* Result summary */}
              {card.toolResult !== undefined && (
                <div
                  style={{
                    fontSize: "11px",
                    color: card.isError ? "#fca5a5" : "#6b7280",
                    fontFamily: monoFont,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  → {card.toolResult.length > 80 ? card.toolResult.slice(0, 77) + "..." : card.toolResult}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** 입력 파라미터를 한 줄 요약으로 변환 */
function summarizeInput(input: Record<string, unknown>): string {
  const keys = Object.keys(input);
  if (keys.length === 0) return "(no input)";

  // 주요 필드 우선: file_path, command, pattern, query, prompt, url
  const priorityKeys = ["file_path", "command", "pattern", "query", "prompt", "url"];
  const key = priorityKeys.find((k) => k in input) ?? keys[0];
  const val = input[key];
  const str = typeof val === "string" ? val : JSON.stringify(val);
  const truncated = str && str.length > 60 ? str.slice(0, 57) + "..." : str;
  return `${key}: ${truncated}`;
}
