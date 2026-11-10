import { useEffect, useRef } from "react";
import { api } from "@/lib/api";

const HEARTBEAT_INTERVAL_MS = 30_000; // 30s
const INACTIVE_TIMEOUT_MS = 120_000;  // 2 min

export function useHeartbeat(enabled: boolean = true) {
  const lastActiveRef = useRef<number>(Date.now());

  useEffect(() => {
    if (!enabled) return;

    const onUserAction = () => {
      lastActiveRef.current = Date.now();
    };

    window.addEventListener("mousemove", onUserAction, { passive: true });
    window.addEventListener("keydown", onUserAction, { passive: true });
    window.addEventListener("scroll", onUserAction, { passive: true });
    window.addEventListener("click", onUserAction, { passive: true });

    const intervalId = window.setInterval(() => {
      const isVisible = document.visibilityState === "visible";
      const isActive = Date.now() - lastActiveRef.current < INACTIVE_TIMEOUT_MS;

      if (isVisible && isActive) {
        api.post("/activity/heartbeat", { visible: true, active: true }).catch(() => {});
      }
    }, HEARTBEAT_INTERVAL_MS);

    return () => {
      window.removeEventListener("mousemove", onUserAction);
      window.removeEventListener("keydown", onUserAction);
      window.removeEventListener("scroll", onUserAction);
      window.removeEventListener("click", onUserAction);
      window.clearInterval(intervalId);
    };
  }, [enabled]);
}
