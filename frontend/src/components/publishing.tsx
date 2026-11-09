import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { JobStatus, PrivacyStatus, PublishJob, Video } from "../api/types";
import { fmtDate, splitList, joinList, toast, useAction, useApi } from "../lib/hooks";
import { fmtBytes, ProgressBar } from "./production";
import { Badge, ErrorBox, Field, Loading, Modal } from "./ui";

const STATUS: Record<JobStatus, { label: string; cls: string }> = {
  queued: { label: "Đang chờ", cls: "bg-slate-100 text-slate-700" },
  running: { label: "Đang upload", cls: "bg-violet-100 text-violet-700" },
  succeeded: { label: "Đã đăng", cls: "bg-emerald-100 text-emerald-700" },
  failed: { label: "Thất bại", cls: "bg-red-100 text-red-700" },
  cancelled: { label: "Đã hủy", cls: "bg-amber-100 text-amber-700" },
};
export const PRIVACY: Record<PrivacyStatus, string> = { private: "Riêng tư (Private)", unlisted: "Không công khai (Unlisted)", public: "Công khai (Public)" };
const EVENTS: Record<string, string> = {
  created: "Tạo tác vụ", started: "Bắt đầu upload", session_started: "Mở phiên upload", uploaded: "Upload xong",
  thumbnail_done: "Thumbnail", playlist_done: "Playlist", succeeded: "Hoàn tất", retry_scheduled: "Lên lịch thử lại",
  quota: "Hết quota API", auth_error: "Lỗi xác thực", failed: "Thất bại", cancelled: "Đã hủy", retry: "Thử lại",
  recovered: "Khôi phục sau khi dừng", paused: "Tạm dừng",
};

export function PublishBadge({ status }: { status: JobStatus }) {
  const s = STATUS[status];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>;
}

/** Local datetime-input <-> ISO helpers (the browser's timezone; backend stores UTC). */
const toLocalInput = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

// ------------------------------------------------------------------ YouTube connection panel
export function YoutubePanel({ channelId, onChanged }: { channelId: number; onChanged: () => void }) {
  const st = useApi(() => api.youtubeStatus(channelId), [channelId]);
  const { busy, run } = useAction();
  const [params, setParams] = useSearchParams();

  // result of the OAuth round-trip (the callback redirects back here)
  useEffect(() => {
    const r = params.get("youtube");
    if (!r) return;
    if (r === "connected") toast("Đã kết nối YouTube", "ok");
    else toast(params.get("message") ?? "Kết nối YouTube thất bại", "error");
    const next = new URLSearchParams(params);
    next.delete("youtube"); next.delete("message");
    setParams(next, { replace: true });
    void st.reload(); onChanged();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (st.loading && !st.data) return <Loading />;
  if (st.error) return <ErrorBox error={st.error} onRetry={st.reload} />;
  const s = st.data!;
  const connect = async () => {
    const r = await run(() => api.youtubeConnect(channelId));
    if (r) window.location.href = r.auth_url;
  };
  return (
    <div className="card space-y-4 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-semibold">Trạng thái kết nối:</span>
        {s.connected ? <Badge tone="green">Đã kết nối</Badge>
          : s.status === "revoked" || s.status === "expired" ? <Badge tone="brand">Cần kết nối lại</Badge>
            : <Badge>Chưa kết nối</Badge>}
        {s.youtube_channel_title && <span className="text-sm">Kênh YouTube: <b>{s.youtube_channel_title}</b></span>}
      </div>
      {s.last_error && <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">{s.last_error}</div>}
      {!s.configured && (
        <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Chưa cấu hình Google OAuth. Đặt <code>GOOGLE_CLIENT_ID</code> và <code>GOOGLE_CLIENT_SECRET</code> trong <code>.env</code>, rồi khởi động lại
          (xem <code>docs/YOUTUBE_SETUP.md</code>).
        </div>
      )}
      {s.connected && (
        <div className="grid gap-1 text-xs text-ink-500 sm:grid-cols-2">
          <div>ID kênh YouTube: <span className="font-mono">{s.youtube_channel_id}</span></div>
          <div>Token làm mới lần cuối: {s.last_refresh_at ? fmtDate(s.last_refresh_at) : "—"}</div>
          <div className="sm:col-span-2">Quyền đã cấp: {s.scopes.map((x) => x.split("/").pop()).join(", ")}</div>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" disabled={busy || !s.configured} onClick={connect}>{s.connected ? "Kết nối lại / đổi tài khoản" : "Kết nối YouTube"}</button>
        {s.status !== "disconnected" && (
          <button className="btn-ghost text-red-700" disabled={busy} onClick={async () => {
            if (!confirm("Ngắt kết nối YouTube của kênh này? Token sẽ bị thu hồi và xóa. Các video đã đăng không bị ảnh hưởng.")) return;
            await run(() => api.youtubeDisconnect(channelId), "Đã ngắt kết nối");
            void st.reload(); onChanged();
          }}>Ngắt kết nối</button>
        )}
      </div>
      <p className="muted">
        Mỗi kênh dùng một tài khoản/kênh YouTube riêng; token được mã hóa (Fernet) trong cơ sở dữ liệu và không bao giờ hiển thị.
        Bạn đăng nhập trực tiếp trên trang của Google — hệ thống không thấy mật khẩu hay mã 2FA.
      </p>
    </div>
  );
}

// ------------------------------------------------------------------ publish dialog
export function PublishModal({ video, onClose, onDone }: { video: Video; onClose: () => void; onDone: () => void }) {
  const ch = useApi(() => api.channel(video.channel_id), [video.channel_id]);
  const project = useApi(async () => video.content_project_id ? api.content(video.channel_id, video.content_project_id) : null, [video.id]);
  const connected = ch.data?.youtube_connected;
  const playlists = useApi(async () => connected ? api.playlists(video.channel_id).catch(() => []) : [], [connected]);
  const slots = useApi(() => api.slots(video.channel_id, 3).catch(() => ({ timezone: "UTC", slots: [] as string[] })), [video.channel_id]);
  const { busy, run } = useAction();

  const [title, setTitle] = useState<string | null>(null);
  const [desc, setDesc] = useState<string | null>(null);
  const [tags, setTags] = useState<string | null>(null);
  const [privacy, setPrivacy] = useState<PrivacyStatus>("private");
  const [when, setWhen] = useState<"now" | "slot" | "custom">("now");
  const [custom, setCustom] = useState(toLocalInput(new Date(Date.now() + 24 * 3600 * 1000)));
  const [playlist, setPlaylist] = useState("");
  const [category, setCategory] = useState("10");

  const p = project.data;
  const t = title ?? (p?.youtube_title || video.title);
  const d = desc ?? (p?.youtube_description ?? "");
  const tg = tags ?? joinList(p?.youtube_tags);
  const scheduled = when !== "now";

  const submit = async () => {
    const body = {
      video_id: video.id, title: t, description: d, tags: splitList(tg), privacy, category_id: category,
      playlist_id: playlist || null,
      ...(when === "slot" ? { use_next_slot: true } : {}),
      ...(when === "custom" ? { publish_at: new Date(custom).toISOString() } : {}),
    };
    const r = await run(() => api.createPublish(video.channel_id, body), "Đã đưa vào hàng đợi đăng");
    if (r) { onDone(); onClose(); }
  };

  return (
    <Modal title={`Đăng lên YouTube — ${video.title}`} wide onClose={onClose}>
      {ch.loading ? <Loading /> : !connected ? (
        <div className="rounded bg-amber-50 p-4 text-sm text-amber-800">Kênh <b>{video.channel_name}</b> chưa kết nối YouTube. Vào chi tiết kênh → tab YouTube để kết nối.</div>
      ) : (
        <div className="space-y-4">
          <Field label={`Tiêu đề (${t.length}/100)`}><input className="input" maxLength={100} value={t} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="Mô tả"><textarea className="input h-28" maxLength={5000} value={d} onChange={(e) => setDesc(e.target.value)} /></Field>
          <Field label="Tags" hint="Cách nhau bằng dấu phẩy (tối đa 500 ký tự)"><input className="input" value={tg} onChange={(e) => setTags(e.target.value)} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Quyền riêng tư" hint={scheduled ? "Video lên lịch được đăng Private rồi tự công khai đúng giờ" : "Mặc định Private để kiểm tra trước khi công khai"}>
              <select className="input" value={scheduled ? "private" : privacy} disabled={scheduled} onChange={(e) => setPrivacy(e.target.value as PrivacyStatus)}>
                {(Object.keys(PRIVACY) as PrivacyStatus[]).map((k) => <option key={k} value={k}>{PRIVACY[k]}</option>)}
              </select>
            </Field>
            <Field label="Playlist">
              <select className="input" value={playlist} onChange={(e) => setPlaylist(e.target.value)}>
                <option value="">— Không thêm —</option>
                {(playlists.data ?? []).map((pl) => <option key={pl.id} value={pl.id}>{pl.title}</option>)}
              </select>
            </Field>
            <Field label="Danh mục">
              <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="10">Music</option><option value="22">People &amp; Blogs</option><option value="27">Education</option><option value="24">Entertainment</option>
              </select>
            </Field>
            <Field label="Thời điểm công khai">
              <select className="input" value={when} onChange={(e) => setWhen(e.target.value as typeof when)}>
                <option value="now">Không hẹn giờ (theo quyền riêng tư)</option>
                <option value="slot" disabled={!slots.data?.slots.length}>Slot trống kế tiếp của kênh{slots.data?.slots[0] ? ` — ${fmtDate(slots.data.slots[0])}` : " (kênh chưa có lịch đăng)"}</option>
                <option value="custom">Chọn giờ cụ thể…</option>
              </select>
            </Field>
          </div>
          {when === "custom" && <Field label="Công khai lúc (giờ trình duyệt)"><input type="datetime-local" className="input" value={custom} onChange={(e) => setCustom(e.target.value)} /></Field>}
          <div className="flex items-center justify-between pt-2">
            <span className="text-xs text-ink-500">Dung lượng {fmtBytes(video.size_bytes)} — upload chạy nền, tiếp tục được nếu bị ngắt.</span>
            <button className="btn-primary" disabled={busy || !t.trim()} onClick={submit}>Đưa vào hàng đợi</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ------------------------------------------------------------------ queue row
export function PublishRow({ j, onChanged }: { j: PublishJob; onChanged: () => void }) {
  const { busy, run } = useAction();
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono text-xs text-ink-500">#{j.id}</span>
        <PublishBadge status={j.status} />
        <Badge tone={j.privacy_status === "public" ? "green" : "slate"}>{j.publish_at ? `Hẹn công khai ${fmtDate(j.publish_at)}` : PRIVACY[j.privacy_status]}</Badge>
        <span className="font-medium">{j.title}</span>
        <span className="text-xs text-ink-500">· {j.channel_name}</span>
        <span className="ml-auto text-xs text-ink-500">{fmtDate(j.created_at)}</span>
      </div>
      {j.status === "running" && j.progress != null && (
        <div className="flex items-center gap-3">
          <ProgressBar value={j.progress} active />
          <span className="whitespace-nowrap text-xs text-ink-500">{Math.round(j.progress * 100)}% · {fmtBytes(j.bytes_uploaded)} / {fmtBytes(j.size_bytes ?? 0)}</span>
        </div>
      )}
      {j.status === "queued" && (
        <div className="text-xs text-ink-500">
          {j.next_attempt_at ? `Chạy sau ${fmtDate(j.next_attempt_at)}` : "Chờ worker"}{j.attempts ? ` · lần thử ${j.attempts}/${j.max_attempts}` : ""}
        </div>
      )}
      {j.last_error && <div className={`rounded px-3 py-2 text-xs ${j.status === "failed" ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-800"}`}>{j.last_error.slice(0, 500)}</div>}
      <div className="flex flex-wrap gap-2">
        {j.youtube_url && <a className="btn-ghost text-xs" href={j.youtube_url} target="_blank" rel="noreferrer">Mở trên YouTube ↗</a>}
        {(j.status === "queued" || j.status === "running") && <button className="btn-ghost text-xs" disabled={busy} onClick={() => run(() => api.cancelPublish(j.id), "Đã hủy").then(onChanged)}>Hủy</button>}
        {(j.status === "failed" || j.status === "cancelled") && <button className="btn-ghost text-xs" disabled={busy} onClick={() => run(() => api.retryPublish(j.id), "Đã đưa lại vào hàng đợi").then(onChanged)}>↻ Thử lại</button>}
        <button className="btn-ghost text-xs" onClick={() => setOpen(!open)}>{open ? "Ẩn lịch sử" : "Lịch sử"}</button>
      </div>
      {open && (
        <ol className="space-y-0.5 rounded bg-slate-50 p-3 text-xs">
          {j.history.map((h, i) => (
            <li key={i}><span className="text-ink-500">{fmtDate(h.at)}</span> · <b>{EVENTS[h.event] ?? h.event}</b>{h.detail ? ` — ${h.detail}` : ""}</li>
          ))}
        </ol>
      )}
    </div>
  );
}
