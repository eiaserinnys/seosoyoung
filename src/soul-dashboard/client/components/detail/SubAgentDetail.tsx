/**
 * SubAgentDetail - 서브 에이전트 (Task) 카드 상세 뷰
 *
 * Task 도구 호출의 상세 정보를 표시합니다.
 * description, prompt, subagent_type 등의 필드를 분리하여 보여줍니다.
 */

import type { DashboardCard } from "@shared/types";

const monoFont = "'Cascadia Code', 'Fira Code', monospace";

export function SubAgentDetail({ card }: { card: DashboardCard }) {
  const input = card.toolInput ?? {};
  const description = (input.description as string) ?? "";
  const prompt = (input.prompt as string) ?? "";
  const subagentType = (input.subagent_type as string) ?? "unknown";

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
        <span style={{ fontSize: "16px" }}>{"\u{1F916}"}</span>
        <div
          style={{
            fontSize: "11px",
            color: "#3b82f6",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            fontWeight: 600,
          }}
        >
          Sub-Agent
        </div>
        {!card.completed && (
          <span
            style={{
              marginLeft: "auto",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "11px",
              color: "#3b82f6",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: "#3b82f6",
                animation: "pulse 2s infinite",
              }}
            />
            Running...
          </span>
        )}
      </div>

      {/* Agent type badge */}
      <div>
        <SectionLabel>Agent Type</SectionLabel>
        <span
          style={{
            display: "inline-block",
            padding: "2px 8px",
            borderRadius: "4px",
            backgroundColor: "rgba(59, 130, 246, 0.15)",
            color: "#60a5fa",
            fontSize: "12px",
            fontWeight: 600,
            fontFamily: monoFont,
          }}
        >
          {subagentType}
        </span>
      </div>

      {/* Description */}
      {description && (
        <div>
          <SectionLabel>Description</SectionLabel>
          <div
            style={{
              fontSize: "13px",
              color: "#d1d5db",
              lineHeight: "1.5",
            }}
          >
            {description}
          </div>
        </div>
      )}

      {/* Prompt */}
      {prompt && (
        <div>
          <SectionLabel>Prompt</SectionLabel>
          <pre
            style={{
              fontSize: "12px",
              color: "#9ca3af",
              backgroundColor: "rgba(0,0,0,0.3)",
              padding: "10px",
              borderRadius: "6px",
              overflow: "auto",
              maxHeight: "300px",
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: monoFont,
            }}
          >
            {prompt}
          </pre>
        </div>
      )}

      {/* Result (if completed) */}
      {card.toolResult !== undefined && (
        <div>
          <SectionLabel>{card.isError ? "Error" : "Result"}</SectionLabel>
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
              fontFamily: monoFont,
            }}
          >
            {card.toolResult}
          </pre>
        </div>
      )}
    </div>
  );
}

/** 섹션 라벨 */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: "11px",
        color: "#6b7280",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        marginBottom: "4px",
      }}
    >
      {children}
    </div>
  );
}
