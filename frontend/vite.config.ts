import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

const CSP_META = /\s*<meta http-equiv="Content-Security-Policy"[^>]*>/;

/** `vite dev` injects an inline script (React hot reload) that the CSP in index.html forbids; drop the CSP there only. */
function noCspInDev(): Plugin {
  return { name: "jobpilot:no-csp-in-dev", apply: "serve", transformIndexHtml: (html) => html.replace(CSP_META, "") };
}

/** The built index.html must carry the CSP: GitHub Pages can't send it as a header. */
function requireCspInBuild(): Plugin {
  return {
    name: "jobpilot:require-csp", apply: "build",
    transformIndexHtml(html) {
      if (!CSP_META.test(html)) throw new Error("index.html lost its Content-Security-Policy <meta> tag");
      return html;
    },
  };
}

/**
 * sonner writes its CSS into an inline <style> element when it loads, which the CSP (style-src 'self') blocks.
 * The same CSS is bundled from sonner/dist/styles.css (imported in components/ui/sonner.tsx), so the build removes
 * the runtime call. If sonner changes how it does this, the build stops here rather than shipping unstyled toasts.
 */
function sonnerWithoutInlineStyle(): Plugin {
  const call = /\n__insertCSS\("(?:[^"\\]|\\.)*"\);/;
  return {
    name: "jobpilot:sonner-without-inline-style", apply: "build", enforce: "pre",
    transform(code, id) {
      if (!/[\\/]node_modules[\\/]sonner[\\/]dist[\\/]index\.m?js$/.test(id)) return null;
      if (!call.test(code)) {
        throw new Error("sonner no longer injects its CSS with __insertCSS(\"…\"): update sonnerWithoutInlineStyle in vite.config.ts");
      }
      return { code: code.replace(call, "\n"), map: null };
    },
  };
}

// base "./" keeps asset URLs relative, so the same build works on GitHub Pages
// (https://<user>.github.io/<repo>/) and behind the local nginx container.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss(), noCspInDev(), requireCspInBuild(), sonnerWithoutInlineStyle()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { port: 5173 },
  build: { sourcemap: false, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.ts"] },
});
