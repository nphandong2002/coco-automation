import { useState } from "react";
import { api } from "../api/client";
import { usePolling } from "../components/production";
import { PublishRow } from "../components/publishing";
import { Empty, ErrorBox, Loading, Stat } from "../components/ui";
import { fmtDate, useApi } from "../lib/hooks";

export default function Publishing() {
  const channels = useApi(api.channels);
  const [channelId, setChannelId] = useState<number | "">("");
  const [status, setStatus] = useState("");
  const st = useApi(api.publishStatus);
  const jobs = useApi(() => api.publishJobs({ channel_id: channelId, status, limit: 100 }), [channelId, status]);
  const counts = st.data?.counts;
  const active = (counts?.queued ?? 0) + (counts?.running ?? 0) > 0;
  usePolling(() => { void st.reload(); void jobs.reload(); }, true, active ? 3000 : 10000);

  const worker = st.data?.workers.find((w) => w.online) ?? st.data?.workers[0];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="h1">Publishing</h1>
          <p className="muted">Hàng đợi upload YouTube — mỗi lần 1 video, tự thử lại khi lỗi mạng, tiếp tục upload dở sau khi khởi động lại. Video mặc định đăng ở chế độ Private.</p>
        </div>
        <button className="btn-ghost" onClick={() => { void st.reload(); void jobs.reload(); }}>↻ Làm mới</button>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Upload worker" value={worker ? (worker.online ? (worker.state === "uploading" ? "Đang upload" : "Sẵn sàng") : "Offline") : "Chưa chạy"}
          sub={worker ? `PID ${worker.pid} · nhịp ${fmtDate(worker.heartbeat_at)}` : "Chạy: scripts/start.sh (khởi động cả worker)"} />
        <Stat label="Đang upload / chờ" value={`${counts?.running ?? "…"} / ${counts?.queued ?? "…"}`} />
        <Stat label="Đã đăng" value={counts?.succeeded ?? "…"} />
        <Stat label="Thất bại" value={counts?.failed ?? "…"} />
      </div>
      {st.data && !worker?.online && (counts?.queued ?? 0) > 0 && (
        <div className="card border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Upload worker không chạy nên các tác vụ đang chờ chưa được xử lý. Khởi động bằng <code>scripts/start.sh</code> hoặc <code>python -m app.worker --kind publish</code>.
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <select className="input w-auto" value={channelId} onChange={(e) => setChannelId(e.target.value ? +e.target.value : "")}>
          <option value="">Tất cả kênh</option>
          {channels.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Mọi trạng thái</option>
          <option value="queued">Đang chờ</option><option value="running">Đang upload</option>
          <option value="succeeded">Đã đăng</option><option value="failed">Thất bại</option><option value="cancelled">Đã hủy</option>
        </select>
      </div>

      {jobs.loading && !jobs.data ? <Loading /> : jobs.error ? <ErrorBox error={jobs.error} onRetry={jobs.reload} /> :
        !jobs.data?.length ? <Empty title="Chưa có tác vụ đăng nào">Vào Video Production hoặc tab Video của kênh, chọn video đã render và bấm "Đăng YouTube".</Empty> : (
          <div className="card divide-y divide-brand-50">
            {jobs.data.map((j) => <PublishRow key={j.id} j={j} onChanged={() => { void jobs.reload(); void st.reload(); }} />)}
          </div>
        )}
    </div>
  );
}
