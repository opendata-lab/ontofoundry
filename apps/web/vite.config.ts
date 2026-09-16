import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    // 端口可覆盖：写死 8000 会让本地开发必须独占该端口，而同机上跑着别的服务
    // 时就只能改代码或杀掉对方。
    proxy: Object.fromEntries(
      ["/api", "/healthz", "/docs", "/openapi.json"].map((path) => [
        path,
        process.env.ONTOFOUNDRY_API_ORIGIN ?? "http://127.0.0.1:8000",
      ]),
    ),
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
