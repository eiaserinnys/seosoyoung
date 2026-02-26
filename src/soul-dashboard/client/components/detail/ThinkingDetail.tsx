/**
 * ThinkingDetail - 텍스트/사고 카드 상세 뷰
 *
 * 선택된 텍스트 카드의 전체 내용을 표시합니다.
 * 스트리밍 중인 카드는 펄스 인디케이터를 함께 보여줍니다.
 */

import type { DashboardCard } from "@shared/types";
import { monoFont } from "./shared";

export function ThinkingDetail({ card }: { card: DashboardCard }) {
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
        <span style={{ fontSize: "16px" }}>{"\u{1F4AD}"}</span>
        <div
          style={{
            fontSize: "11px",
            color: "#8b5cf6",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            fontWeight: 600,
          }}
        >
          Thinking
        </div>
        {!card.completed && (
          <span
            style={{
              marginLeft: "auto",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "11px",
              color: "#8b5cf6",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: "#8b5cf6",
                animation: "pulse 2s infinite",
              }}
            />
            Streaming...
          </span>
        )}
      </div>

      {/* Full text content */}
      <pre
        style={{
          fontSize: "13px",
          color: "#d1d5db",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          lineHeight: "1.6",
          margin: 0,
          fontFamily: monoFont,
        }}
      >
        {card.content || "(streaming...)"}
      </pre>

      {/* Character count */}
      {card.content && (
        <div
          style={{
            fontSize: "10px",
            color: "#4b5563",
            textAlign: "right",
          }}
        >
          {card.content.length.toLocaleString()} chars
        </div>
      )}
    </div>
  );
}
