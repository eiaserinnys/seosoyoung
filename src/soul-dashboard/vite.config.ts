import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  resolve: {
    alias: {
      "@shared": resolve(__dirname, "shared"),
    },
  },
  build: {
    // Phase 6에서 클라이언트 빌드 설정 추가 예정
    outDir: "dist/client",
  },
  server: {
    // 개발 시 대시보드 서버로 API 프록시
    proxy: {
      "/api": {
        target: "http://localhost:3106",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "node",
    include: ["../../tests/soul-dashboard/**/*.test.ts"],
    alias: {
      "@shared": resolve(__dirname, "shared"),
    },
  },
});
