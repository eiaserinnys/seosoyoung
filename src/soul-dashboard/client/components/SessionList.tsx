/**
 * SessionList + SessionItem - 세션 목록 컴포넌트
 *
 * 좌측 패널에 세션 목록을 표시합니다.
 * 각 세션의 상태를 인디케이터(점멸/뱃지)로 시각화합니다.
 */

import type { SessionSummary, SessionStatus } from "@shared/types";
import { useDashboardStore } from "../stores/dashboard-store";

// === Status Badge Config ===

interface StatusConfig {
  label: string;
  color: string;
  bgColor: string;
  animate: boolean;
}

const STATUS_CONFIG: Record<SessionStatus, StatusConfig> = {
  running: {
    label: "Running",
    color: "#22c55e",
    bgColor: "rgba(34, 197, 94, 0.15)",
    animate: true,
  },
  completed: {
    label: "Done",
    color: "#6b7280",
    bgColor: "rgba(107, 114, 128, 0.15)",
    animate: false,
  },
  error: {
    label: "Error",
    color: "#ef4444",
    bgColor: "rgba(239, 68, 68, 0.15)",
    animate: false,
  },
  unknown: {
    label: "Unknown",
    color: "#9ca3af",
    bgColor: "rgba(156, 163, 175, 0.15)",
    animate: false,
  },
};

// === SessionItem ===

interface SessionItemProps {
  session: SessionSummary;
  isActive: boolean;
  onClick: () => void;
}

function SessionItem({ session, isActive, onClick }: SessionItemProps) {
  const config = STATUS_CONFIG[session.status];
  const sessionKey = `${session.clientId}:${session.requestId}`;

  // 시간 포맷
  const timeStr = session.createdAt
    ? new Date(session.createdAt).toLocaleString("ko-KR", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "...";

  return (
    <button
      data-testid={`session-item-${sessionKey}`}
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        width: "100%",
        padding: "10px 12px",
        border: "none",
        borderLeft: isActive ? "3px solid #3b82f6" : "3px solid transparent",
        background: isActive ? "rgba(59, 130, 246, 0.08)" : "transparent",
        cursor: "pointer",
        textAlign: "left",
        transition: "background 0.15s",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
      title={sessionKey}
    >
      {/* Status indicator (점멸 애니메이션) */}
      <span
        style={{
          width: "8px",
          height: "8px",
          borderRadius: "50%",
          backgroundColor: config.color,
          flexShrink: 0,
          animation: config.animate ? "pulse 2s infinite" : "none",
        }}
      />

      {/* Session info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "13px",
            color: "#e5e7eb",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {session.requestId.slice(0, 8)}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            marginTop: "2px",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              color: "#9ca3af",
            }}
          >
            {timeStr}
          </span>
          <span
            data-testid="session-status-badge"
            style={{
              fontSize: "10px",
              color: config.color,
              backgroundColor: config.bgColor,
              padding: "1px 5px",
              borderRadius: "3px",
              fontWeight: 500,
            }}
          >
            {config.label}
          </span>
        </div>
      </div>

      {/* Event count badge */}
      {session.eventCount > 0 && (
        <span
          style={{
            fontSize: "11px",
            color: "#6b7280",
            backgroundColor: "rgba(107, 114, 128, 0.2)",
            padding: "1px 5px",
            borderRadius: "8px",
            flexShrink: 0,
          }}
        >
          {session.eventCount}
        </span>
      )}
    </button>
  );
}

// === SessionList ===

interface SessionListProps {
  sessions: SessionSummary[];
  loading: boolean;
  error: string | null;
}

export function SessionList({ sessions, loading, error }: SessionListProps) {
  const activeSessionKey = useDashboardStore((s) => s.activeSessionKey);
  const setActiveSession = useDashboardStore((s) => s.setActiveSession);

  const handleSelect = (session: SessionSummary) => {
    const key = `${session.clientId}:${session.requestId}`;
    setActiveSession(key);
  };

  return (
    <div
      data-testid="session-list"
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
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span>Sessions</span>
        <span style={{ color: "#6b7280", fontWeight: 400 }}>
          {sessions.length}
        </span>
      </div>

      {/* Loading state */}
      {loading && sessions.length === 0 && (
        <div
          style={{
            padding: "20px",
            textAlign: "center",
            color: "#6b7280",
            fontSize: "13px",
          }}
        >
          Loading...
        </div>
      )}

      {/* Error state */}
      {error && (
        <div
          style={{
            padding: "10px 14px",
            color: "#ef4444",
            fontSize: "12px",
            backgroundColor: "rgba(239, 68, 68, 0.08)",
          }}
        >
          {error}
        </div>
      )}

      {/* Session list */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          overflowX: "hidden",
        }}
      >
        {sessions.length === 0 && !loading && (
          <div
            style={{
              padding: "20px",
              textAlign: "center",
              color: "#6b7280",
              fontSize: "13px",
            }}
          >
            No sessions yet
          </div>
        )}
        {sessions.map((session) => {
          const key = `${session.clientId}:${session.requestId}`;
          return (
            <SessionItem
              key={key}
              session={session}
              isActive={activeSessionKey === key}
              onClick={() => handleSelect(session)}
            />
          );
        })}
      </div>
    </div>
  );
}
