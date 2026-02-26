/**
 * useSessionList - 세션 목록 폴링 훅
 *
 * /api/sessions를 주기적으로 폴링하여 스토어를 갱신합니다.
 * 마운트 시 즉시 1회 조회 + intervalMs 간격으로 반복.
 */

import { useEffect, useRef, useCallback } from "react";
import { useDashboardStore } from "../stores/dashboard-store";
import type { SessionSummary } from "@shared/types";

interface UseSessionListOptions {
  /** 폴링 간격 (ms). 기본 5000 */
  intervalMs?: number;
  /** 자동 폴링 활성화. 기본 true */
  enabled?: boolean;
}

interface SessionListResponse {
  sessions: SessionSummary[];
}

export function useSessionList(options: UseSessionListOptions = {}) {
  const { intervalMs = 5000, enabled = true } = options;

  const setSessions = useDashboardStore((s) => s.setSessions);
  const setSessionsLoading = useDashboardStore((s) => s.setSessionsLoading);
  const setSessionsError = useDashboardStore((s) => s.setSessionsError);

  const sessions = useDashboardStore((s) => s.sessions);
  const loading = useDashboardStore((s) => s.sessionsLoading);
  const error = useDashboardStore((s) => s.sessionsError);

  // 첫 로드 추적 (초기엔 로딩 표시, 이후엔 백그라운드 갱신)
  const isFirstLoad = useRef(true);
  const abortRef = useRef<AbortController | null>(null);

  const fetchSessions = useCallback(async () => {
    // 첫 로드에만 로딩 표시
    if (isFirstLoad.current) {
      setSessionsLoading(true);
    }

    try {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch("/api/sessions", {
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const data: SessionListResponse = await res.json();
      setSessions(data.sessions);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return; // 취소된 요청은 무시
      }
      const message = err instanceof Error ? err.message : "세션 목록 조회 실패";
      setSessionsError(message);
    } finally {
      // 항상 첫 로드 완료 표시 (에러 시에도 로딩 플리커 방지)
      isFirstLoad.current = false;
      setSessionsLoading(false);
    }
  }, [setSessions, setSessionsLoading, setSessionsError]);

  // 마운트 시 즉시 조회 + 폴링
  useEffect(() => {
    if (!enabled) return;

    // 즉시 1회 조회
    fetchSessions();

    // 인터벌 폴링
    const timer = setInterval(fetchSessions, intervalMs);

    return () => {
      clearInterval(timer);
      abortRef.current?.abort();
    };
  }, [fetchSessions, intervalMs, enabled]);

  return {
    sessions,
    loading,
    error,
    refetch: fetchSessions,
  };
}
