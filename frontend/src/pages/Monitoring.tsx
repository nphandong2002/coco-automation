import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { MonAlert, MonWorker, Monitoring as Mon, QueueStat } from "../api/types";
import { PALETTE } from "../components/analytics";
import { usePolling } from "../components/production";
import { Badge, ErrorBox, Loading, Stat } from "../components/ui";
import { fmtDate, toast, useAction, useApi } from "../lib/hooks";

const WORKER_LABEL: Record<string, string> = { render: "Render (FFmpeg)", publish: "Upload YouTube", analytics: "Analytics sync", monitor: "Monitor & watchdog" };
const STATE_LABEL: Record<string, string> = { idle: "Rảnh", rendering: "Đang render", uploading: "Đang upload", syncing: "Đang đồng bộ", waiting_lock: "Chờ khóa", stopped: "Đã dừng", never_started: "Chưa từng chạy" };
const dur = (s: number | null | undefined) => {
  if (s === null || s === undefined) return "—";
  if (s < 90) return `${s}s`;
  if (s < 5400) return `${Math.round(s / 60)} phút`;
  return `${(s / 3600).toFixed(1)} giờ`;
};
const tone = (pct: number, warn: number, crit: number) => (pct >= crit ? "text-red-700" : pct >= warn ? "text-amber-700" : "text-emerald-700");

export default function Monitoring() {
  const [hours, setHours] = useState(6);
  const snap = useApi(api.monitoring);
  const hist = useApi(() => api.monitoringHistory(hours), [hours]);
  const { busy, run } = useAction();
  usePolling(() => { void snap.reload(); void hist.reload(); }, true, 10000);

  if (snap.loading && !snap.data) return <Loading />;
  if (snap.error && !snap.data) return <ErrorBox error={snap.error} onRetry={snap.reload} />;
  const m = snap.data;
  if (!m) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="h1">Monitoring</h1>
          <p className="muted">Số đo thực từ máy chủ <b>{m.hostname}</b> · cập nhật {fmtDate(m.generated_at)} · tự làm mới mỗi 10 giây.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" disabled={busy} onClick={() => run(async () => {
            const r = await api.runWatchdog();
            toast(r.actions.length ? r.actions.join(" · ") : "Không có tác vụ nào bị treo", r.actions.length ? "error" : "ok");
            void snap.reload();
          })}>🐕 Kiểm tra tác vụ treo</button>
          <button className="btn-ghost" disabled={busy} onClick={() => run(async () => {
            const r = await api.runMaintenance();
            toast(`Dọn dẹp xong: ${r.system_logs_deleted} log, ${r.metrics_deleted} mẫu số đo, ${r.tmp_files_deleted} file tạm`, "ok");
            void snap.reload();
          })}>🧹 Dọn dẹp ngay</button>
          <button className="btn-ghost" onClick={() => { void snap.reload(); void hist.reload(); }}>↻</button>
        </div>
      </div>

      <StatusBanner m={m} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="CPU" value={<span className={tone(m.host.cpu_percent, 80, 95)}>{m.host.cpu_percent.toFixed(0)}%</span>}
          sub={`${m.host.cpu_count} nhân${m.host.load_avg ? ` · load ${m.host.load_avg.join(" / ")}` : ""}`} />
        <Stat label="RAM" value={<span className={tone(m.host.ram_percent, m.config.limits.ram_warn_percent, 97)}>{m.host.ram_percent.toFixed(0)}%</span>}
          sub={`Trống ${m.host.ram_available_mb} MB / ${m.host.ram_total_gb} GB${m.host.swap_percent !== null ? ` · swap ${m.host.swap_percent}%` : ""}`} />
        <Stat label="Ổ đĩa lưu video" value={<span className={m.host.disk_free_gb < m.config.limits.min_free_disk_gb ? "text-red-700" : m.host.disk_free_gb < m.config.limits.disk_warn_gb ? "text-amber-700" : "text-emerald-700"}>{m.host.disk_free_gb} GB trống</span>}
          sub={`${m.host.disk_percent}% đã dùng / ${m.host.disk_total_gb} GB`} />
        <Stat label="Database" value={m.database.ok ? <span className="text-emerald-700">OK</span> : <span className="text-red-700">Lỗi</span>}
          sub={m.database.ok ? `${m.database.latency_ms} ms · ${m.database.size_mb} MB · ${m.database.connections} kết nối` : m.database.message} />
      </div>

      <div className="card p-5">
        <div className="mb-3 flex items-center gap-3">
          <div className="font-semibold">Lịch sử tài nguyên</div>
          <select className="input ml-auto w-auto" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            <option value={1}>1 giờ</option><option value={6}>6 giờ</option><option value={24}>24 giờ</option><option value={168}>7 ngày</option>
          </select>
        </div>
        {hist.data && hist.data.points.length > 1 ? (
          <div className="grid gap-6 lg:grid-cols-2">
            <HistChart title="CPU & RAM (%)" data={hist.data.points} lines={[["cpu", "CPU", PALETTE[0]], ["ram", "RAM", PALETTE[1]]]} max={100} />
            <HistChart title="Hàng đợi & FFmpeg" data={hist.data.points} lines={[["render_queue", "Render", PALETTE[2]], ["upload_queue", "Upload", PALETTE[3]], ["ffmpeg", "FFmpeg", PALETTE[4]]]} />
          </div>
        ) : <div className="muted rounded-lg bg-brand-50 p-6 text-center">Chưa đủ mẫu. Monitor worker ghi một mẫu mỗi phút — biểu đồ sẽ xuất hiện sau vài phút.</div>}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card overflow-x-auto p-5">
          <div className="mb-3 font-semibold">Workers</div>
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-ink-500"><tr>{["Worker", "Trạng thái", "Tác vụ", "Heartbeat", "PID"].map((h) => <th key={h} className="px-2 py-1.5">{h}</th>)}</tr></thead>
            <tbody>{m.workers.map((w) => <WorkerRow key={w.kind} w={w} />)}</tbody>
          </table>
          <p className="muted mt-2 text-xs">Worker mất heartbeat &gt; {m.config.limits.worker_stale_seconds}s được coi là ngừng. Supervisor tự khởi động lại sau 5 giây; tác vụ dở dang được khôi phục khi worker chạy lại.</p>
        </div>

        <div className="card p-5">
          <div className="mb-3 font-semibold">Hàng đợi</div>
          <div className="space-y-4">
            <Queue title="Render" q={m.queues.render} />
            <Queue title="Upload YouTube" q={m.queues.upload} />
            <Queue title="Đồng bộ Analytics" q={m.queues.analytics} />
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card p-5">
          <div className="mb-3 flex items-center gap-2 font-semibold">Tiến trình FFmpeg {m.processes.ffmpeg.length > 1 && <Badge tone="brand">&gt;1 — bất thường</Badge>}</div>
          {m.processes.ffmpeg.length === 0 ? <div className="muted">Không có FFmpeg đang chạy.</div> : (
            <ul className="space-y-2 text-sm">
              {m.processes.ffmpeg.map((p) => (
                <li key={p.pid} className="rounded-lg border border-brand-100 p-2">
                  <div>PID {p.pid} · {p.rss_mb} MB · chạy {dur(p.elapsed_sec)}</div>
                  <code className="block truncate text-xs text-ink-500" title={p.cmd}>{p.cmd}</code>
                </li>
              ))}
            </ul>
          )}
          <p className="muted mt-3 text-xs">Ứng dụng: {m.processes.app_processes} tiến trình, {m.processes.app_rss_mb} MB RAM. Chỉ 1 render nặng chạy tại một thời điểm.</p>
        </div>

        <div className="card p-5">
          <div className="mb-3 font-semibold">Sức khỏe YouTube (24 giờ)</div>
          <div className="mb-3 flex flex-wrap gap-2 text-sm">
            <Badge tone="green">{m.youtube.credentials.valid} kênh kết nối tốt</Badge>
            {m.youtube.credentials.expired + m.youtube.credentials.revoked > 0 && <Badge tone="brand">{m.youtube.credentials.expired + m.youtube.credentials.revoked} cần kết nối lại</Badge>}
            {m.youtube.quota_parked > 0 && <Badge tone="blue">{m.youtube.quota_parked} chờ quota</Badge>}
          </div>
          {m.youtube.recent_errors.length === 0 && m.youtube.sync_errors.length === 0 ? <div className="muted">Không có lỗi/cảnh báo YouTube.</div> : (
            <ul className="space-y-2 text-sm">
              {m.youtube.sync_errors.map((e) => <li key={e.channel_id} className="text-red-800">Analytics · {e.channel_name}: {e.kind} — {e.error}</li>)}
              {m.youtube.recent_errors.map((e, i) => <li key={i}><span className={e.level === "error" ? "text-red-800" : "text-amber-800"}>{e.category}</span> · {e.message} <span className="text-xs text-ink-500">{fmtDate(e.at)}</span></li>)}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBanner({ m }: { m: Mon }) {
  const cfg = {
    ok: { cls: "border-emerald-200 bg-emerald-50 text-emerald-900", t: "✔ Hệ thống hoạt động bình thường" },
    warning: { cls: "border-amber-200 bg-amber-50 text-amber-900", t: `! ${m.alerts.length} cảnh báo` },
    critical: { cls: "border-red-200 bg-red-50 text-red-900", t: `✖ Cần xử lý ngay — ${m.alerts.filter((a) => a.severity === "critical").length} vấn đề nghiêm trọng` },
  }[m.status];
  return (
    <div className={`card p-4 ${cfg.cls}`}>
      <div className="font-semibold">{cfg.t}</div>
      {m.alerts.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {m.alerts.map((a: MonAlert) => (
            <li key={a.code}><b>{a.severity === "critical" ? "NGHIÊM TRỌNG" : "Cảnh báo"}:</b> {a.message}{a.hint && <span className="opacity-75"> — {a.hint}</span>}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function WorkerRow({ w }: { w: MonWorker }) {
  return (
    <tr className="border-t border-brand-100">
      <td className="px-2 py-1.5 font-medium">{WORKER_LABEL[w.kind] ?? w.kind}</td>
      <td className="px-2 py-1.5"><span className={w.online ? "text-emerald-700" : "text-red-700"}>{w.online ? "● " : "○ "}{STATE_LABEL[w.state] ?? w.state}</span></td>
      <td className="px-2 py-1.5">{w.current_job_id ? `#${w.current_job_id}` : "—"}</td>
      <td className="px-2 py-1.5">{w.heartbeat_age_sec === null ? "—" : `${dur(w.heartbeat_age_sec)} trước`}</td>
      <td className="px-2 py-1.5">{w.pid ?? "—"}</td>
    </tr>
  );
}

function Queue({ title, q }: { title: string; q: QueueStat }) {
  return (
    <div>
      <div className="mb-1 text-sm font-medium">{title}</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-700">
        <span>Chờ: <b>{q.queued}</b></span><span>Đang chạy: <b>{q.running}</b></span>
        {q.waiting_retry !== undefined && <span>Chờ thử lại: <b>{q.waiting_retry}</b></span>}
        {q.failed_24h !== undefined && <span className={q.failed_24h ? "text-red-700" : ""}>Lỗi 24h: <b>{q.failed_24h}</b></span>}
        {q.succeeded_24h !== undefined && <span>Xong 24h: <b>{q.succeeded_24h}</b></span>}
        {q.oldest_queued_sec ? <span>Chờ lâu nhất: <b>{dur(q.oldest_queued_sec)}</b></span> : null}
      </div>
    </div>
  );
}

function HistChart({ title, data, lines, max }: { title: string; data: Record<string, unknown>[]; lines: [string, string, string][]; max?: number }) {
  return (
    <div>
      <div className="mb-1 text-sm font-medium">{title}</div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1e3d0" />
          <XAxis dataKey="ts" fontSize={11} minTickGap={40} tickFormatter={(v) => new Date(String(v)).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} />
          <YAxis fontSize={11} width={36} domain={max ? [0, max] : [0, "auto"]} allowDecimals={false} />
          <Tooltip labelFormatter={(l) => fmtDate(String(l))} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
          {lines.map(([k, n, c]) => <Line key={k} dataKey={k} name={n} stroke={c} dot={false} strokeWidth={2} isAnimationActive={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
