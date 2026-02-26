/**
 * ErrorDetail - 에러 카드 상세 뷰
 *
 * 도구 실행 중 에러가 발생한 카드의 상세 정보를 표시합니다.
 * 에러 메시지를 강조하고, 도구 이름과 입력 정보도 함께 보여줍니다.
 */

import type { DashboardCard } from "@shared/types";

const monoFont = "'Cascadia Code', 'Fira Code', monospace";

export function ErrorDetail({ card }: { card: DashboardCard }) {
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
        <span style={{ fontSize: "16px" }}>{"\u274C"}</span>
        <div
          style={{
            fontSize: "11px",
            color: "#ef4444",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            fontWeight: 600,
          }}
        >
          Error
        </div>
      </div>

      {/* Error banner */}
      <div
        style={{
          padding: "10px 12px",
          borderRadius: "6px",
          backgroundColor: "rgba(239, 68, 68, 0.1)",
          border: "1px solid rgba(239, 68, 68, 0.2)",
        }}
      >
        <div
          style={{
            fontSize: "12px",
            color: "#fca5a5",
            fontWeight: 600,
            marginBottom: "4px",
          }}
        >
          {card.toolName ?? "Tool"} failed
        </div>
        <pre
          style={{
            fontSize: "12px",
            color: "#fca5a5",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.5",
            margin: 0,
            fontFamily: monoFont,
          }}
        >
          {card.toolResult || "(no error message)"}
        </pre>
      </div>

      {/* Tool info */}
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
          {card.toolName ?? "unknown"}
        </div>
      </div>

      {/* Tool input that caused the error */}
      {card.toolInput && (
        <div>
          <SectionLabel>Input</SectionLabel>
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
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: monoFont,
            }}
          >
            {JSON.stringify(card.toolInput, null, 2)}
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
