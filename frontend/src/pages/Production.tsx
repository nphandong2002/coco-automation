import { useState } from "react";
import { api } from "../api/client";
import { JobRow, usePolling, useCapabilities, VideoList } from "../components/production";
import { Badge, ErrorBox, Loading, Stat, Tabs } from "../components/ui";
import { fmtDate, useApi } from "../lib/hooks";

type Tab = "queue" | "videos";

export default function Production() {
  const channels = useApi(api.channels);
  const [channelId, setChannelId] = useState<number | "">("");
  const [status, setStatus] = useState("");
  const [tab, setTab] = useState<Tab>("queue");
  const st = useApi(api.productionStatus);
  const jobs = useApi(() => api.jobs({ channel_id: channelId, status, limit: 100 }), [channelId, status]);
  const videos = useApi(() => api.videos({ channel_id: channelId }), [channelId]);
  const caps = useCapabilities();
  const active = (st.data?.queued ?? 0) + (st.data?.running ?? 0) > 0;
  usePolling(() => { void st.reload(); void jobs.reload(); }, active || tab === "queue", active ? 3000 : 10000);

  const worker = st.data?.workers.find((w) => w.online) ?? st.data?.workers[0];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="h1">Video Production</h1>
          <p className="muted">Hàng đợi render FFmpeg — tối đa 1 tác vụ nặng cùng lúc. Hàng đợi lưu trong PostgreSQL, không mất khi khởi động lại.</p>
        </div>
        <button className="btn-ghost" onClick={() => { void st.reload(); void jobs.reload(); void videos.reload(); }}>↻ Làm mới</button>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Render worker" value={worker ? (worker.online ? (worker.state === "rendering" ? "Đang render" : worker.state === "waiting_lock" ? "Chờ khóa" : "Sẵn sàng") : "Offline") : "Chưa chạy"}
          sub={worker ? `${worker.hostname} · PID ${worker.pid} · nhịp ${fmtDate(worker.heartbeat_at)}` : "Chạy: scripts/start.sh (khởi động cả worker)"} />
        <Stat label="Đang chạy / chờ" value={`${st.data?.running ?? "…"} / ${st.data?.queued ?? "…"}`} sub="Kênh tạm dừng: tác vụ chờ tới khi bật lại" />
        <Stat label="Thành công 24h" value={st.data?.succeeded_24h ?? "…"} />
        <Stat label="Thất bại 24h" value={st.data?.failed_24h ?? "…"} />
      </div>
      {st.data && !worker?.online && (
        <div className="card border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Render worker chưa chạy — tác vụ sẽ nằm trong hàng đợi. Khởi động bằng <code>scripts/start.sh</code> (hoặc <code>sudo systemctl start coco-worker</code>).
        </div>
      )}
      {caps.data && (
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge tone={caps.data.ffmpeg_path ? "green" : "slate"}>{caps.data.ffmpeg_version?.split(" Copyright")[0] ?? "Chưa có FFmpeg"}</Badge>
          <Badge tone={caps.data.drawtext ? "green" : "slate"}>drawtext {caps.data.drawtext ? "✔" : "✖"}</Badge>
          <Badge tone={caps.data.font_path ? "green" : "slate"}>font: {caps.data.font_path?.split(/[\\/]/).pop() ?? "không có"}</Badge>
          <Badge>x264 {caps.data.render_preset} · CRF {caps.data.render_crf} · {caps.data.render_threads} luồng</Badge>
          <Badge>vòng lặp {caps.data.loop_seconds}s</Badge>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ key: "queue", label: "Hàng đợi render" }, { key: "videos", label: "Video đã sản xuất" }]} />
        <select className="input ml-auto w-auto" value={channelId} onChange={(e) => setChannelId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Tất cả kênh</option>
          {channels.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {tab === "queue" && (
          <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Mọi trạng thái</option>
            {["queued", "running", "succeeded", "failed", "cancelled"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
      </div>

      {tab === "queue" && (jobs.loading && !jobs.data ? <Loading /> : jobs.error ? <ErrorBox error={jobs.error} onRetry={jobs.reload} /> : (
        <div className="card divide-y divide-brand-50">
          {jobs.data?.length ? jobs.data.map((j) => <JobRow key={j.id} j={j} onChanged={() => { void jobs.reload(); void st.reload(); }} />) :
            <div className="muted p-5">Chưa có tác vụ render. Mở một dự án trong Content Library → tab Render.</div>}
        </div>
      ))}
      {tab === "videos" && (videos.loading && !videos.data ? <Loading /> : videos.error ? <ErrorBox error={videos.error} onRetry={videos.reload} /> :
        <VideoList items={videos.data ?? []} onChanged={() => void videos.reload()} />)}
    </div>
  );
}
