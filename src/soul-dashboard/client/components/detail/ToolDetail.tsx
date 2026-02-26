/**
 * ToolDetail - 도구 호출 카드 상세 뷰
 *
 * 도구 이름, 입력 파라미터, 실행 결과를 상세히 표시합니다.
 * 에러가 아닌 일반 도구 호출에 사용됩니다.
 */

import type { DashboardCard } from "@shared/types";

const monoFont = "'Cascadia Code', 'Fira Code', monospace";

export function ToolDetail({ card }: { card: DashboardCard }) {
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
        <span style={{ fontSize: "16px" }}>{"\u{1F527}"}</span>
        <div
          style={{
            fontSize: "11px",
            color: "#f59e0b",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            fontWeight: 600,
          }}
        >
          Tool Call
        </div>
        {!card.completed && (
          <span
            style={{
              marginLeft: "auto",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "11px",
              color: "#f59e0b",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: "#f59e0b",
                animation: "pulse 2s infinite",
              }}
            />
            Running...
          </span>
        )}
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
          {card.toolName ?? "unknown"}
        </div>
      </div>

      {/* Tool input */}
      {card.toolInput && (
        <div>
          <SectionLabel>Input</SectionLabel>
          <CodeBlock>{JSON.stringify(card.toolInput, null, 2)}</CodeBlock>
        </div>
      )}

      {/* Tool result */}
      {card.toolResult !== undefined && (
        <div>
          <SectionLabel>Result</SectionLabel>
          <CodeBlock>{card.toolResult}</CodeBlock>
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

/** 코드 블록 */
function CodeBlock({ children }: { children: React.ReactNode }) {
  return (
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
      {children}
    </pre>
  );
}
