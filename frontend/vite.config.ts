/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { seoFiles } from "./seo-plugin";

export default defineConfig(({ mode }) => {
  // .env files plus real environment variables (e.g. build arguments on the hosting platform).
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [react(), tailwindcss(), seoFiles(env.VITE_SITE_URL)],
    build: {
      // No source maps in the public bundle; the source code is in the repository anyway,
      // and this keeps the deployed files small.
      sourcemap: false,
    },
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
      port: 5173,
      // During development, API calls go to the FastAPI server on port 8000.
      proxy: {
        "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
