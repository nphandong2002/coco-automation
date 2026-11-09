import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Asset, AssetKind, Capabilities, ContentProject, ContentType, Job, JobStatus, LicenseType, ProductionStatus, Video } from "../api/types";
import { fmtDate, useAction, useApi } from "../lib/hooks";
import { Badge, Empty, ErrorBox, Loading, Modal } from "./ui";

export const CONTENT_TYPES: Record<ContentType, string> = {
  study_with_me: "Study With Me", pomodoro: "Pomodoro", cozy_ambience: "Cozy Ambience",
  rain_sounds: "Rain Sounds", fireplace_sounds: "Fireplace Sounds", sleep_ambience: "Sleep Ambience",
  reading_room: "Reading Room", cafe_ambience: "Café Ambience", nature_ambience: "Nature Ambience",
};

export const LICENSES: Record<LicenseType, string> = {
  owned: "Tự sở hữu", cc0: "CC0 (public domain)", cc_by: "CC BY (cần ghi công)",
  royalty_free: "Royalty-free", licensed: "Đã mua giấy phép",
};

export const KINDS: Record<AssetKind, string> = { image: "Hình ảnh", audio: "Âm thanh", video: "Video", font: "Font" };

const PROD: Record<ProductionStatus, { label: string; cls: string }> = {
  draft: { label: "Nháp", cls: "bg-slate-100 text-slate-700" },
  ready: { label: "Sẵn sàng", cls: "bg-sky-100 text-sky-800" },
  queued: { label: "Chờ render", cls: "bg-amber-100 text-amber-800" },
  rendering: { label: "Đang render", cls: "bg-violet-100 text-violet-800" },
  rendered: { label: "Đã render", cls: "bg-emerald-100 text-emerald-800" },
  failed: { label: "Lỗi", cls: "bg-red-100 text-red-800" },
  published: { label: "Đã đăng", cls: "bg-brand-100 text-brand-700" },
};

const JOB: Record<JobStatus, { label: string; cls: string }> = {
  queued: { label: "Đang chờ", cls: "bg-amber-100 text-amber-800" },
  running: { label: "Đang chạy", cls: "bg-violet-100 text-violet-800" },
  succeeded: { label: "Thành công", cls: "bg-emerald-100 text-emerald-800" },
  failed: { label: "Thất bại", cls: "bg-red-100 text-red-800" },
  cancelled: { label: "Đã hủy", cls: "bg-slate-200 text-slate-700" },
};

export function ProdBadge({ status }: { status: ProductionStatus }) {
  const s = PROD[status];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>;
}

export function JobBadge({ status }: { status: JobStatus }) {
  const s = JOB[status];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>;
}

export function ProgressBar({ value, active }: { value: number; active?: boolean }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-brand-50">
      <div className={`h-full rounded-full ${active ? "bg-violet-500" : "bg-brand-500"} transition-all`} style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  );
}

export function fmtDuration(sec: number | null | undefined) {
  if (sec == null) return "—";
  const s = Math.round(sec);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

export function fmtMinutes(min: number) {
  return min % 60 === 0 ? `${min / 60} giờ` : `${min} phút`;
}

export function fmtBytes(n: number) {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

/** Re-run `fn` every `ms` while `active` is true (render queue auto-refresh). */
export function usePolling(fn: () => void, active: boolean, ms = 3000) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => ref.current(), ms);
    return () => clearInterval(t);
  }, [active, ms]);
}

let capsPromise: Promise<Capabilities> | null = null;
/** Render capabilities (generators, effects, durations…) — fetched once per page load. */
export function useCapabilities() {
  return useApi(() => {
    capsPromise ??= api.capabilities().catch((e) => { capsPromise = null; throw e; });
    return capsPromise;
  });
}

export function AssetThumb({ a, className = "" }: { a: Asset; className?: string }) {
  if (a.kind === "image") return <img src={a.url} alt={a.name} className={`h-full w-full object-cover ${className}`} loading="lazy" />;
  if (a.kind === "video") return <video src={a.url} className={`h-full w-full object-cover ${className}`} muted preload="metadata" />;
  return <div className={`flex h-full w-full items-center justify-center bg-brand-50 text-3xl ${className}`}>{a.kind === "audio" ? "♫" : "Aa"}</div>;
}

/** Choose one usable asset (channel's own + shared library) of a given kind. */
export function AssetPicker({ channelId, kind, onPick, onClose }: { channelId: number; kind: AssetKind; onPick: (a: Asset) => void; onClose: () => void }) {
  const { data, error, loading, reload } = useApi(() => api.usableAssets(channelId, kind), [channelId, kind]);
  const caps = useCapabilities();
  const { busy, run } = useAction();
  const [style, setStyle] = useState("rainy_window");
  return (
    <Modal title={`Chọn ${KINDS[kind].toLowerCase()}`} wide onClose={onClose}>
      {kind === "image" && (
        <div className="mb-4 flex flex-wrap items-end gap-2 rounded-lg bg-brand-50 p-3">
          <label className="text-sm">Tạo ảnh nền tự động
            <select className="input mt-1" value={style} onChange={(e) => setStyle(e.target.value)}>
              {Object.entries(caps.data?.background_styles ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <button className="btn-ghost" disabled={busy} onClick={async () => {
            const a = await run(() => api.generateBackground({ channel_id: channelId, style }), "Đã tạo ảnh nền");
            if (a) { void reload(); onPick(a); }
          }}>✦ Tạo theo bảng màu kênh</button>
          <span className="text-xs text-ink-500">Ảnh do hệ thống tạo — bạn sở hữu. Tải ảnh/âm thanh riêng ở mục <Link to="/assets" className="underline">Assets</Link>.</span>
        </div>
      )}
      {loading && !data ? <Loading /> : error ? <ErrorBox error={error} onRetry={reload} /> : !data?.length ? (
        <Empty title={`Chưa có ${KINDS[kind].toLowerCase()} nào`}>Tải lên ở mục Assets (bắt buộc khai báo giấy phép).</Empty>
      ) : (
        <div className="grid max-h-[60vh] grid-cols-2 gap-3 overflow-y-auto sm:grid-cols-3">
          {data.map((a) => (
            <button key={a.id} className="card overflow-hidden text-left hover:ring-2 hover:ring-brand-400" onClick={() => onPick(a)}>
              <div className="aspect-video">{<AssetThumb a={a} />}</div>
              <div className="p-2 text-xs">
                <div className="truncate font-medium">{a.name}</div>
                <div className="text-ink-500">{a.channel_id ? "Kênh" : "Dùng chung"} · {LICENSES[a.license_type]}{a.duration_sec ? ` · ${fmtDuration(a.duration_sec)}` : ""}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}

export function ProjectTable({ items, showChannel = true }: { items: ContentProject[]; showChannel?: boolean }) {
  if (!items.length) return <Empty title="Chưa có dự án nội dung">Tạo dự án mới hoặc sinh ý tưởng từ chủ đề của kênh.</Empty>;
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-brand-50 text-left text-xs uppercase tracking-wide text-ink-500">
          <tr><th className="px-4 py-3">Dự án</th>{showChannel && <th className="px-4 py-3">Kênh</th>}<th className="px-4 py-3">Loại</th>
            <th className="px-4 py-3">Thời lượng</th><th className="px-4 py-3">Trạng thái</th><th className="px-4 py-3">Render gần nhất</th></tr>
        </thead>
        <tbody className="divide-y divide-brand-50">
          {items.map((p) => (
            <tr key={p.id} className="hover:bg-brand-50/50">
              <td className="px-4 py-3">
                <Link to={`/channels/${p.channel_id}/content/${p.id}`} className="flex items-center gap-3">
                  <div className="h-10 w-16 shrink-0 overflow-hidden rounded bg-brand-50">
                    {(p.thumbnail_url || p.background_url) && <img src={p.thumbnail_url ?? p.background_url ?? ""} alt="" className="h-full w-full object-cover" />}
                  </div>
                  <div><div className="font-medium text-ink-900">{p.title}</div>
                    <div className="text-xs text-ink-500">{[p.character_name && `${p.character_name} v${p.character_version_no}`, p.setting].filter(Boolean).join(" · ") || "—"}</div></div>
                </Link>
              </td>
              {showChannel && <td className="px-4 py-3"><Link className="hover:underline" to={`/channels/${p.channel_id}`}>{p.channel_name}</Link></td>}
              <td className="px-4 py-3">{CONTENT_TYPES[p.content_type]}</td>
              <td className="px-4 py-3">{fmtMinutes(p.duration_minutes)}</td>
              <td className="px-4 py-3"><ProdBadge status={p.status} /></td>
              <td className="px-4 py-3">
                {p.latest_job ? (
                  <div className="w-40 space-y-1"><div className="flex items-center gap-2"><JobBadge status={p.latest_job.status} />
                    <span className="text-xs text-ink-500">{p.latest_job.job_type === "preview" ? "xem thử" : "video"}</span></div>
                    {p.latest_job.status === "running" && <ProgressBar value={p.latest_job.progress} active />}</div>
                ) : <span className="text-xs text-ink-300">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function VideoList({ items, onChanged }: { items: Video[]; onChanged?: () => void }) {
  const [open, setOpen] = useState<Video | null>(null);
  const { busy, run } = useAction();
  if (!items.length) return <Empty title="Chưa có video nào">Video xuất hiện tại đây sau khi render hoàn tất và qua kiểm tra chất lượng.</Empty>;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((v) => (
          <div key={v.id} className="card overflow-hidden">
            <button className="relative block aspect-video w-full bg-ink-900" onClick={() => setOpen(v)}>
              {v.thumbnail_url && <img src={v.thumbnail_url} alt="" className="h-full w-full object-cover opacity-90" />}
              <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 text-xs text-white">{fmtDuration(v.duration_sec)}</span>
              <span className="absolute inset-0 flex items-center justify-center text-4xl text-white/90">▶</span>
            </button>
            <div className="space-y-1 p-3 text-sm">
              <div className="line-clamp-2 font-medium">{v.title}</div>
              <div className="text-xs text-ink-500">{v.channel_name} · {v.width}x{v.height} · {v.fps} fps · {fmtBytes(v.size_bytes)}</div>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                {v.qc_passed ? <Badge tone="green">QC đạt</Badge> : <Badge>QC lỗi</Badge>}
                {v.youtube_video_id ? <Badge tone="blue">Đã đăng</Badge> : <Badge>Chưa đăng (Phase 3)</Badge>}
                <a className="ml-auto text-xs text-brand-700 underline" href={v.url} download>Tải về</a>
              </div>
            </div>
          </div>
        ))}
      </div>
      {open && (
        <Modal title={open.title} wide onClose={() => setOpen(null)}>
          <video src={open.url} controls className="w-full rounded-lg bg-black" poster={open.thumbnail_url ?? undefined} />
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="space-y-1 text-sm">
              <div>Thời lượng: <b>{fmtDuration(open.duration_sec)}</b> · {open.width}x{open.height} · {open.fps} fps</div>
              <div>Dung lượng: {fmtBytes(open.size_bytes)}{open.qc_report.render_seconds ? ` · render ${fmtDuration(open.qc_report.render_seconds)}` : ""}</div>
              <div className="break-all text-xs text-ink-500">SHA-256: {open.sha256}</div>
              <div className="text-xs text-ink-500">Tạo lúc {fmtDate(open.created_at)}</div>
            </div>
            <div className="space-y-1 text-xs">
              <div className="font-semibold uppercase text-ink-500">Kiểm tra chất lượng</div>
              {(open.qc_report.checks ?? []).map((c) => (
                <div key={c.name} className="flex gap-2"><span className={c.ok ? "text-emerald-600" : c.critical ? "text-red-600" : "text-amber-600"}>{c.ok ? "✔" : "✖"}</span>
                  <span className="font-mono">{c.name}</span><span className="text-ink-500">{c.detail}</span></div>
              ))}
            </div>
          </div>
          {!open.youtube_video_id && (
            <div className="mt-4 flex justify-end">
              <button className="btn-ghost text-red-700" disabled={busy} onClick={async () => {
                if (!confirm("Xóa vĩnh viễn file video này khỏi ổ đĩa?")) return;
                const ok = await run(() => api.deleteVideo(open.id).then(() => true), "Đã xóa video");
                if (ok) { setOpen(null); onChanged?.(); }
              }}>Xóa video</button>
            </div>
          )}
        </Modal>
      )}
    </>
  );
}

export function JobRow({ j, onChanged, compact }: { j: Job; onChanged: () => void; compact?: boolean }) {
  const { busy, run } = useAction();
  const [log, setLog] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const active = j.status === "running" || j.status === "queued";
  return (
    <div className="space-y-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono text-xs text-ink-500">#{j.id}</span>
        <JobBadge status={j.status} />
        <Badge tone={j.job_type === "preview" ? "blue" : "brand"}>{j.job_type === "preview" ? `Xem thử ${Math.round(j.duration_sec ?? 0)}s` : `Video ${fmtDuration(j.duration_sec)}`}</Badge>
        {!compact && <Link className="font-medium hover:underline" to={`/channels/${j.channel_id}/content/${j.content_project_id}`}>{j.project_title ?? `Dự án #${j.content_project_id}`}</Link>}
        {!compact && <span className="text-xs text-ink-500">· {j.channel_name}</span>}
        <span className="ml-auto text-xs text-ink-500">{fmtDate(j.created_at)}</span>
      </div>
      {j.status === "running" && (
        <div className="flex items-center gap-3">
          <ProgressBar value={j.progress} active />
          <span className="whitespace-nowrap text-xs text-ink-500">{Math.round(j.progress * 100)}% · {j.step}{j.eta_seconds != null ? ` · còn ~${fmtDuration(j.eta_seconds)}` : ""}</span>
        </div>
      )}
      {j.status === "queued" && <div className="text-xs text-ink-500">{j.step}{j.attempts ? ` · lần thử ${j.attempts}/${j.max_attempts}` : ""}</div>}
      {j.error && <div className="rounded bg-red-50 px-3 py-2 text-xs text-red-800">{j.error.slice(0, 600)}</div>}
      <div className="flex flex-wrap gap-2">
        {active && <button className="btn-ghost text-xs" disabled={busy || j.cancel_requested} onClick={() => run(() => api.cancelJob(j.id), "Đã gửi yêu cầu hủy").then(onChanged)}>{j.cancel_requested ? "Đang hủy…" : "Hủy"}</button>}
        {(j.status === "failed" || j.status === "cancelled") && <button className="btn-ghost text-xs" disabled={busy} onClick={() => run(() => api.retryJob(j.id), "Đã đưa lại vào hàng đợi").then(onChanged)}>↻ Chạy lại</button>}
        {j.output_url && j.job_type === "preview" && <button className="btn-ghost text-xs" onClick={() => setPreview(true)}>▶ Xem bản thử</button>}
        {j.has_log && <button className="btn-ghost text-xs" onClick={async () => setLog(await api.jobLog(j.id).catch((e) => String(e)))}>Log FFmpeg</button>}
      </div>
      {log !== null && (
        <Modal title={`Log tác vụ #${j.id}`} wide onClose={() => setLog(null)}>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded bg-ink-900 p-3 text-xs text-white">{log}</pre>
        </Modal>
      )}
      {preview && j.output_url && (
        <Modal title={`Bản xem thử #${j.id}`} wide onClose={() => setPreview(false)}>
          <video src={j.output_url} controls autoPlay className="w-full rounded-lg bg-black" />
        </Modal>
      )}
    </div>
  );
}
