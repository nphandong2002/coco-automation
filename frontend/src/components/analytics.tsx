import { ReactNode } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { Distribution, Kpi, RetentionData, SeriesPoint, Timeseries, VideoPerf } from "../api/types";
import { Badge } from "./ui";

export const PALETTE = ["#b8703a", "#3f7f93", "#7a9a4a", "#9b5f9e", "#c9563f", "#d4a22a", "#5a6bb0", "#4a8f7b"];

export const nf = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "—" : v.toLocaleString("vi-VN", { maximumFractionDigits: digits });
export const fmtMinutes = (m: number | null | undefined) => {
  if (m === null || m === undefined) return "—";
  return m >= 120 ? `${nf(m / 60, 1)} giờ` : `${nf(m, 0)} phút`;
};
export const fmtSeconds = (s: number | null | undefined) => {
  if (s === null || s === undefined) return "—";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`;
};
export const fmtPct = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? "—" : `${nf(v, digits)}%`);
export const fmtRatio = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${nf(v * 100, 1)}%`);
export const shortDate = (s: string) => `${s.slice(8, 10)}/${s.slice(5, 7)}`;

/** Where a number comes from — dashboards must never blur real vs calculated vs missing data. */
export function SourceBadge({ kind }: { kind: "youtube_api" | "calculated" | "not_synced" | "preliminary" }) {
  const map = {
    youtube_api: { t: "YouTube API", tone: "green" as const },
    calculated: { t: "Coco tính toán", tone: "blue" as const },
    not_synced: { t: "Chưa đồng bộ", tone: "slate" as const },
    preliminary: { t: "Sơ bộ", tone: "brand" as const },
  }[kind];
  return <Badge tone={map.tone}>{map.t}</Badge>;
}

export function Delta({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-xs text-ink-300">so kỳ trước: —</span>;
  const up = pct >= 0;
  return <span className={`text-xs font-semibold ${up ? "text-emerald-700" : "text-red-700"}`}>{up ? "▲" : "▼"} {nf(Math.abs(pct), 1)}% <span className="font-normal text-ink-500">so kỳ trước</span></span>;
}

export function KpiCard({ label, kpi, format, note }: { label: string; kpi: Kpi; format: (v: number | null) => string; note?: ReactNode }) {
  const missing = kpi.value === null;
  return (
    <div className="card p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-ink-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${missing ? "text-ink-300" : ""}`}>{format(kpi.value)}</div>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        {missing ? <SourceBadge kind="not_synced" /> : <Delta pct={kpi.change_pct} />}
        {note}
      </div>
    </div>
  );
}

export function NoData({ children }: { children?: ReactNode }) {
  return (
    <div className="flex h-56 items-center justify-center rounded-lg bg-brand-50 p-4 text-center text-sm text-ink-500">
      {children ?? "Chưa có dữ liệu thực từ YouTube. Kết nối kênh rồi bấm “Đồng bộ ngay”."}
    </div>
  );
}

const tip = { contentStyle: { borderRadius: 8, border: "1px solid #f9e8d4", fontSize: 12 } };

export type SeriesMetric = "views" | "watch_time_minutes" | "subscribers_net" | "likes" | "comments";
export const SERIES_METRICS: { key: SeriesMetric; label: string }[] = [
  { key: "views", label: "Lượt xem" }, { key: "watch_time_minutes", label: "Watch time (phút)" },
  { key: "subscribers_net", label: "Subscriber ròng" }, { key: "likes", label: "Likes" }, { key: "comments", label: "Comments" },
];

/** Line chart of a metric over time; optional multi-channel lines. The newest days (preliminary) are shaded. */
export function SeriesChart({ data, metric, split }: { data: Timeseries; metric: SeriesMetric; split: boolean }) {
  if (!data.points.length) return <NoData />;
  const merged: Record<string, string | number>[] = data.points.map((p) => {
    const row: Record<string, string | number> = { period: p.period, total: p[metric] };
    data.by_channel.forEach((c) => {
      const hit = c.points.find((x: SeriesPoint) => x.period === p.period);
      row[`c${c.channel_id}`] = hit ? hit[metric] : 0;
    });
    return row;
  });
  const prelimStart = data.granularity === "day" && data.preliminary_since > data.points[0].period ? data.preliminary_since : null;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={merged} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1e3d0" />
        <XAxis dataKey="period" tickFormatter={shortDate} fontSize={11} minTickGap={24} />
        <YAxis fontSize={11} width={56} tickFormatter={(v) => nf(v as number)} />
        <Tooltip {...tip} labelFormatter={(l) => new Date(String(l)).toLocaleDateString("vi-VN")} formatter={(v) => nf(Number(v), 1)} />
        {prelimStart && <ReferenceArea x1={prelimStart} x2={data.points[data.points.length - 1].period} fill="#d4a22a" fillOpacity={0.12} />}
        {split && data.by_channel.length > 1
          ? data.by_channel.map((c, i) => <Line key={c.channel_id} dataKey={`c${c.channel_id}`} name={c.channel_name} stroke={PALETTE[i % PALETTE.length]} dot={false} strokeWidth={2} />)
          : <Line dataKey="total" name="Tổng" stroke={PALETTE[0]} dot={false} strokeWidth={2.5} />}
        {split && data.by_channel.length > 1 && <Legend />}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function VideoBars({ videos, metric }: { videos: VideoPerf[]; metric: "views" | "watch_time_minutes" | "score" }) {
  const rows = videos.filter((v) => v[metric] !== null).slice(0, 10).map((v) => ({ name: v.title.length > 28 ? v.title.slice(0, 27) + "…" : v.title, value: v[metric] as number }));
  if (!rows.length) return <NoData>Chưa có video nào có dữ liệu để so sánh.</NoData>;
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 34)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1e3d0" horizontal={false} />
        <XAxis type="number" fontSize={11} tickFormatter={(v) => nf(v as number)} />
        <YAxis type="category" dataKey="name" width={170} fontSize={11} />
        <Tooltip {...tip} formatter={(v) => nf(Number(v), 1)} />
        <Bar dataKey="value" fill={PALETTE[0]} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ChannelBars({ rows, metric }: { rows: { channel_name: string; views: number | null; watch_time_minutes: number | null }[]; metric: "views" | "watch_time_minutes" }) {
  const data = rows.filter((r) => r[metric] !== null).map((r) => ({ name: r.channel_name, value: r[metric] as number }));
  if (!data.length) return <NoData>Chưa kênh nào có dữ liệu đã đồng bộ.</NoData>;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ left: 0, right: 12 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1e3d0" />
        <XAxis dataKey="name" fontSize={11} />
        <YAxis fontSize={11} width={56} tickFormatter={(v) => nf(v as number)} />
        <Tooltip {...tip} formatter={(v) => nf(Number(v), 1)} />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>{data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}</Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Donut({ data }: { data: Distribution }) {
  if (!data.items.length) return <NoData>Chưa có lượt xem để phân bổ.</NoData>;
  return (
    <div className="flex flex-col items-center gap-2 md:flex-row">
      <ResponsiveContainer width="100%" height={230}>
        <PieChart>
          <Pie data={data.items} dataKey="views" nameKey="label" innerRadius={55} outerRadius={90} paddingAngle={2}>
            {data.items.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
          </Pie>
          <Tooltip {...tip} formatter={(v) => nf(Number(v))} />
        </PieChart>
      </ResponsiveContainer>
      <ul className="w-full space-y-1 text-sm md:w-64">
        {data.items.map((i, k) => (
          <li key={i.key} className="flex items-center gap-2">
            <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: PALETTE[k % PALETTE.length] }} />
            <span className="truncate">{i.label}</span><span className="ml-auto text-ink-500">{nf(i.share, 1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RetentionChart({ data }: { data: RetentionData }) {
  if (data.data_state === "not_synced" || !data.points.length) return <NoData>{data.note ?? "Chưa có đường giữ chân người xem từ YouTube."}</NoData>;
  const rows = data.points.map(([x, y]) => ({ x: Math.round(x * 100), y: +(y * 100).toFixed(1) }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1e3d0" />
        <XAxis dataKey="x" unit="%" fontSize={11} />
        <YAxis fontSize={11} unit="%" width={48} />
        <Tooltip {...tip} formatter={(v) => `${v}%`} labelFormatter={(l) => `${l}% thời lượng video`} />
        <Area dataKey="y" name="Người xem còn lại" stroke={PALETTE[1]} fill={PALETTE[1]} fillOpacity={0.2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SlotBars({ rows, labelOf, metric = "avg_views_7d" }: { rows: { n: number; avg_views_7d: number | null; reliable: boolean; [k: string]: unknown }[]; labelOf: (r: { [k: string]: unknown }) => string; metric?: "avg_views_7d" }) {
  const data = rows.map((r) => ({ name: labelOf(r), value: r[metric] ?? 0, n: r.n, reliable: r.reliable }));
  if (!data.some((d) => d.n > 0)) return <NoData>Chưa đủ video có đủ 8 ngày dữ liệu từ lúc đăng.</NoData>;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ left: 0, right: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1e3d0" />
        <XAxis dataKey="name" fontSize={10} interval={0} />
        <YAxis fontSize={11} width={48} />
        <Tooltip {...tip} formatter={(v, _n, p) => [`${nf(Number(v), 1)} (${(p.payload as { n: number }).n} video)`, "Lượt xem 7 ngày đầu (TB)"]} />
        <Bar dataKey="value" radius={[3, 3, 0, 0]}>{data.map((d, i) => <Cell key={i} fill={d.reliable ? PALETTE[0] : "#e8cfae"} />)}</Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
