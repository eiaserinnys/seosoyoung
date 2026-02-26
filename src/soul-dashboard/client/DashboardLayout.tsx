/**
 * DashboardLayout - 3패널 레이아웃
 *
 * SessionList | NodeGraph + ChatInput | DetailView 구성.
 * SSE 구독, 세션 목록 폴링, 브라우저 알림을 여기서 초기화합니다.
 */

import { SessionList } from "./components/SessionList";
import { NodeGraph } from "./components/NodeGraph";
import { DetailView } from "./components/DetailView";
import { ChatInput } from "./components/ChatInput";
import { useSessionList } from "./hooks/useSessionList";
import { useSession } from "./hooks/useSession";
import { useNotification } from "./hooks/useNotification";
import { useDashboardStore } from "./stores/dashboard-store";

// === Connection Status Badge ===

function ConnectionBadge({
  status,
}: {
  status: "disconnected" | "connecting" | "connected" | "error";
}) {
  const config = {
    disconnected: { label: "Idle", color: "#6b7280" },
    connecting: { label: "Connecting...", color: "#f59e0b" },
    connected: { label: "Live", color: "#22c55e" },
    error: { label: "Reconnecting...", color: "#ef4444" },
  }[status];

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        fontSize: "11px",
        color: config.color,
      }}
    >
      <span
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          backgroundColor: config.color,
          animation:
            status === "connected" || status === "connecting"
              ? "pulse 2s infinite"
              : "none",
        }}
      />
      {config.label}
    </span>
  );
}

// === Main Layout ===

export function DashboardLayout() {
  const activeSessionKey = useDashboardStore((s) => s.activeSessionKey);

  // 세션 목록 폴링
  const { sessions, loading, error } = useSessionList({ intervalMs: 5000 });

  // 활성 세션 SSE 구독
  const { status: sseStatus } = useSession({
    sessionKey: activeSessionKey,
  });

  // 브라우저 알림 (완료/에러/인터벤션)
  useNotification();

  return (
    <div
      data-testid="dashboard-layout"
      style={{
        display: "flex",
        flexDirection: "column",
        width: "100vw",
        height: "100vh",
        backgroundColor: "#111827",
        color: "#e5e7eb",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        overflow: "hidden",
      }}
    >
      {/* Top bar */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 16px",
          height: "40px",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          backgroundColor: "rgba(0,0,0,0.2)",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "#9ca3af",
            letterSpacing: "0.02em",
          }}
        >
          Soul Dashboard
        </span>
        <ConnectionBadge status={sseStatus} />
      </header>

      {/* 3-Panel content */}
      <div
        style={{
          display: "flex",
          flex: 1,
          overflow: "hidden",
        }}
      >
        {/* Left: Session List */}
        <aside
          data-testid="session-panel"
          style={{
            width: "240px",
            flexShrink: 0,
            borderRight: "1px solid rgba(255,255,255,0.08)",
            overflow: "hidden",
          }}
        >
          <SessionList sessions={sessions} loading={loading} error={error} />
        </aside>

        {/* Center: Node Graph + Chat Input */}
        <main
          data-testid="graph-panel"
          style={{
            flex: 1,
            borderRight: "1px solid rgba(255,255,255,0.08)",
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ flex: 1, overflow: "hidden" }}>
            <NodeGraph />
          </div>
          <ChatInput />
        </main>

        {/* Right: Detail View */}
        <aside
          data-testid="detail-panel"
          style={{
            width: "360px",
            flexShrink: 0,
            overflow: "hidden",
          }}
        >
          <DetailView />
        </aside>
      </div>
    </div>
  );
}
