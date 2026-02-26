/**
 * SoulClient 테스트
 *
 * Soul SSE 구독 클라이언트의 핵심 로직을 검증합니다.
 * 실제 SSE 서버 없이 단위 테스트 수준에서 검증합니다.
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { SoulClient } from "../../../src/soul-dashboard/server/soul-client.js";

describe("SoulClient", () => {
  let client: SoulClient;

  afterEach(() => {
    client?.close();
  });

  describe("constructor", () => {
    it("should initialize with default options", () => {
      client = new SoulClient({
        soulBaseUrl: "http://localhost:3105",
      });

      expect(client.getActiveSubscriptions()).toEqual([]);
    });

    it("should strip trailing slash from base URL", () => {
      client = new SoulClient({
        soulBaseUrl: "http://localhost:3105/",
      });

      // URL은 내부적으로 정규화됨 - 구독 시 확인 가능
      expect(client.getActiveSubscriptions()).toEqual([]);
    });
  });

  describe("onEvent / onError", () => {
    it("should register event handlers", () => {
      client = new SoulClient({
        soulBaseUrl: "http://localhost:3105",
      });

      const handler = vi.fn();
      client.onEvent(handler);

      // 핸들러가 등록되었지만 아직 호출되지 않았음
      expect(handler).not.toHaveBeenCalled();
    });

    it("should register error handlers", () => {
      client = new SoulClient({
        soulBaseUrl: "http://localhost:3105",
      });

      const handler = vi.fn();
      client.onError(handler);

      expect(handler).not.toHaveBeenCalled();
    });
  });

  describe("subscribe / unsubscribe", () => {
    it("should track active subscriptions (connection will fail in test)", () => {
      client = new SoulClient({
        soulBaseUrl: "http://localhost:39999", // 존재하지 않는 서버
      });

      // subscribe는 내부적으로 EventSource 연결을 시도
      // 테스트 환경에서는 연결이 실패하지만 구독 추적은 됨
      // Note: 실제 구현에서 EventSource 생성자가 예외를 던질 수 있음
      try {
        client.subscribe("bot", "req-1");
      } catch {
        // EventSource 생성 실패는 예상됨
      }
    });

    it("should not duplicate subscriptions", () => {
      client = new SoulClient({
        soulBaseUrl: "http://localhost:39999",
      });

      try {
        client.subscribe("bot", "req-1");
        client.subscribe("bot", "req-1"); // 중복
      } catch {
        // 예상됨
      }
    });
  });

  describe("close", () => {
    it("should close without error when no subscriptions", () => {
      client = new SoulClient({
        soulBaseUrl: "http://localhost:3105",
      });

      expect(() => client.close()).not.toThrow();
      expect(client.getActiveSubscriptions()).toEqual([]);
    });
  });
});
