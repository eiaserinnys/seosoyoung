/**
 * 세션 ID 파싱 유틸리티
 *
 * URL 파라미터 또는 쿼리 파라미터에서 clientId/requestId를 추출합니다.
 */

/**
 * 세션 ID를 clientId와 requestId로 파싱합니다.
 *
 * 지원 형식:
 * - URL param: "clientId:requestId" (URL 인코딩된 콜론)
 * - Query params: ?clientId=...&requestId=...
 */
export function parseSessionId(
  idParam: string,
  query: Record<string, string>,
): { clientId?: string; requestId?: string } {
  // Query param 우선
  if (query.clientId && query.requestId) {
    return { clientId: query.clientId, requestId: query.requestId };
  }

  // URL param에서 파싱
  const decoded = decodeURIComponent(idParam);
  const colonIdx = decoded.indexOf(":");
  if (colonIdx > 0) {
    return {
      clientId: decoded.substring(0, colonIdx),
      requestId: decoded.substring(colonIdx + 1),
    };
  }

  return {};
}
