/**
 * Soul Dashboard - Zustand Store
 *
 * 대시보드 전역 상태 관리.
 * 세션 목록, 활성 세션, 선택된 카드, SSE 이벤트 처리를 담당합니다.
 */

import { create } from "zustand";
import type {
  SessionSummary,
  SessionDetail,
  DashboardCard,
  SoulSSEEvent,
} from "@shared/types";

// === State Interface ===

export interface DashboardState {
  /** 세션 목록 */
  sessions: SessionSummary[];
  sessionsLoading: boolean;
  sessionsError: string | null;

  /** 활성 세션 (현재 보고 있는 세션) */
  activeSessionKey: string | null;
  activeSession: SessionDetail | null;

  /** 선택된 카드 (상세 뷰에 표시) */
  selectedCardId: string | null;

  /** 선택된 이벤트 노드 데이터 (user/intervention/tool_group 노드용, 카드 기반이 아닌 노드) */
  selectedEventNodeData: {
    nodeType: string;
    label: string;
    content: string;
    /** tool_group 노드: 그룹 내 카드 ID 목록 */
    groupedCardIds?: string[];
    /** tool_group 노드: 도구 이름 */
    toolName?: string;
    /** tool_group 노드: 그룹 내 도구 개수 */
    groupCount?: number;
  } | null;

  /** 활성 세션의 카드 목록 (SSE 이벤트로 구성) */
  cards: DashboardCard[];

  /**
   * 그래프 레이아웃에 영향을 주는 SSE 이벤트만 저장.
   * session, complete, error, intervention_sent 이벤트만 포함합니다.
   * text_delta 등 노이즈성 이벤트는 저장하지 않아 메모리 사용을 제한합니다.
   */
  graphEvents: SoulSSEEvent[];

  /** 접힌 서브 에이전트 그룹 ID 집합 */
  collapsedGroups: Set<string>;

  /** 마지막으로 수신한 이벤트 ID (SSE 재연결용) */
  lastEventId: number;
}

// === Actions Interface ===

export interface DashboardActions {
  // 세션 목록
  setSessions: (sessions: SessionSummary[]) => void;
  setSessionsLoading: (loading: boolean) => void;
  setSessionsError: (error: string | null) => void;

  // 활성 세션
  setActiveSession: (key: string | null, detail?: SessionDetail) => void;

  // 카드 선택
  selectCard: (cardId: string | null) => void;

  // 이벤트 노드 선택 (user/intervention/tool_group 등 카드가 아닌 노드)
  selectEventNode: (data: {
    nodeType: string;
    label: string;
    content: string;
    groupedCardIds?: string[];
    toolName?: string;
    groupCount?: number;
  } | null) => void;

  // SSE 이벤트 처리
  processEvent: (event: SoulSSEEvent, eventId: number) => void;

  // 서브 에이전트 그룹 접기/펼치기
  toggleGroupCollapse: (groupId: string) => void;

  // 상태 초기화
  clearCards: () => void;
  reset: () => void;
}

// === Initial State ===

const initialState: DashboardState = {
  sessions: [],
  sessionsLoading: false,
  sessionsError: null,
  activeSessionKey: null,
  activeSession: null,
  selectedCardId: null,
  selectedEventNodeData: null,
  cards: [],
  graphEvents: [],
  collapsedGroups: new Set<string>(),
  lastEventId: 0,
};

// === Store ===

export const useDashboardStore = create<DashboardState & DashboardActions>(
  (set, get) => ({
    ...initialState,

    // --- 세션 목록 ---

    setSessions: (sessions) => set({ sessions, sessionsError: null }),

    setSessionsLoading: (sessionsLoading) => set({ sessionsLoading }),

    setSessionsError: (sessionsError) =>
      set({ sessionsError, sessionsLoading: false }),

    // --- 활성 세션 ---

    setActiveSession: (key, detail) =>
      set({
        activeSessionKey: key,
        activeSession: detail ?? null,
        selectedCardId: null,
        selectedEventNodeData: null,
        cards: [],
        graphEvents: [],
        collapsedGroups: new Set<string>(),
        lastEventId: 0,
      }),

    // --- 카드 선택 ---

    selectCard: (cardId) => set({ selectedCardId: cardId, selectedEventNodeData: null }),

    // --- 이벤트 노드 선택 ---

    selectEventNode: (data) => set({ selectedEventNodeData: data, selectedCardId: null }),

    // --- SSE 이벤트 처리 ---
    // 주의: 카드 객체를 직접 변경하지 않고, 새 객체를 생성하여 참조 동등성을 보장합니다.

    processEvent: (event, eventId) => {
      const state = get();
      const cards = [...state.cards];
      // 그래프 레이아웃에 영향을 주는 이벤트만 저장 (메모리 절약)
      const isGraphRelevant =
        event.type === "session" ||
        event.type === "complete" ||
        event.type === "error" ||
        event.type === "intervention_sent" ||
        event.type === "user_message";
      const graphEvents = isGraphRelevant
        ? [...state.graphEvents, event]
        : state.graphEvents;
      let updated = false;

      switch (event.type) {
        // 텍스트 카드 시작
        case "text_start": {
          cards.push({
            cardId: event.card_id,
            type: "text",
            content: "",
            completed: false,
          });
          updated = true;
          break;
        }

        // 텍스트 카드 델타 (누적) — 새 객체 생성으로 참조 변경 보장
        case "text_delta": {
          const idx = cards.findIndex((c) => c.cardId === event.card_id);
          if (idx !== -1) {
            cards[idx] = {
              ...cards[idx],
              content: cards[idx].content + event.text,
            };
            updated = true;
          }
          break;
        }

        // 텍스트 카드 완료
        case "text_end": {
          const idx = cards.findIndex((c) => c.cardId === event.card_id);
          if (idx !== -1) {
            cards[idx] = { ...cards[idx], completed: true };
            updated = true;
          }
          break;
        }

        // 도구 카드 시작 — 항상 고유 cardId 부여, parentCardId로 thinking 연결 보존
        case "tool_start": {
          const cardId = `tool-${eventId}`;
          cards.push({
            cardId,
            type: "tool",
            content: "",
            toolName: event.tool_name,
            toolInput: event.tool_input,
            completed: false,
            toolUseId: event.tool_use_id,
            parentCardId: event.card_id,
          });
          updated = true;
          break;
        }

        // 도구 카드 결과 — tool_use_id 우선, 실패 시 tool_name으로 폴백 매칭
        case "tool_result": {
          let idx = -1;
          // 1차: tool_use_id로 정확 매칭 (가장 신뢰성 높음)
          if (event.tool_use_id) {
            idx = cards.findIndex(
              (c) => c.type === "tool" && c.toolUseId === event.tool_use_id,
            );
          }
          // 2차: card_id로 미완료 tool 카드 매칭
          if (idx === -1 && event.card_id) {
            idx = cards.findIndex(
              (c) => c.type === "tool" && !c.completed && c.parentCardId === event.card_id && c.toolName === event.tool_name,
            );
          }
          // 3차 폴백: tool_name으로 역순 재탐색
          if (idx === -1) {
            for (let i = cards.length - 1; i >= 0; i--) {
              if (
                cards[i].type === "tool" &&
                !cards[i].completed &&
                cards[i].toolName === event.tool_name
              ) {
                idx = i;
                break;
              }
            }
          }
          if (idx !== -1) {
            cards[idx] = {
              ...cards[idx],
              toolResult: event.result,
              isError: event.is_error,
              completed: true,
            };
            updated = true;
          }
          break;
        }

        // progress 이벤트: 텍스트 카드 없이 들어오는 경우 별도 처리 안 함
        // complete, error, result: 세션 상태 업데이트는 세션 목록 폴링이 담당
        default:
          break;
      }

      if (updated || isGraphRelevant) {
        set({ cards, graphEvents, lastEventId: eventId });
      } else {
        set({ lastEventId: eventId });
      }
    },

    // --- 서브 에이전트 그룹 ---

    toggleGroupCollapse: (groupId) => {
      const current = get().collapsedGroups;
      const next = new Set(current);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      set({ collapsedGroups: next });
    },

    // --- 초기화 ---

    clearCards: () =>
      set({
        cards: [],
        graphEvents: [],
        collapsedGroups: new Set<string>(),
        lastEventId: 0,
        selectedCardId: null,
        selectedEventNodeData: null,
      }),

    reset: () => set(initialState),
  }),
);
