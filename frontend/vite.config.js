import vue from "@vitejs/plugin-vue";
import { defineConfig, loadEnv } from "vite";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || "http://localhost:8000";
  const wsProxyTarget = proxyTarget.replace(/^http/, "ws");

  return {
  plugins: [vue()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },

  // ── CSS 预处理器配置 ──────────────────────────────
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `@use "@/assets/styles/variables.scss" as *;`,
      },
    },
  },

  // ── 开发服务器配置 ────────────────────────────────
  server: {
    port: 5173,
    open: true,
    proxy: {
      // 更具体的摄像头路径必须位于通用 /api 之前，确保本地开发可升级 WebSocket。
      "/api/detection/camera": {
        target: wsProxyTarget,
        ws: true,
        changeOrigin: true,
      },
      // REST API 代理
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },

  // ── Vitest 测试配置 ───────────────────────────────
  test: {
    // 使用 happy-dom 模拟浏览器环境
    environment: "happy-dom",
    // 全局 setup 文件
    setupFiles: ["./tests/setup.js"],
    // 测试文件匹配模式
    include: ["tests/**/*.{test,spec}.{js,ts}"],
    // 覆盖率（可选）
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
    },
  },
  };
});
