/**
 * useSession - SSE 구독 훅
 *
 * 특정 세션의 /api/sessions/:id/events SSE 스트림을 구독합니다.
 * Last-Event-ID를 지원하여 재연결 시 놓친 이벤트를 복구합니다.
 */

import { useEffect, useRef, useCallback, useState } from "react";
import { useDashboardStore } from "../stores/dashboard-store";
import type { SoulSSEEvent, SSEEventType } from "@shared/types";

interface UseSessionOptions {
  /** 구독할 세션 키 (clientId:requestId). null이면 구독 안 함 */
  sessionKey: string | null;
  /** 자동 재연결 활성화. 기본 true */
  autoReconnect?: boolean;
  /** 재연결 간격 (ms). 기본 3000 */
  reconnectIntervalMs?: number;
  /** 최대 재연결 간격 (ms). 기본 30000 */
  maxReconnectIntervalMs?: number;
  /** 최대 재연결 시도 횟수. 기본 20 */
  maxReconnectAttempts?: number;
}

type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

/** SSE 이벤트 타입 목록 (구독 등록용) */
const SSE_EVENT_TYPES: SSEEventType[] = [
  "progress",
  "memory",
  "session",
  "intervention_sent",
  "user_message",
  "debug",
  "complete",
  "error",
  "text_start",
  "text_delta",
  "text_end",
  "tool_start",
  "tool_result",
  "result",
  "context_usage",
  "compact",
  "reconnect",
];

/** 세션 종료 이벤트 타입 */
const TERMINAL_EVENTS = new Set<string>(["complete", "error"]);

export function useSession(options: UseSessionOptions) {
  const {
    sessionKey,
    autoReconnect = true,
    reconnectIntervalMs = 3000,
    maxReconnectIntervalMs = 30000,
    maxReconnectAttempts = 20,
  } = options;

  const processEvent = useDashboardStore((s) => s.processEvent);
  const lastEventId = useDashboardStore((s) => s.lastEventId);

  const [status, setStatus] = useState<ConnectionStatus>("disconnected");

  // Refs: stale closure 방지를 위해 최신 값을 ref로 동기화
  const processEventRef = useRef(processEvent);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const lastEventIdRef = useRef(0);
  const isTerminalRef = useRef(false);

  // 최신 processEvent/lastEventId를 ref에 동기화
  useEffect(() => {
    processEventRef.current = processEvent;
  }, [processEvent]);

  useEffect(() => {
    lastEventIdRef.current = lastEventId;
  }, [lastEventId]);

  /** SSE 연결 닫기 */
  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setStatus("disconnected");
  }, []);

  /** SSE 연결 생성 */
  const connect = useCallback(() => {
    if (!sessionKey) return;

    // 기존 연결 정리
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setStatus("connecting");

    // URL 구성: sessionKey를 인코딩하여 특수문자 안전 보장
    let url = `/api/sessions/${encodeURIComponent(sessionKey)}/events`;
    if (lastEventIdRef.current > 0) {
      url += `?lastEventId=${lastEventIdRef.current}`;
    }

    const es = new EventSource(url);
    eventSourceRef.current = es;

    // 연결 성공
    es.onopen = () => {
      setStatus("connected");
      reconnectAttemptRef.current = 0;
    };

    // 타입별 이벤트 리스너 등록 (ref 경유로 stale closure 방지)
    for (const eventType of SSE_EVENT_TYPES) {
      es.addEventListener(eventType, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data) as SoulSSEEvent;
          const eventId = e.lastEventId ? parseInt(e.lastEventId, 10) : 0;

          processEventRef.current(data, eventId);

          // 터미널 이벤트면 연결 종료 (재연결 불필요)
          if (TERMINAL_EVENTS.has(eventType)) {
            isTerminalRef.current = true;
            es.close();
            eventSourceRef.current = null;
            setStatus("disconnected");
          }
        } catch {
          // JSON 파싱 실패: 무시 (keepalive 등)
        }
      });
    }

    // 에러 처리 & 재연결
    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;

      // 터미널 이벤트 이후의 에러는 재연결하지 않음
      if (isTerminalRef.current) {
        setStatus("disconnected");
        return;
      }

      setStatus("error");

      const attempt = reconnectAttemptRef.current;
      if (autoReconnect && attempt < maxReconnectAttempts) {
        // 지수적 백오프 (상한: maxReconnectIntervalMs)
        const delay = Math.min(
          reconnectIntervalMs * Math.pow(2, attempt),
          maxReconnectIntervalMs,
        );
        reconnectAttemptRef.current = attempt + 1;

        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connect();
        }, delay);
      } else if (attempt >= maxReconnectAttempts) {
        // 재연결 상한 도달 — 포기
        setStatus("disconnected");
      }
    };
  }, [
    sessionKey,
    autoReconnect,
    reconnectIntervalMs,
    maxReconnectIntervalMs,
    maxReconnectAttempts,
  ]);

  // sessionKey 변경 시 연결 관리
  useEffect(() => {
    isTerminalRef.current = false;
    reconnectAttemptRef.current = 0;

    if (sessionKey) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [sessionKey, connect, disconnect]);

  return {
    status,
    connect,
    disconnect,
  };
}
