import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// base "./" keeps asset URLs relative, so the same build works on GitHub Pages
// (https://<user>.github.io/<repo>/) and behind the local nginx container.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { port: 5173 },
  build: { sourcemap: false, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.ts"] },
});
