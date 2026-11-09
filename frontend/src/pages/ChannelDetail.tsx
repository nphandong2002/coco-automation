import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Channel, ChannelSummary } from "../api/types";
import ChannelForm, { channelToInput, WEEKDAYS } from "../components/ChannelForm";
import { CharacterCard, CreateCharacterForm } from "../components/CharacterForms";
import { ColorChips, Empty, ErrorBox, Field, ImageUpload, Loading, Modal, Stat, StatusBadge, Tabs } from "../components/ui";
import { fmtDate, useAction, useApi } from "../lib/hooks";
import { ProjectTable, VideoList } from "../components/production";
import { YoutubePanel } from "../components/publishing";
import { NewProjectModal } from "./ContentLibrary";

type Tab = "overview" | "brand" | "characters" | "content" | "videos" | "youtube" | "activity";

export default function ChannelDetail() {
  const id = Number(useParams().channelId);
  const nav = useNavigate();
  const { data: ch, setData, error, loading, reload } = useApi(() => api.channel(id), [id]);
  const summary = useApi(() => api.channelSummary(id), [id]);
  const [tab, setTab] = useState<Tab>("overview");
  const [modal, setModal] = useState<"clone" | "delete" | null>(null);
  const { busy, run } = useAction();

  if (loading && !ch) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!ch) return null;

  const update = (c?: Channel) => { if (c) { setData(c); void summary.reload(); } };

  return (
    <div className="space-y-6">
      <div className="card overflow-hidden">
        <div className="h-36 bg-gradient-to-r from-brand-100 to-brand-50">
          {ch.banner_url && <img src={ch.banner_url} alt="" className="h-full w-full object-cover" />}
        </div>
        <div className="flex flex-wrap items-end gap-4 px-6 pb-5">
          <div className="-mt-10 h-20 w-20 overflow-hidden rounded-full border-4 border-white bg-brand-100">
            {ch.avatar_url ? <img src={ch.avatar_url} alt="" className="h-full w-full object-cover" /> :
              <div className="flex h-full items-center justify-center text-2xl font-bold text-brand-700">{ch.name[0]}</div>}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2"><h1 className="h1">{ch.name}</h1><StatusBadge status={ch.status} /></div>
            <div className="font-mono text-xs text-ink-500">{ch.code} · #{ch.id}{ch.cloned_from_id ? ` · sao chép từ kênh #${ch.cloned_from_id}` : ""}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            {ch.enabled
              ? <button className="btn-ghost" disabled={busy} onClick={() => run(() => api.pauseChannel(id), "Đã tạm dừng kênh").then(update)}>⏸ Tạm dừng</button>
              : <button className="btn-primary" disabled={busy} onClick={() => run(() => api.enableChannel(id), "Đã bật kênh").then(update)}>▶ Bật kênh</button>}
            <button className="btn-ghost" onClick={() => setModal("clone")}>⧉ Sao chép</button>
            <button className="btn-ghost text-red-700" onClick={() => setModal("delete")}>Xóa</button>
          </div>
        </div>
        {ch.last_error && (
          <div className="flex items-center justify-between border-t border-red-100 bg-red-50 px-6 py-3 text-sm text-red-800">
            <span>Lỗi: {ch.last_error} {ch.last_error_at && `(${fmtDate(ch.last_error_at)})`}</span>
            <button className="btn-ghost" onClick={() => run(() => api.clearChannelError(id), "Đã xóa lỗi").then(update)}>Đánh dấu đã xử lý</button>
          </div>
        )}
      </div>

      <Tabs<Tab> value={tab} onChange={setTab} tabs={[
        { key: "overview", label: "Tổng quan" }, { key: "brand", label: "Thương hiệu & lịch đăng" },
        { key: "characters", label: "Nhân vật" }, { key: "content", label: "Nội dung" }, { key: "videos", label: "Video" },
        { key: "youtube", label: "YouTube" }, { key: "activity", label: "Hoạt động" },
      ]} />

      {tab === "overview" && <OverviewTab ch={ch} summary={summary.data} />}
      {tab === "brand" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4">
            <div className="card space-y-4 p-5">
              <ImageUpload label="Avatar" url={ch.avatar_url} busy={busy}
                onFile={(f) => run(() => api.uploadChannelImage(id, "avatar", f), "Đã cập nhật avatar").then(update)} />
              <ImageUpload label="Banner" url={ch.banner_url} busy={busy} aspect="aspect-[16/5]"
                onFile={(f) => run(() => api.uploadChannelImage(id, "banner", f), "Đã cập nhật banner").then(update)} />
            </div>
          </div>
          <div className="card p-5 lg:col-span-2">
            <ChannelForm key={ch.updated_at} initial={channelToInput(ch)} busy={busy}
              onSubmit={(v) => run(() => api.updateChannel(id, v), "Đã lưu").then(update)} />
          </div>
        </div>
      )}
      {tab === "characters" && <CharactersTab channelId={id} />}
      {tab === "content" && <ContentTab channelId={id} />}
      {tab === "videos" && <VideosTab channelId={id} />}
      {tab === "youtube" && <YoutubePanel channelId={id} onChanged={reload} />}
      {tab === "activity" && <ActivityTab channelId={id} />}

      {modal === "clone" && <CloneModal ch={ch} onClose={() => setModal(null)} onDone={(c) => nav(`/channels/${c.id}`)} />}
      {modal === "delete" && <DeleteModal ch={ch} onClose={() => setModal(null)} onDone={() => nav("/channels")} />}
    </div>
  );
}

function OverviewTab({ ch, summary }: { ch: Channel; summary: ChannelSummary | null }) {
  const slots = ch.publish_schedule.slots ?? [];
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Nhân vật" value={summary ? summary.characters_owned + summary.characters_granted : "…"}
          sub={summary ? `${summary.characters_owned} sở hữu · ${summary.characters_granted} được cấp quyền` : undefined} />
        <Stat label="Nội dung" value={summary?.content_projects ?? "…"} sub="Dự án nội dung của kênh" />
        <Stat label="Video" value={summary?.videos ?? "…"} sub={summary ? `${summary.render_jobs_active} đang render/chờ` : undefined} />
        <Stat label="Analytics" value={summary ? (summary.analytics_days_synced ? `${summary.analytics_days_synced} ngày` : "Chưa đồng bộ") : "…"} sub="YouTube Analytics — Phase 4" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card space-y-3 p-5">
          <div className="font-semibold">Thương hiệu</div>
          <p className="text-sm">{ch.description || <span className="text-ink-300">Chưa có mô tả</span>}</p>
          <Info label="Ngôn ngữ / Quốc gia" value={`${ch.language} / ${ch.target_country}`} />
          <Info label="Chủ đề" value={ch.topics.join(", ") || "—"} />
          <Info label="Phong cách hình ảnh" value={[ch.visual_style.theme, ch.visual_style.mood].filter(Boolean).join(" · ") || "—"} />
          {(ch.visual_style.palette?.length ?? 0) > 0 && <ColorChips colors={ch.visual_style.palette!} />}
          <Info label="Âm thanh" value={[...(ch.audio_style.ambience ?? []), ch.audio_style.music].filter(Boolean).join(", ") || "—"} />
        </div>
        <div className="card space-y-3 p-5">
          <div className="font-semibold">Lịch đăng ({ch.publish_schedule.timezone ?? "—"})</div>
          {slots.length === 0 ? <p className="muted">Chưa thiết lập khung giờ đăng.</p> : (
            <ul className="space-y-1 text-sm">{slots.map((s, i) => <li key={i}>{WEEKDAYS[s.weekday]} — {s.time}</li>)}</ul>
          )}
          <p className="text-xs text-ink-500">Scheduler sẽ dùng lịch này để tạo tác vụ đăng ở Phase 3.</p>
        </div>
      </div>
    </div>
  );
}

const Info = ({ label, value }: { label: string; value: string }) => (
  <div className="text-sm"><span className="text-ink-500">{label}: </span>{value}</div>
);

function CharactersTab({ channelId }: { channelId: number }) {
  const { data, error, loading, reload } = useApi(() => api.characters(channelId), [channelId]);
  const [creating, setCreating] = useState(false);
  const { busy, run } = useAction();
  const nav = useNavigate();
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><button className="btn-primary" onClick={() => setCreating(true)}>+ Tạo nhân vật</button></div>
      {loading && !data ? <Loading /> : error ? <ErrorBox error={error} onRetry={reload} /> : !data?.length ? (
        <Empty title="Kênh chưa có nhân vật">Tạo nhân vật riêng cho kênh, hoặc nhờ kênh khác cấp quyền dùng nhân vật của họ.</Empty>
      ) : <div className="grid gap-4 md:grid-cols-2">{data.map((c) => <CharacterCard key={c.id} c={c} />)}</div>}
      {creating && (
        <Modal title="Tạo nhân vật" wide onClose={() => setCreating(false)}>
          <CreateCharacterForm busy={busy} onCancel={() => setCreating(false)} onSubmit={async (v) => {
            const c = await run(() => api.createCharacter(channelId, v), "Đã tạo nhân vật");
            if (c) nav(`/channels/${channelId}/characters/${c.id}`);
          }} />
        </Modal>
      )}
    </div>
  );
}

function ActivityTab({ channelId }: { channelId: number }) {
  const { data, error, loading, reload } = useApi(() => api.channelActivity(channelId), [channelId]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  return (
    <div className="card divide-y divide-brand-50">
      {data?.map((a) => (
        <div key={a.id} className="flex justify-between gap-4 px-5 py-3 text-sm">
          <span>{a.message}</span><span className="whitespace-nowrap text-xs text-ink-500">{fmtDate(a.created_at)}</span>
        </div>
      ))}
      {data?.length === 0 && <div className="muted p-5">Chưa có hoạt động.</div>}
    </div>
  );
}

function CloneModal({ ch, onClose, onDone }: { ch: Channel; onClose: () => void; onDone: (c: Channel) => void }) {
  const [name, setName] = useState(`${ch.name} (copy)`);
  const [code, setCode] = useState(`${ch.code}-copy`.slice(0, 64));
  const [inc, setInc] = useState(true);
  const { busy, run } = useAction();
  return (
    <Modal title={`Sao chép cấu hình "${ch.name}"`} onClose={onClose}>
      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault();
        const c = await run(() => api.cloneChannel(ch.id, { name, code, include_characters: inc }), "Đã tạo kênh mới");
        if (c) onDone(c);
      }}>
        <Field label="Tên kênh mới"><input className="input" required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Mã kênh mới"><input className="input font-mono" required value={code} onChange={(e) => setCode(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={inc} onChange={(e) => setInc(e.target.checked)} />
          Sao chép cả nhân vật do kênh sở hữu (tạo bản sao độc lập)</label>
        <p className="muted">Không sao chép: kết nối YouTube, video, thống kê, và nhân vật được kênh khác cấp quyền.</p>
        <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={onClose}>Hủy</button>
          <button className="btn-primary" disabled={busy}>Sao chép</button></div>
      </form>
    </Modal>
  );
}

function DeleteModal({ ch, onClose, onDone }: { ch: Channel; onClose: () => void; onDone: () => void }) {
  const [confirm, setConfirm] = useState("");
  const { busy, run } = useAction();
  return (
    <Modal title="Xóa kênh" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm">Thao tác này xóa vĩnh viễn kênh <b>{ch.name}</b>, toàn bộ nhân vật, nội dung, video và file của kênh. Không thể hoàn tác.</p>
        <Field label={`Nhập mã kênh "${ch.code}" để xác nhận`}><input className="input font-mono" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
        <div className="flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>Hủy</button>
          <button className="btn-danger" disabled={busy || confirm !== ch.code}
            onClick={async () => { const ok = await run(() => api.deleteChannel(ch.id, confirm).then(() => true), "Đã xóa kênh"); if (ok) onDone(); }}>Xóa vĩnh viễn</button>
        </div>
      </div>
    </Modal>
  );
}


function ContentTab({ channelId }: { channelId: number }) {
  const { data, error, loading, reload } = useApi(() => api.channelContent(channelId), [channelId]);
  const ch = useApi(() => api.channel(channelId), [channelId]);
  const [creating, setCreating] = useState(false);
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><button className="btn-primary" onClick={() => setCreating(true)}>+ Dự án nội dung</button></div>
      {loading && !data ? <Loading /> : error ? <ErrorBox error={error} onRetry={reload} /> : <ProjectTable items={data ?? []} showChannel={false} />}
      {creating && ch.data && <NewProjectModal channels={[ch.data]} initialChannel={channelId} onClose={() => setCreating(false)} />}
    </div>
  );
}

function VideosTab({ channelId }: { channelId: number }) {
  const { data, error, loading, reload } = useApi(() => api.videos({ channel_id: channelId }), [channelId]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  return <VideoList items={data ?? []} onChanged={() => void reload()} />;
}
