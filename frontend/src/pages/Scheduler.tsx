import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { PublishBadge } from "../components/publishing";
import { Empty, ErrorBox, Loading } from "../components/ui";
import { fmtDate, useApi } from "../lib/hooks";

const DAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"];

export default function Scheduler() {
  const channels = useApi(api.channels);
  const [channelId, setChannelId] = useState<number | "">("");
  const id = channelId === "" ? channels.data?.[0]?.id : channelId;
  const ch = channels.data?.find((c) => c.id === id);
  const slots = useApi(async () => (id ? api.slots(id, 10) : null), [id]);
  const jobs = useApi(async () => (id ? api.publishJobs({ channel_id: id, limit: 200 }) : []), [id]);

  if (channels.loading) return <Loading />;
  if (channels.error) return <ErrorBox error={channels.error} onRetry={channels.reload} />;
  if (!channels.data?.length) return <Empty title="Chưa có kênh nào">Tạo kênh trước khi lên lịch đăng.</Empty>;

  const upcoming = (jobs.data ?? [])
    .filter((j) => j.publish_at && new Date(j.publish_at) > new Date() && j.status !== "cancelled" && j.status !== "failed")
    .sort((a, b) => +new Date(a.publish_at!) - +new Date(b.publish_at!));
  const sched = ch?.publish_schedule;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="h1">Scheduler</h1>
          <p className="muted">Lịch đăng riêng của từng kênh. Video được upload ở chế độ Private, YouTube tự công khai đúng giờ hẹn.</p>
        </div>
        <select className="input w-auto" value={id ?? ""} onChange={(e) => setChannelId(+e.target.value)}>
          {channels.data.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card space-y-3 p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Khung giờ đăng hằng tuần</h2>
            {ch && <Link className="text-sm text-brand-700 underline" to={`/channels/${ch.id}`}>Sửa trong kênh</Link>}
          </div>
          {!sched?.slots?.length ? <p className="muted">Kênh chưa có khung giờ. Thêm trong Sửa kênh → Lịch đăng.</p> : (
            <>
              <div className="text-xs text-ink-500">Múi giờ: {sched.timezone}</div>
              <ul className="space-y-1 text-sm">
                {[...(sched.slots ?? [])].sort((a, b) => a.weekday - b.weekday || a.time.localeCompare(b.time)).map((s, i) => (
                  <li key={i} className="flex gap-3"><span className="w-20 text-ink-500">{DAYS[s.weekday]}</span><span className="font-mono">{s.time}</span></li>
                ))}
              </ul>
            </>
          )}
        </div>
        <div className="card space-y-3 p-5">
          <h2 className="font-semibold">Slot trống kế tiếp</h2>
          {slots.loading ? <Loading /> : !slots.data?.slots.length ? <p className="muted">Không có slot trống.</p> : (
            <ul className="space-y-1 text-sm">{slots.data.slots.map((s) => <li key={s}>{fmtDate(s)}</li>)}</ul>
          )}
          <p className="muted">Khi đăng video, chọn "Slot trống kế tiếp của kênh" để tự gán giờ, không trùng video khác.</p>
        </div>
      </div>

      <div className="card">
        <h2 className="border-b border-brand-50 px-5 py-3 font-semibold">Video đã hẹn giờ công khai</h2>
        {!upcoming.length ? <p className="muted p-5">Chưa có video nào được hẹn giờ.</p> : (
          <ul className="divide-y divide-brand-50">
            {upcoming.map((j) => (
              <li key={j.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                <span className="w-44 font-mono text-xs">{fmtDate(j.publish_at!)}</span>
                <PublishBadge status={j.status} /><span className="font-medium">{j.title}</span>
                {j.youtube_url && <a className="ml-auto text-xs text-brand-700 underline" href={j.youtube_url} target="_blank" rel="noreferrer">YouTube ↗</a>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
