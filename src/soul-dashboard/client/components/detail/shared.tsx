/**
 * Detail 컴포넌트 공통 유틸리티
 *
 * SectionLabel, CodeBlock, monoFont 등 상세 뷰 컴포넌트에서
 * 공통으로 사용되는 스타일 요소를 정의합니다.
 */

export const monoFont = "'Cascadia Code', 'Fira Code', monospace";

/** 섹션 라벨 */
export function SectionLabel({ children }: { children: React.ReactNode }) {
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
export function CodeBlock({
  children,
  variant = "default",
  maxHeight = 300,
}: {
  children: React.ReactNode;
  variant?: "default" | "error";
  maxHeight?: number;
}) {
  const color = variant === "error" ? "#fca5a5" : "#9ca3af";
  const bg =
    variant === "error" ? "rgba(239, 68, 68, 0.08)" : "rgba(0,0,0,0.3)";

  return (
    <pre
      style={{
        fontSize: "12px",
        color,
        backgroundColor: bg,
        padding: "10px",
        borderRadius: "6px",
        overflow: "auto",
        maxHeight,
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

/** JSON.stringify의 안전한 래퍼 (circular reference 방어) */
export function safeStringify(obj: unknown, indent = 2): string {
  try {
    return JSON.stringify(obj, null, indent);
  } catch {
    return String(obj);
  }
}
