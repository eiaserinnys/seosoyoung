/**
 * Playwright E2E 테스트 설정
 *
 * Soul Dashboard의 브라우저 기반 인터랙션 테스트를 위한 설정입니다.
 * 테스트 서버(Express + Vite)를 자동 시작하고 Chromium에서 테스트를 실행합니다.
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

  use: {
    baseURL: "http://localhost:3109",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // 테스트 전에 대시보드 서버 시작 (CI에서 사용)
  // webServer: {
  //   command: "npm run dev",
  //   url: "http://localhost:3109/api/health",
  //   reuseExistingServer: !process.env.CI,
  //   timeout: 10_000,
  // },
});
