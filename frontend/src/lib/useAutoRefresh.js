import { useEffect, useRef } from "react";

// Smart auto-refresh: re-runs fn on an interval (only when tab visible) and on window focus.
export function useAutoRefresh(fn, interval = 8000, enabled = true) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    if (!enabled) return;
    const run = () => { if (document.visibilityState === "visible") saved.current?.(); };
    const id = setInterval(run, interval);
    const onFocus = () => saved.current?.();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", run);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", run);
    };
  }, [interval, enabled]);
}

export function relTime(iso) {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
