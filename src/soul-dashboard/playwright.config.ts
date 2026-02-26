/**
 * Playwright E2E 테스트 설정
 *
 * Soul Dashboard의 브라우저 기반 인터랙션 테스트를 위한 설정입니다.
 * - API 테스트: 자체 mock 서버 사용 (dashboard.e2e.ts)
 * - UI 테스트: 빌드된 클라이언트 + mock API 서버 (dashboard-ui.e2e.ts)
 *
 * UI 테스트 실행 전 `npx vite build`로 클라이언트를 빌드해야 합니다.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  timeout: 30_000,

  /* 스크린샷 / trace 출력 디렉토리 */
  outputDir: "./e2e/test-results",

  use: {
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // webServer 설정 없음: UI 테스트는 fixture에서 mock 서버를 직접 시작하여
  // 빌드된 클라이언트(dist/client/)를 서빙합니다. 포트 충돌 방지를 위해
  // 랜덤 포트를 사용합니다.
});
