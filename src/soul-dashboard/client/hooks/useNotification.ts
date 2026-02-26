/**
 * useNotification - 브라우저 알림 훅
 *
 * Soul 세션의 주요 이벤트(완료, 에러, 인터벤션 요청)에 대해
 * 브라우저 Notification API를 통해 알림을 표시합니다.
 *
 * 탭이 비활성 상태(document.hidden)일 때만 알림을 표시하여
 * 사용자가 대시보드를 보고 있을 때는 방해하지 않습니다.
 */

import { useEffect, useRef, useCallback } from "react";
import { useDashboardStore } from "../stores/dashboard-store";
import type { SoulSSEEvent } from "@shared/types";

/** 알림을 트리거하는 이벤트 타입 */
const NOTIFY_EVENT_TYPES = new Set(["complete", "error", "intervention_sent"]);

/**
 * 브라우저 알림 권한을 요청하고 이벤트 기반 알림을 관리합니다.
 *
 * @param enabled - 알림 활성화 여부 (기본 true)
 */
export function useNotification(enabled = true) {
  const graphEvents = useDashboardStore((s) => s.graphEvents);
  const activeSessionKey = useDashboardStore((s) => s.activeSessionKey);

  // 이미 알림을 보낸 이벤트 수를 추적 (중복 방지)
  const notifiedCountRef = useRef(0);

  // 알림 자동 닫기 타이머를 추적 (메모리 누수 방지)
  const timersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  // 세션 변경 시 카운터 리셋
  useEffect(() => {
    notifiedCountRef.current = 0;
  }, [activeSessionKey]);

  // 컴포넌트 언마운트 시 타이머 정리
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      for (const t of timers) clearTimeout(t);
      timers.clear();
    };
  }, []);

  // 알림 권한 요청
  useEffect(() => {
    if (!enabled) return;
    if (typeof Notification === "undefined") return;

    if (Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, [enabled]);

  /** 브라우저 알림 표시 */
  const showNotification = useCallback(
    (title: string, body: string, tag?: string) => {
      if (!enabled) return;
      if (typeof Notification === "undefined") return;
      if (Notification.permission !== "granted") return;

      // 탭이 활성 상태면 알림 불필요
      if (!document.hidden) return;

      try {
        const notification = new Notification(title, {
          body,
          tag: tag ?? `soul-${Date.now()}`,
          icon: "/favicon.ico",
          silent: false,
        });

        // 알림 클릭 시 탭으로 포커스
        notification.onclick = () => {
          window.focus();
          notification.close();
        };

        // 10초 후 자동 닫기 (타이머 추적하여 언마운트 시 정리)
        const timer = setTimeout(() => {
          notification.close();
          timersRef.current.delete(timer);
        }, 10_000);
        timersRef.current.add(timer);
      } catch {
        // Notification 생성 실패 (Service Worker 환경 등)
      }
    },
    [enabled],
  );

  // 새 이벤트 감지 → 알림
  useEffect(() => {
    if (!enabled || !activeSessionKey) return;

    // 아직 처리하지 않은 이벤트만 확인
    const newEvents = graphEvents.slice(notifiedCountRef.current);
    notifiedCountRef.current = graphEvents.length;

    for (const event of newEvents) {
      if (!NOTIFY_EVENT_TYPES.has(event.type)) continue;

      const { title, body } = formatNotification(event);
      showNotification(title, body, `soul-${event.type}-${graphEvents.length}`);
    }
  }, [graphEvents, activeSessionKey, enabled, showNotification]);

  return { showNotification };
}

/**
 * 이벤트 타입에 따라 알림 제목과 본문을 생성합니다.
 */
function formatNotification(event: SoulSSEEvent): { title: string; body: string } {
  switch (event.type) {
    case "complete":
      return {
        title: "\u2705 Session Complete",
        body: event.result
          ? event.result.length > 100
            ? event.result.slice(0, 97) + "..."
            : event.result
          : "Session completed successfully",
      };

    case "error":
      return {
        title: "\u274C Session Error",
        body: event.message || "An error occurred",
      };

    case "intervention_sent":
      return {
        title: `\u270B Intervention (${event.user})`,
        body: event.text.length > 100
          ? event.text.slice(0, 97) + "..."
          : event.text,
      };

    default:
      return {
        title: "Soul Dashboard",
        body: `Event: ${event.type}`,
      };
  }
}
