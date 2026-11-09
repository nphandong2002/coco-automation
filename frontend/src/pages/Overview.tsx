import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { MetricValue } from "../api/types";
import { ErrorBox, Loading, Stat } from "../components/ui";
import { fmtDate, useApi } from "../lib/hooks";

function metric(m: MetricValue, unit = "") {
  if (m.value === null) return { value: "—", sub: "Chưa đồng bộ từ YouTube — vào Analytics để đồng bộ" };
  return {
    value: Math.round(m.value).toLocaleString("vi-VN") + unit,
    sub: `Nguồn: ${m.source === "youtube_api" ? "YouTube API" : "Ước tính"}${m.synced_at ? " · " + fmtDate(m.synced_at) : ""}`,
  };
}

function Sparkline({ points }: { points: { day: string; views: number }[] }) {
  const w = 600, h = 140, max = Math.max(...points.map((p) => p.views), 1);
  const d = points.map((p, i) => `${i ? "L" : "M"}${(i / Math.max(points.length - 1, 1)) * w},${h - (p.views / max) * (h - 10)}`).join(" ");
  return <svg viewBox={`0 0 ${w} ${h}`} className="h-36 w-full"><path d={d} fill="none" stroke="#b8703a" strokeWidth="2.5" /></svg>;
}

export default function Overview() {
  const { data, error, loading, reload } = useApi(api.overview);
  const mon = useApi(api.monitoring);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const s = data.channels_by_status;
  const views = metric(data.total_views);
  const subs = metric(data.total_subscribers);
  const gained = metric(data.total_subscribers_gained);
  const wt = metric(data.total_watch_time_minutes, " phút");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="h1">Overview</h1>
        <div className="flex gap-2"><Link className="btn-ghost" to="/analytics">▲ Analytics chi tiết</Link><button className="btn-ghost" onClick={reload}>↻ Làm mới</button></div>
      </div>

      {mon.data && mon.data.status !== "ok" && (
        <Link to="/monitoring" className={`card block p-3 text-sm ${mon.data.status === "critical" ? "border-red-200 bg-red-50 text-red-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
          <b>{mon.data.status === "critical" ? "✖ Hệ thống cần xử lý ngay" : "! Hệ thống có cảnh báo"}:</b> {mon.data.alerts[0]?.message}
          {mon.data.alerts.length > 1 && ` (+${mon.data.alerts.length - 1} nữa)`} — xem Monitoring →
        </Link>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Tổng số kênh" value={data.channels_total}
          sub={`${s.active} active · ${s.paused} paused · ${s.error} error · ${s.disconnected} disconnected`} />
        <Stat label="Kênh đang hoạt động" value={s.active} sub="Đã kết nối YouTube và đang bật" />
        <Stat label="Nhân vật" value={data.characters_total} />
        <Stat label="Dự án nội dung" value={data.content_projects_total} />
        <Stat label="Video đã sản xuất" value={data.videos_produced} />
        <Stat label="Đang render" value={data.render_jobs_running} sub={`${data.render_jobs_queued} trong hàng đợi`} />
        <Stat label="Chờ đăng" value={data.videos_waiting_publish} />
        <Stat label="Tổng lượt xem" value={views.value} sub={views.sub} />
        <Stat label="Tổng subscriber" value={subs.value} sub={subs.sub} />
        <Stat label="Subscriber tăng (kỳ đã đồng bộ)" value={gained.value} sub={gained.sub} />
        <Stat label="Watch time" value={wt.value} sub={wt.sub} />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="card p-5 lg:col-span-3">
          <div className="mb-2 font-semibold">Lượt xem 30 ngày gần nhất</div>
          {data.daily_views.length ? <Sparkline points={data.daily_views} /> : (
            <div className="flex h-36 items-center justify-center rounded-lg bg-brand-50 text-sm text-ink-500">
              Chưa có dữ liệu thực từ YouTube Analytics. Kết nối kênh rồi đồng bộ tại trang Analytics để thấy biểu đồ.
            </div>
          )}
        </div>
        <div className="card p-5 lg:col-span-2">
          <div className="mb-3 font-semibold">Hoạt động gần đây</div>
          {data.recent_activity.length === 0 ? <div className="muted">Chưa có hoạt động. <Link className="text-brand-700 underline" to="/channels">Tạo kênh đầu tiên</Link></div> : (
            <ul className="space-y-2.5">
              {data.recent_activity.map((a) => (
                <li key={a.id} className="text-sm">
                  <div>{a.message}</div>
                  <div className="text-xs text-ink-500">{fmtDate(a.created_at)}{a.channel_name ? ` · ${a.channel_name}` : ""}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
