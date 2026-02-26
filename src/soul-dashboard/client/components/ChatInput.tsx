/**
 * ChatInput - Soul 인터벤션 입력 컴포넌트
 *
 * 활성 세션에 메시지를 전송하여 실행 중인 Claude에 개입합니다.
 * POST /api/sessions/:id/message 엔드포인트를 호출합니다.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useDashboardStore } from "../stores/dashboard-store";

const ACCENT = "#f97316";
const MAX_LENGTH = 50_000;

export function ChatInput() {
  const activeSessionKey = useDashboardStore((s) => s.activeSessionKey);
  const sessions = useDashboardStore((s) => s.sessions);

  // 활성 세션의 상태에 따라 라벨 결정: running → "Intervention", 그 외 → "Chat"
  const isRunning = useMemo(() => {
    if (!activeSessionKey) return false;
    const session = sessions.find(
      (s) => `${s.clientId}:${s.requestId}` === activeSessionKey,
    );
    return session?.status === "running";
  }, [activeSessionKey, sessions]);

  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSent, setLastSent] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 세션 변경 시 상태 초기화 & in-flight 요청 취소
  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setText("");
    setSending(false);
    setError(null);
    setLastSent(null);
  }, [activeSessionKey]);

  // textarea 높이 자동 조절
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
    }
  }, [text]);

  const sendMessage = useCallback(async () => {
    if (!activeSessionKey || !text.trim() || sending) return;

    const trimmed = text.trim();
    if (trimmed.length > MAX_LENGTH) {
      setError(`Message too long (${trimmed.length}/${MAX_LENGTH})`);
      return;
    }

    // 이전 요청 취소
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setSending(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/sessions/${encodeURIComponent(activeSessionKey)}/message`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: trimmed,
            user: "dashboard",
          }),
          signal: controller.signal,
        },
      );

      if (!response.ok) {
        const body = await response.json().catch(() => ({ error: { message: "Unknown error" } }));
        throw new Error(body.error?.message ?? `HTTP ${response.status}`);
      }

      setLastSent(trimmed);
      setText("");
    } catch (err) {
      // AbortError는 의도적 취소이므로 무시
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Failed to send");
    } finally {
      setSending(false);
    }
  }, [activeSessionKey, text, sending]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Ctrl+Enter / Cmd+Enter로 전송
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        sendMessage();
      }
    },
    [sendMessage],
  );

  if (!activeSessionKey) return null;

  return (
    <div
      data-testid="chat-input"
      style={{
        borderTop: "1px solid rgba(255,255,255,0.08)",
        padding: "12px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        flexShrink: 0,
      }}
    >
      {/* Label */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          fontSize: "11px",
          color: "#6b7280",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          fontWeight: 600,
        }}
      >
        <span style={{ fontSize: "12px" }}>{isRunning ? "\u270B" : "\uD83D\uDCAC"}</span>
        {isRunning ? "Intervention" : "Chat"}
      </div>

      {/* Input area */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          alignItems: "flex-end",
        }}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Send a message to Claude..."
          disabled={sending}
          rows={1}
          style={{
            flex: 1,
            backgroundColor: "rgba(0,0,0,0.3)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "6px",
            padding: "8px 10px",
            fontSize: "13px",
            color: "#d1d5db",
            fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            resize: "none",
            outline: "none",
            minHeight: "36px",
            maxHeight: "120px",
            lineHeight: "1.4",
            transition: "border-color 0.15s",
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "rgba(249, 115, 22, 0.4)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)";
          }}
        />
        <button
          data-testid="send-button"
          onClick={sendMessage}
          disabled={sending || !text.trim()}
          style={{
            padding: "8px 14px",
            borderRadius: "6px",
            border: "none",
            backgroundColor: sending || !text.trim()
              ? "rgba(255,255,255,0.05)"
              : ACCENT,
            color: sending || !text.trim() ? "#6b7280" : "#fff",
            fontSize: "12px",
            fontWeight: 600,
            cursor: sending || !text.trim() ? "default" : "pointer",
            flexShrink: 0,
            height: "36px",
            transition: "all 0.15s",
          }}
        >
          {sending ? "..." : "Send"}
        </button>
      </div>

      {/* Hint */}
      <div style={{ fontSize: "10px", color: "#4b5563" }}>
        Ctrl+Enter to send
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            fontSize: "11px",
            color: "#ef4444",
            padding: "4px 8px",
            borderRadius: "4px",
            backgroundColor: "rgba(239, 68, 68, 0.08)",
          }}
        >
          {error}
        </div>
      )}

      {/* Last sent confirmation */}
      {lastSent && !error && (
        <div
          style={{
            fontSize: "11px",
            color: "#22c55e",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {"\u2705"} Sent: {lastSent.length > 60 ? lastSent.slice(0, 57) + "..." : lastSent}
        </div>
      )}
    </div>
  );
}
