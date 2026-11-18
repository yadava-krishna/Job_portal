import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { CSPProvider } from "@base-ui/react/csp-provider";
import "./index.css";
import App from "./App";

// After a new version is published, a tab still running the old one may ask for page code that no longer exists.
// Reload once to pick up the new version instead of showing a blank page (guarded so it can never loop).
window.addEventListener("vite:preloadError", (event) => {
  try {
    const last = Number(sessionStorage.getItem("jobpilot:reloaded-at") || 0);
    if (Date.now() - last < 60_000) return;
    sessionStorage.setItem("jobpilot:reloaded-at", String(Date.now()));
  } catch { /* storage unavailable: still reload */ }
  event.preventDefault();
  window.location.reload();
});

// Apply the saved theme before the first paint, on every screen (sign-in, loading, onboarding too), not only once the
// theme toggle mounts. Done here rather than in an inline <script> because the CSP forbids inline scripts.
try {
  const stored = localStorage.getItem("jobpilot.theme");
  const dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", dark);
} catch { /* storage unavailable: light theme */ }

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* No inline <style> elements from Base UI (the CSP blocks them); their CSS is in index.css. */}
    <CSPProvider disableStyleElements>
      <App />
    </CSPProvider>
  </StrictMode>,
);
