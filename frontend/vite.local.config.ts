// Local preview of the redesign against the local backend (not used by builds or deploys).
// The dev server proxies /api to the backend on 127.0.0.1:8000, so the app and its API share one origin.
import { mergeConfig } from "vite";
import base from "./vite.config";

export default mergeConfig(base, {
  server: { host: "127.0.0.1", port: 5180, strictPort: true, proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } } },
});
