import { useCallback, useEffect, useRef, useState } from "react";

/** Load data from the API with loading/error state and a reload() function. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void reload(); }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, setData, error, loading, reload };
}

/** Wrap a mutation: tracks busy state and reports errors through toast(). */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>, okMsg?: string): Promise<T | undefined> => {
    setBusy(true);
    try {
      const r = await fn();
      if (okMsg) toast(okMsg, "ok");
      return r;
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, run };
}

type ToastKind = "ok" | "error";
type Listener = (msg: string, kind: ToastKind) => void;
const listeners = new Set<Listener>();
export function toast(msg: string, kind: ToastKind = "ok") { listeners.forEach((l) => l(msg, kind)); }
export function onToast(l: Listener) { listeners.add(l); return () => { listeners.delete(l); }; }

export const splitList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
export const joinList = (a?: string[]) => (a ?? []).join(", ");
export const fmtDate = (s: string) => new Date(s).toLocaleString("vi-VN");
