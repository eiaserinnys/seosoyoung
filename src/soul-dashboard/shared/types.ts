/**
 * Soul Dashboard - 공유 타입 정의
 *
 * 서버와 클라이언트 양쪽에서 사용하는 이벤트, 세션, 카드 타입.
 * Python Soul 서버의 schemas.py와 동기화를 유지합니다.
 */

// === SSE Event Types ===

/** Soul SSE 이벤트 타입 (Python SSEEventType과 동기화) */
export type SSEEventType =
  // 기본 이벤트
  | "progress"
  | "memory"
  | "session"
  | "intervention_sent"
  | "user_message"
  | "debug"
  | "complete"
  | "error"
  // 세분화 이벤트 (대시보드용)
  | "text_start"
  | "text_delta"
  | "text_end"
  | "tool_start"
  | "tool_result"
  | "result"
  // 대시보드 내부 이벤트
  | "context_usage"
  | "compact"
  | "reconnect";

// === Soul SSE Event Payloads ===

export interface ProgressEvent {
  type: "progress";
  text: string;
}

export interface MemoryEvent {
  type: "memory";
  used_gb: number;
  total_gb: number;
  percent: number;
}

export interface SessionEvent {
  type: "session";
  session_id: string;
}

export interface InterventionSentEvent {
  type: "intervention_sent";
  user: string;
  text: string;
}

/** 사용자가 보낸 초기 프롬프트 (세션 시작 시 대시보드가 생성) */
export interface UserMessageEvent {
  type: "user_message";
  user: string;
  text: string;
}

export interface DebugEvent {
  type: "debug";
  message: string;
}

export interface CompleteEvent {
  type: "complete";
  result: string;
  attachments: string[];
  claude_session_id?: string;
}

export interface ErrorEvent {
  type: "error";
  message: string;
  error_code?: string;
}

export interface ContextUsageEvent {
  type: "context_usage";
  used_tokens: number;
  max_tokens: number;
  percent: number;
}

export interface CompactEvent {
  type: "compact";
  trigger: string;
  message: string;
}

// === 세분화 SSE Events (대시보드 전용) ===

export interface TextStartEvent {
  type: "text_start";
  card_id: string;
}

export interface TextDeltaEvent {
  type: "text_delta";
  card_id: string;
  text: string;
}

export interface TextEndEvent {
  type: "text_end";
  card_id: string;
}

export interface ToolStartEvent {
  type: "tool_start";
  card_id?: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  /** SDK ToolUseBlock ID (tool_result 매칭용) */
  tool_use_id?: string;
}

export interface ToolResultEvent {
  type: "tool_result";
  card_id?: string;
  tool_name: string;
  result: string;
  is_error: boolean;
  /** SDK ToolUseBlock ID (tool_start 매칭용) */
  tool_use_id?: string;
}

export interface ResultEvent {
  type: "result";
  success: boolean;
  output: string;
  error?: string;
}

export interface ReconnectEvent {
  type: "reconnect";
  last_event_id?: number;
}

/** Soul에서 수신하는 모든 SSE 이벤트 유니온 */
export type SoulSSEEvent =
  | ProgressEvent
  | MemoryEvent
  | SessionEvent
  | InterventionSentEvent
  | UserMessageEvent
  | DebugEvent
  | CompleteEvent
  | ErrorEvent
  | ContextUsageEvent
  | CompactEvent
  | TextStartEvent
  | TextDeltaEvent
  | TextEndEvent
  | ToolStartEvent
  | ToolResultEvent
  | ResultEvent
  | ReconnectEvent;

// === JSONL Record ===

/** EventStore JSONL 레코드 형식 (파일의 한 줄) */
export interface EventRecord {
  id: number;
  event: Record<string, unknown>;
}

// === Session ===

/** 세션 상태 */
export type SessionStatus = "running" | "completed" | "error" | "unknown";

/** 세션 요약 정보 (목록 조회용) */
export interface SessionSummary {
  clientId: string;
  requestId: string;
  status: SessionStatus;
  eventCount: number;
  lastEventType?: string;
  createdAt?: string;
  completedAt?: string;
}

/** 세션 상세 정보 */
export interface SessionDetail extends SessionSummary {
  claudeSessionId?: string;
  prompt?: string;
  result?: string;
  error?: string;
  events: EventRecord[];
}

// === Dashboard Card ===

/**
 * 대시보드 카드 - 텍스트 블록 또는 도구 호출 단위의 UI 추상화.
 *
 * Soul의 card_id(UUID4 8자)로 식별됩니다.
 * text_start → text_delta → text_end 시퀀스를 하나의 카드로 집계합니다.
 */
export interface DashboardCard {
  cardId: string;
  type: "text" | "tool";
  /** 텍스트 카드: 누적된 텍스트 내용 */
  content: string;
  /** 도구 카드: 도구 이름 */
  toolName?: string;
  /** 도구 카드: 입력 파라미터 */
  toolInput?: Record<string, unknown>;
  /** 도구 카드: 실행 결과 */
  toolResult?: string;
  /** 도구 카드: 오류 여부 */
  isError?: boolean;
  /** 카드가 완료되었는지 (text_end 수신 또는 tool_result 수신) */
  completed: boolean;
  /** 도구 카드: SDK ToolUseBlock ID (tool_result 매칭용) */
  toolUseId?: string;
  /** 도구 카드: 부모 thinking 카드 ID (레이아웃 그룹핑용) */
  parentCardId?: string;
}

// === API Request/Response ===

/** POST /api/sessions 요청 (대시보드에서 세션 생성) */
export interface CreateSessionRequest {
  prompt: string;
  clientId?: string;
  resumeSessionId?: string;
}

/** POST /api/sessions/:id/message 요청 */
export interface SendMessageRequest {
  text: string;
  user: string;
  attachmentPaths?: string[];
}

/** 공통 API 에러 응답 */
export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// === Dashboard SSE Event (서버 → 클라이언트) ===

/**
 * 대시보드 서버가 클라이언트에 보내는 SSE 이벤트 래퍼.
 *
 * Soul의 이벤트를 그대로 중계하되, 세션 식별자를 추가합니다.
 */
export interface DashboardSSEEvent {
  /** EventStore의 단조증가 ID */
  eventId: number;
  /** 세션 식별자 */
  sessionKey: string;
  /** 원본 Soul 이벤트 */
  event: SoulSSEEvent;
}
