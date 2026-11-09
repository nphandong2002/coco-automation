import { ReactNode, useEffect, useState } from "react";
import type { ChannelStatus } from "../api/types";
import { onToast } from "../lib/hooks";

const STATUS: Record<ChannelStatus, { label: string; cls: string }> = {
  active: { label: "Active", cls: "bg-emerald-100 text-emerald-800" },
  paused: { label: "Paused", cls: "bg-amber-100 text-amber-800" },
  error: { label: "Error", cls: "bg-red-100 text-red-800" },
  disconnected: { label: "Disconnected", cls: "bg-slate-200 text-slate-700" },
};

export function StatusBadge({ status }: { status: ChannelStatus }) {
  const s = STATUS[status];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>;
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "brand" | "blue" | "green" }) {
  const map = {
    slate: "bg-slate-100 text-slate-700",
    brand: "bg-brand-100 text-brand-700",
    blue: "bg-sky-100 text-sky-800",
    green: "bg-emerald-100 text-emerald-800",
  };
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${map[tone]}`}>{children}</span>;
}

export function Loading() {
  return <div className="muted p-6">Đang tải…</div>;
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="card border-red-200 bg-red-50 p-4 text-sm text-red-800">
      {error} {onRetry && <button className="ml-2 underline" onClick={onRetry}>Thử lại</button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-2 p-10 text-center">
      <div className="text-3xl">🍃</div>
      <div className="font-semibold">{title}</div>
      {children && <div className="muted max-w-md">{children}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 pt-16" onClick={onClose}>
      <div className={`card w-full ${wide ? "max-w-3xl" : "max-w-lg"} p-5`} onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button className="text-ink-500 hover:text-ink-900" onClick={onClose} aria-label="Đóng">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-500">{hint}</span>}
    </label>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="card p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-ink-500">{label}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-500">{sub}</div>}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: string }[]; value: T; onChange: (k: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-brand-100">
      {tabs.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${value === t.key ? "border-brand-600 text-brand-700" : "border-transparent text-ink-500 hover:text-ink-900"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function ImageUpload({ label, url, onFile, busy, aspect = "aspect-square" }: { label: string; url: string | null; onFile: (f: File) => void; busy?: boolean; aspect?: string }) {
  return (
    <div>
      <span className="label">{label}</span>
      <label className={`relative flex ${aspect} cursor-pointer items-center justify-center overflow-hidden rounded-lg border-2 border-dashed border-brand-100 bg-brand-50 hover:border-brand-400`}>
        {url ? <img src={url} alt={label} className="h-full w-full object-cover" /> : <span className="text-xs text-ink-500">Chọn ảnh PNG/JPG/WEBP</span>}
        {busy && <span className="absolute inset-0 flex items-center justify-center bg-white/70 text-xs">Đang tải lên…</span>}
        <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
      </label>
    </div>
  );
}

export function ColorChips({ colors }: { colors: string[] }) {
  if (!colors.length) return <span className="muted">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {colors.map((c) => (
        <span key={c} className="flex items-center gap-1 rounded-full border border-brand-100 px-2 py-0.5 text-xs">
          <span className="h-3 w-3 rounded-full border border-black/10" style={{ background: c }} />{c}
        </span>
      ))}
    </div>
  );
}

export function Toaster() {
  const [items, setItems] = useState<{ id: number; msg: string; kind: string }[]>([]);
  useEffect(() => onToast((msg, kind) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, msg, kind }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), kind === "error" ? 6000 : 3000);
  }), []);
  return (
    <div className="fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {items.map((i) => (
        <div key={i.id} className={`rounded-lg px-4 py-3 text-sm shadow-lg ${i.kind === "error" ? "bg-red-600 text-white" : "bg-ink-900 text-white"}`}>{i.msg}</div>
      ))}
    </div>
  );
}
