import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { AnalyticsFilters, GroupStat, Insights, SyncStatusInfo, VideoPerf } from "../api/types";
import {
  ChannelBars, Delta, Donut, KpiCard, NoData, RetentionChart, SERIES_METRICS, SeriesChart, SeriesMetric, SlotBars,
  SourceBadge, VideoBars, fmtMinutes, fmtPct, fmtRatio, fmtSeconds, nf,
} from "../components/analytics";
import { CONTENT_TYPES, usePolling } from "../components/production";
import { Badge, Empty, ErrorBox, Loading, Modal, Stat, Tabs } from "../components/ui";
import { fmtDate, toast, useAction, useApi } from "../lib/hooks";

const isoDay = (d: Date) => d.toISOString().slice(0, 10);
const daysAgo = (n: number) => isoDay(new Date(Date.now() - n * 86_400_000));
const fmtDay = (d: string) => new Date(d).toLocaleDateString("vi-VN");
const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

const LABEL: Record<VideoPerf["label"], { t: string; tone: "green" | "slate" | "brand" | "blue" }> = {
  strong: { t: "Hiệu quả cao", tone: "green" }, average: { t: "Trung bình", tone: "blue" }, weak: { t: "Thấp", tone: "brand" },
  insufficient_data: { t: "Chưa đủ video so sánh", tone: "slate" }, too_new: { t: "Quá mới (<3 ngày)", tone: "slate" },
  not_synced: { t: "Chưa đồng bộ", tone: "slate" },
};

export default function Analytics() {
  return <AnalyticsView />;
}

/** Whole analytics dashboard. With `channelId` it is the channel's own Analytics tab. */
export function AnalyticsView({ channelId }: { channelId?: number }) {
  const channels = useApi(api.channels);
  const [f, setF] = useState<AnalyticsFilters>({ channel_id: channelId ?? "", start: daysAgo(27), end: daysAgo(0), topic: "", video_status: "" });
  const [granularity, setGranularity] = useState("day");
  const [metric, setMetric] = useState<SeriesMetric>("views");
  const [split, setSplit] = useState(false);
  const [videoMetric, setVideoMetric] = useState<"views" | "watch_time_minutes" | "score">("watch_time_minutes");
  const [tab, setTab] = useState<"charts" | "videos" | "insights">("charts");
  const [retentionFor, setRetentionFor] = useState<VideoPerf | null>(null);
  const [donutBy, setDonutBy] = useState<"channel" | "topic">(channelId ? "topic" : "channel");
  const scoped = channelId !== undefined;
  const key = JSON.stringify(f);

  const sync = useApi(() => api.anSyncStatus(f.channel_id), [f.channel_id]);
  const summary = useApi(() => api.anSummary(f), [key]);
  const series = useApi(() => api.anSeries(f, granularity, split), [key, granularity, split]);
  const dist = useApi(() => api.anDistribution(f, donutBy), [key, donutBy]);
  const compare = useApi(() => api.anCompare(f), [f.start, f.end]);
  const videos = useApi(() => api.anVideos(f, "score"), [key]);
  const insights = useApi(() => api.anInsights(f), [key]);
  const { busy, run } = useAction();

  const queued = (sync.data?.channels ?? []).length > 0;
  usePolling(() => { void sync.reload(); }, queued, 15000);

  const reloadAll = () => { void sync.reload(); void summary.reload(); void series.reload(); void dist.reload(); void compare.reload(); void videos.reload(); void insights.reload(); };
  const doSync = async () => {
    if (scoped) await run(() => api.anSyncChannel(channelId!), "Đã xếp lịch đồng bộ — dữ liệu sẽ cập nhật sau ít phút");
    else {
      const r = await run(() => api.anSyncAll());
      if (r) toast(r.queued ? `Đã xếp lịch đồng bộ ${r.queued} kênh` : "Không có kênh nào cần/được phép đồng bộ", r.queued ? "ok" : "error");
    }
    void sync.reload();
  };

  const set = (patch: Partial<AnalyticsFilters>) => setF((x) => ({ ...x, ...patch }));
  const s = summary.data;

  return (
    <div className="space-y-6">
      {!scoped && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="h1">Analytics</h1>
            <p className="muted">Số liệu thực từ YouTube Analytics API & Data API. Giá trị chưa đồng bộ hiển thị “—”, không bao giờ là số giả.</p>
          </div>
          <button className="btn-ghost" onClick={reloadAll}>↻ Làm mới</button>
        </div>
      )}

      <SyncBar info={sync.data} busy={busy} onSync={doSync} scoped={scoped} />

      {/* ---------------------------------------------------------------- filters */}
      <div className="card grid grid-cols-2 gap-3 p-4 md:grid-cols-3 lg:grid-cols-6">
        {!scoped && (
          <label><span className="label">Kênh</span>
            <select className="input" value={f.channel_id ?? ""} onChange={(e) => set({ channel_id: e.target.value ? Number(e.target.value) : "" })}>
              <option value="">Tất cả kênh</option>
              {(channels.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></label>
        )}
        <label><span className="label">Từ ngày</span><input type="date" className="input" value={f.start} max={f.end} onChange={(e) => set({ start: e.target.value })} /></label>
        <label><span className="label">Đến ngày</span><input type="date" className="input" value={f.end} min={f.start} onChange={(e) => set({ end: e.target.value })} /></label>
        <label><span className="label">Chủ đề</span>
          <select className="input" value={f.topic ?? ""} onChange={(e) => set({ topic: e.target.value })}>
            <option value="">Tất cả</option>
            {Object.entries(CONTENT_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
        <label><span className="label">Trạng thái video</span>
          <select className="input" value={f.video_status ?? ""} onChange={(e) => set({ video_status: e.target.value })}>
            <option value="">Tất cả</option><option value="public">Public</option><option value="unlisted">Unlisted</option><option value="private">Private</option>
          </select></label>
        <div className="flex items-end gap-2">
          {[7, 28, 90].map((d) => <button key={d} className="btn-ghost" onClick={() => set({ start: daysAgo(d - 1), end: daysAgo(0) })}>{d}d</button>)}
        </div>
      </div>

      {summary.error ? <ErrorBox error={summary.error} onRetry={summary.reload} /> : !s ? <Loading /> : (
        <>
          {s.basis === "videos" && <div className="card border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">Đang lọc theo chủ đề/trạng thái video: số liệu được cộng từ báo cáo từng video (không có “subscriber mất”).</div>}
          {s.data_state === "not_synced" && (
            <div className="card border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              Chưa có dữ liệu YouTube trong khoảng này. {s.sync.connected === 0 ? <>Hãy <Link className="underline" to="/channels">kết nối YouTube cho kênh</Link>.</> : "Bấm “Đồng bộ ngay” hoặc chờ worker tự đồng bộ."}
            </div>
          )}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KpiCard label="Lượt xem" kpi={s.kpis.views} format={(v) => nf(v)} />
            <KpiCard label="Watch time" kpi={s.kpis.watch_time_minutes} format={fmtMinutes} />
            <KpiCard label="Thời gian xem TB" kpi={s.kpis.average_view_duration_sec} format={fmtSeconds} />
            <KpiCard label="% xem TB" kpi={s.kpis.average_view_percentage} format={(v) => fmtPct(v)} />
            <KpiCard label="Subscriber ròng" kpi={s.kpis.subscribers_net.value === null ? s.kpis.subscribers_gained : s.kpis.subscribers_net}
              format={(v) => (v === null ? "—" : (v > 0 ? "+" : "") + nf(v))}
              note={s.kpis.subscribers_net.value !== null ? <span className="text-xs text-ink-500">+{nf(s.kpis.subscribers_gained.value)} / −{nf(s.kpis.subscribers_lost.value)}</span> : <span className="text-xs text-ink-500">chỉ tính “gained”</span>} />
            <Stat label="Tổng subscriber" value={s.subscribers_total.value === null ? "—" : nf(s.subscribers_total.value)}
              sub={s.subscribers_total.value === null ? <SourceBadge kind="not_synced" /> :
                <>{s.subscribers_total.channels_counted}/{s.subscribers_total.channels_total} kênh{s.subscribers_total.channels_hidden ? ` · ${s.subscribers_total.channels_hidden} ẩn số sub` : ""}</>} />
            <KpiCard label="Likes" kpi={s.kpis.likes} format={(v) => nf(v)} />
            <KpiCard label="Comments" kpi={s.kpis.comments} format={(v) => nf(v)} />
          </div>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Video đã đăng" value={s.production.videos_published} sub="Có ID YouTube" />
            <Stat label="Đang xử lý" value={s.production.videos_processing} sub="Render + upload" />
            <Stat label="Thất bại" value={s.production.videos_failed} sub="Render hoặc upload lỗi" />
            <Stat label={s.best_channel ? "Kênh tốt nhất (watch time)" : "Video xem nhiều nhất"}
              value={<span className="text-lg">{s.best_channel?.channel_name ?? s.top_video?.title ?? "—"}</span>}
              sub={s.best_channel ? `${fmtMinutes(s.best_channel.watch_time_minutes)} · ${nf(s.best_channel.views)} lượt xem` : s.top_video ? `${nf(s.top_video.views)} lượt xem` : "Chưa có dữ liệu"} />
          </div>
          <p className="muted text-xs">
            Dữ liệu từ {fmtDay(s.range.start)} đến {fmtDay(s.range.end)}{s.last_synced_at ? ` · đồng bộ lần cuối ${fmtDate(s.last_synced_at)}` : ""}.
            Các ngày từ {fmtDay(s.preliminary_since)} là dữ liệu <SourceBadge kind="preliminary" /> — YouTube có thể điều chỉnh.
            {s.top_video && !s.best_channel && <> Video xem nhiều nhất: <b>{s.top_video.title}</b>.</>}
          </p>
        </>
      )}

      <Tabs<"charts" | "videos" | "insights"> value={tab} onChange={setTab} tabs={[
        { key: "charts", label: "Biểu đồ" }, { key: "videos", label: "Hiệu suất video" }, { key: "insights", label: "Đánh giá & đề xuất" }]} />

      {tab === "charts" && (
        <div className="space-y-6">
          <div className="card p-5">
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <div className="font-semibold">Theo thời gian</div>
              <select className="input w-auto" value={metric} onChange={(e) => setMetric(e.target.value as SeriesMetric)}>
                {SERIES_METRICS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
              </select>
              <select className="input w-auto" value={granularity} onChange={(e) => setGranularity(e.target.value)}>
                <option value="day">Theo ngày</option><option value="week">Theo tuần</option><option value="month">Theo tháng</option>
              </select>
              {!scoped && !f.channel_id && <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} />Tách theo kênh</label>}
              <span className="ml-auto"><SourceBadge kind={series.data?.data_state === "synced" ? "youtube_api" : "not_synced"} /></span>
            </div>
            {series.error ? <ErrorBox error={series.error} /> : series.data ? <SeriesChart data={series.data} metric={metric} split={split} /> : <Loading />}
            <div className="muted mt-1 text-xs">Vùng vàng = ngày gần nhất (sơ bộ). Ngày YouTube không trả dữ liệu không được vẽ thành 0.</div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card p-5">
              <div className="mb-3 flex items-center gap-3">
                <div className="font-semibold">So sánh video</div>
                <select className="input ml-auto w-auto" value={videoMetric} onChange={(e) => setVideoMetric(e.target.value as typeof videoMetric)}>
                  <option value="watch_time_minutes">Watch time</option><option value="views">Lượt xem</option><option value="score">Điểm hiệu quả</option>
                </select>
              </div>
              {videos.data ? <VideoBars videos={[...videos.data.items].sort((a, b) => ((b[videoMetric] ?? -1) - (a[videoMetric] ?? -1)))} metric={videoMetric} /> : <Loading />}
            </div>
            <div className="card p-5">
              <div className="mb-3 flex items-center gap-3">
                <div className="font-semibold">Phân bổ lượt xem</div>
                <select className="input ml-auto w-auto" value={donutBy} onChange={(e) => setDonutBy(e.target.value as "channel" | "topic")}>
                  {!scoped && <option value="channel">Theo kênh</option>}<option value="topic">Theo chủ đề</option>
                </select>
              </div>
              {dist.data ? <Donut data={dist.data} /> : <Loading />}
            </div>
          </div>

          {!scoped && (
            <div className="card p-5">
              <div className="mb-3 font-semibold">So sánh các kênh</div>
              {compare.data ? (
                <div className="space-y-4">
                  <div className="grid gap-6 lg:grid-cols-2">
                    <ChannelBars rows={compare.data.items} metric="views" />
                    <ChannelBars rows={compare.data.items} metric="watch_time_minutes" />
                  </div>
                  <ChannelTable rows={compare.data.items} best={compare.data.best?.channel_id} note={compare.data.growth_note} />
                </div>
              ) : <Loading />}
            </div>
          )}
          <RetentionPanel channelId={f.channel_id} />
        </div>
      )}

      {tab === "videos" && (
        <div className="card overflow-x-auto">
          {videos.error ? <ErrorBox error={videos.error} /> : !videos.data ? <Loading /> : videos.data.items.length === 0
            ? <Empty title="Chưa có video đã đăng lên YouTube">Video xuất hiện ở đây sau khi upload qua Publishing.</Empty>
            : <VideoTable items={videos.data.items} showChannel={!scoped} onRetention={setRetentionFor} note={videos.data.scoring.note} />}
        </div>
      )}

      {tab === "insights" && (insights.error ? <ErrorBox error={insights.error} onRetry={insights.reload} /> : !insights.data ? <Loading /> : <InsightsPanel data={insights.data} channelId={f.channel_id} />)}

      {retentionFor && <RetentionModal video={retentionFor} onClose={() => setRetentionFor(null)} />}
    </div>
  );
}

// ------------------------------------------------------------------ sync
function SyncBar({ info, busy, onSync, scoped }: { info: SyncStatusInfo | null; busy: boolean; onSync: () => void; scoped: boolean }) {
  const rows = info?.channels ?? [];
  const bad = rows.filter((c) => c.state === "error");
  const STATE: Record<string, string> = { synced: "Đã đồng bộ", stale: "Cũ", not_synced: "Chưa đồng bộ", error: "Lỗi", disconnected: "Chưa kết nối" };
  const latest = rows.map((r) => r.last_success_at).filter(Boolean).sort().pop();
  return (
    <div className="card space-y-2 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn-primary" disabled={busy || rows.every((r) => !r.connected)} onClick={onSync}>{busy ? "Đang xếp lịch…" : "⟳ Đồng bộ ngay"}</button>
        <span className="text-sm text-ink-500">
          {latest ? `Lần đồng bộ thành công gần nhất: ${fmtDate(latest)}` : "Chưa có lần đồng bộ nào"} · tự động mỗi {info ? Math.round(info.interval_minutes / 60 * 10) / 10 : "—"} giờ
        </span>
        {info && !info.worker_alive && <Badge tone="brand">Analytics worker chưa chạy — dữ liệu sẽ không tự cập nhật</Badge>}
      </div>
      {!scoped && rows.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {rows.map((c) => (
            <span key={c.channel_id} title={c.error ?? ""} className={`rounded-full px-2 py-0.5 text-xs ${c.state === "error" ? "bg-red-100 text-red-800" : c.state === "synced" ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-700"}`}>
              {c.channel_name}: {STATE[c.state]}
            </span>
          ))}
        </div>
      )}
      {bad.map((c) => (
        <div key={c.channel_id} className="rounded-lg bg-red-50 p-2 text-sm text-red-800">
          <b>{c.channel_name}</b> — {c.error}{" "}
          {(c.error_kind === "scope" || c.error_kind === "auth") && <Link className="underline" to={`/channels/${c.channel_id}`}>Kết nối lại YouTube</Link>}
          {c.error_kind === "quota" && c.retry_after && <> · thử lại sau {fmtDate(c.retry_after)}</>}
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ tables
function ChannelTable({ rows, best, note }: { rows: import("../api/types").ChannelCompareRow[]; best?: number; note: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-ink-500"><tr>
          {["Kênh", "Lượt xem", "Tăng trưởng", "Watch time", "Sub ròng", "Tổng sub", "% xem TB", "Tương tác", "Video đăng"].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.channel_id} className="border-t border-brand-100">
              <td className="px-3 py-2 font-medium"><Link className="hover:underline" to={`/channels/${r.channel_id}`}>{r.channel_name}</Link>{best === r.channel_id && <> <Badge tone="green">Tốt nhất</Badge></>}</td>
              <td className="px-3 py-2">{nf(r.views)}</td>
              <td className="px-3 py-2"><Delta pct={r.views_growth_pct} /></td>
              <td className="px-3 py-2">{fmtMinutes(r.watch_time_minutes)}</td>
              <td className="px-3 py-2">{r.subscribers_net === null ? "—" : (r.subscribers_net > 0 ? "+" : "") + nf(r.subscribers_net)}</td>
              <td className="px-3 py-2">{nf(r.subscribers_total)}</td>
              <td className="px-3 py-2">{fmtPct(r.average_view_percentage)}</td>
              <td className="px-3 py-2">{fmtRatio(r.engagement_rate)}</td>
              <td className="px-3 py-2">{r.videos_published}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted mt-2 text-xs">{note} “Tốt nhất” = nhiều watch time nhất trong kỳ.</p>
    </div>
  );
}

function VideoTable({ items, showChannel, onRetention, note }: { items: VideoPerf[]; showChannel: boolean; onRetention: (v: VideoPerf) => void; note: string }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-xs uppercase text-ink-500"><tr>
        {["Video", ...(showChannel ? ["Kênh"] : []), "Đánh giá", "Lượt xem", "Watch time", "TB xem", "% xem", "Giữ chân", "Sub +", "Tương tác", ""].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}
      </tr></thead>
      <tbody>
        {items.map((v) => (
          <>
            <tr key={v.video_id} className="border-t border-brand-100 align-top">
              <td className="max-w-xs px-3 py-2">
                <div className="truncate font-medium" title={v.title}>{v.title}</div>
                <div className="text-xs text-ink-500">{v.content_type ? CONTENT_TYPES[v.content_type] : "—"}{v.duration_minutes ? ` · ${nf(v.duration_minutes)} phút` : ""}{v.published_at ? ` · ${fmtDay(v.published_at)}` : ""}</div>
              </td>
              {showChannel && <td className="px-3 py-2">{v.channel_name}</td>}
              <td className="px-3 py-2">
                <Badge tone={LABEL[v.label].tone}>{LABEL[v.label].t}</Badge>
                {v.score !== null && <div className="mt-0.5 text-xs text-ink-500" title="Điểm Coco tính: watch time, % xem, giữ chân, sub, tương tác, lượt xem/ngày">điểm {nf(v.score)}/100</div>}
              </td>
              <td className="px-3 py-2">{nf(v.views)}</td>
              <td className="px-3 py-2">{fmtMinutes(v.watch_time_minutes)}</td>
              <td className="px-3 py-2">{fmtSeconds(v.average_view_duration_sec)}</td>
              <td className="px-3 py-2">{fmtPct(v.average_view_percentage)}</td>
              <td className="px-3 py-2">{v.has_retention ? <button className="text-brand-700 underline" onClick={() => onRetention(v)}>{fmtRatio(v.retention_avg)}</button> : "—"}</td>
              <td className="px-3 py-2">{nf(v.subscribers_gained)}</td>
              <td className="px-3 py-2">{fmtRatio(v.engagement_rate)}</td>
              <td className="px-3 py-2">{v.weak_reasons.length > 0 && <button className="text-xs underline" onClick={() => setOpen(open === v.video_id ? null : v.video_id)}>Vì sao thấp?</button>}</td>
            </tr>
            {open === v.video_id && (
              <tr key={`r${v.video_id}`} className="bg-brand-50"><td colSpan={11} className="px-3 py-2 text-sm"><ul className="list-disc pl-5">{v.weak_reasons.map((r) => <li key={r}>{r}</li>)}</ul></td></tr>
            )}
          </>
        ))}
      </tbody>
      <tfoot><tr><td colSpan={11} className="muted px-3 py-2 text-xs">{note} <SourceBadge kind="youtube_api" /> số liệu · <SourceBadge kind="calculated" /> điểm & nhãn.</td></tr></tfoot>
    </table>
  );
}

function RetentionModal({ video, onClose }: { video: VideoPerf; onClose: () => void }) {
  const { data, error, loading } = useApi(() => api.anVideoRetention(video.video_id), [video.video_id]);
  return (
    <Modal title={`Giữ chân người xem — ${video.title}`} onClose={onClose} wide>
      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : data && (
        <div className="space-y-3">
          <RetentionChart data={data} />
          <RetentionFacts s={data.summary} />
        </div>
      )}
    </Modal>
  );
}

function RetentionFacts({ s }: { s: import("../api/types").RetentionSummary }) {
  if (s.average === null) return null;
  return (
    <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-5">
      {[["Trung bình", s.average], ["Còn lại ở 10%", s.at_10], ["25%", s.at_25], ["50%", s.at_50], ["75%", s.at_75]].map(([l, v]) => (
        <div key={String(l)}><div className="text-xs text-ink-500">{l}</div><div className="font-semibold">{fmtRatio(v as number | null)}</div></div>
      ))}
      {s.steepest_drop && <div className="col-span-full text-red-800">Rơi mạnh nhất: từ {Math.round(s.steepest_drop.from * 100)}% đến {Math.round(s.steepest_drop.to * 100)}% video ({nf(s.steepest_drop.delta * 100, 0)} điểm %).</div>}
    </div>
  );
}

function RetentionPanel({ channelId }: { channelId?: number | "" }) {
  const { data, error, loading } = useApi(() => api.anChannelRetention(channelId), [channelId]);
  return (
    <div className="card p-5">
      <div className="mb-3 flex items-center gap-3"><div className="font-semibold">Giữ chân người xem (trung bình các video)</div>
        {data && <SourceBadge kind={data.data_state === "synced" ? "youtube_api" : "not_synced"} />}{data?.n_videos ? <span className="muted">{data.n_videos} video</span> : null}</div>
      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : data && <><RetentionChart data={data} /><div className="mt-3"><RetentionFacts s={data.summary} /></div></>}
    </div>
  );
}

// ------------------------------------------------------------------ insights
const CONF: Record<string, { t: string; tone: "green" | "blue" | "slate" }> = { high: { t: "Độ tin cậy cao", tone: "green" }, medium: { t: "Trung bình", tone: "blue" }, low: { t: "Mẫu ít", tone: "slate" } };

function InsightsPanel({ data, channelId }: { data: Insights; channelId?: number | "" }) {
  const ideaCid = channelId || undefined; // idea generation lives in Content Library
  return (
    <div className="space-y-6">
      <div className="card p-5">
        <div className="mb-1 flex items-center gap-2 font-semibold">Đề xuất nội dung tiếp theo <SourceBadge kind="calculated" /></div>
        <p className="muted mb-3 text-xs">Dựa trên {data.videos_scored}/{data.videos_total} video đã đủ dữ liệu. Mỗi đề xuất ghi rõ số liệu căn cứ; không dùng riêng lượt xem.</p>
        <ul className="space-y-3">
          {data.recommendations.map((r, i) => (
            <li key={i} className="rounded-lg border border-brand-100 p-3 text-sm">
              <div className="mb-1 flex items-center gap-2"><Badge tone={CONF[r.confidence].tone}>{CONF[r.confidence].t}</Badge><span className="text-xs uppercase text-ink-500">{r.kind}</span></div>
              {r.text}
              {r.suggested_content_type && ideaCid && <div className="mt-2"><Link className="btn-ghost" to="/content">Mở Content Library để sinh ý tưởng “{CONTENT_TYPES[r.suggested_content_type]}” →</Link></div>}
            </li>
          ))}
          {data.recommendations.length === 0 && <li className="muted">Chưa có đề xuất nào.</li>}
        </ul>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <GroupTable title="Chủ đề (loại nội dung)" rows={data.topics} />
        <GroupTable title="Thời lượng video" rows={data.durations} />
      </div>
      <GroupTable title="Chủ đề chi tiết (theme)" rows={data.themes} />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card p-5">
          <div className="mb-2 font-semibold">Khung giờ đăng (giờ của kênh)</div>
          <SlotBars rows={data.posting_times.by_hour as never} labelOf={(r) => `${String(r.hour).padStart(2, "0")}h`} />
          <p className="muted mt-1 text-xs">{data.posting_times.measured_videos} video đo được. Cột nhạt = dưới 3 mẫu, chưa đáng tin. {data.posting_times.note}</p>
        </div>
        <div className="card p-5">
          <div className="mb-2 font-semibold">Ngày trong tuần</div>
          <SlotBars rows={data.posting_times.by_weekday as never} labelOf={(r) => WEEKDAYS[r.weekday as number]} />
        </div>
      </div>

      <div className="card p-5">
        <div className="mb-2 font-semibold">Video hiệu suất thấp</div>
        {data.underperformers.length === 0 ? <div className="muted">Không có video nào bị đánh giá thấp (hoặc chưa đủ video để so sánh).</div> : (
          <ul className="space-y-3">
            {data.underperformers.map((u) => (
              <li key={u.video_id} className="text-sm"><b>{u.title}</b> <span className="text-ink-500">· {u.channel_name} · điểm {nf(u.score)}</span>
                <ul className="list-disc pl-5 text-ink-700">{u.reasons.map((r) => <li key={r}>{r}</li>)}</ul></li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function GroupTable({ title, rows }: { title: string; rows: GroupStat[] }) {
  const label = useMemo(() => (g: GroupStat) => (g.group === "content_type" ? CONTENT_TYPES[g.key as keyof typeof CONTENT_TYPES] ?? String(g.key) : g.label), []);
  return (
    <div className="card overflow-x-auto p-5">
      <div className="mb-2 font-semibold">{title}</div>
      {rows.length === 0 ? <NoData>Chưa có dữ liệu.</NoData> : (
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-ink-500"><tr>{["", "Video", "Điểm TB", "Lượt xem/ngày", "% xem", "Sub/1000"].map((h) => <th key={h} className="px-2 py-1.5">{h}</th>)}</tr></thead>
          <tbody>{rows.map((g) => (
            <tr key={String(g.key)} className="border-t border-brand-100">
              <td className="px-2 py-1.5 font-medium">{label(g)}</td><td className="px-2 py-1.5">{g.n_videos}</td>
              <td className="px-2 py-1.5">{g.avg_score === null ? <span className="text-ink-300" title="Cần ≥4 video đủ dữ liệu trong kênh">—</span> : nf(g.avg_score)}</td>
              <td className="px-2 py-1.5">{nf(g.avg_views_per_day, 1)}</td><td className="px-2 py-1.5">{fmtPct(g.avg_view_pct)}</td><td className="px-2 py-1.5">{nf(g.subs_per_1k_views, 2)}</td>
            </tr>))}</tbody>
        </table>
      )}
    </div>
  );
}
