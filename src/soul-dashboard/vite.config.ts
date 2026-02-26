import { defineConfig } from "vite";
import { resolve } from "path";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  root: ".",
  resolve: {
    alias: {
      "@shared": resolve(__dirname, "shared"),
    },
  },
  build: {
    outDir: "dist/client",
    emptyOutDir: true,
  },
  server: {
    // 개발 시 대시보드 서버로 API 프록시
    proxy: {
      "/api": {
        target: "http://localhost:3109",
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
    server: {
      deps: {
        external: [
          "express",
          "cors",
          "eventsource",
        ],
        moduleDirectories: [
          resolve(__dirname, "node_modules"),
          "node_modules",
        ],
      },
    },
  },
});
