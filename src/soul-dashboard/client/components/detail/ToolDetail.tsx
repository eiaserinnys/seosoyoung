/**
 * ToolDetail - 도구 호출 카드 상세 뷰
 *
 * 도구 이름, 입력 파라미터, 실행 결과를 상세히 표시합니다.
 * 에러가 아닌 일반 도구 호출에 사용됩니다.
 */

import type { DashboardCard } from "@shared/types";
import { monoFont, SectionLabel, CodeBlock, safeStringify } from "./shared";

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
          <CodeBlock>{safeStringify(card.toolInput)}</CodeBlock>
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
