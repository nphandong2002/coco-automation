import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ContentType, Idea } from "../api/types";
import { CONTENT_TYPES, fmtMinutes, ProjectTable, usePolling } from "../components/production";
import { Badge, Empty, ErrorBox, Field, Loading, Modal } from "../components/ui";
import { useAction, useApi } from "../lib/hooks";

export default function ContentLibrary() {
  const channels = useApi(api.channels);
  const [channelId, setChannelId] = useState<number | "">("");
  const [status, setStatus] = useState("");
  const [ctype, setCtype] = useState("");
  const [q, setQ] = useState("");
  const list = useApi(() => api.contentAll({ channel_id: channelId, status, content_type: ctype, q }), [channelId, status, ctype, q]);
  const [creating, setCreating] = useState(false);
  const busyRender = (list.data ?? []).some((p) => p.status === "queued" || p.status === "rendering");
  usePolling(() => void list.reload(), busyRender, 4000);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="h1">Content Library</h1>
          <p className="muted">Kho nội dung riêng của từng kênh. Nội dung chỉ khác tiêu đề sẽ bị chặn (chống trùng lặp hàng loạt).</p>
        </div>
        <button className="btn-primary" disabled={!channels.data?.length} onClick={() => setCreating(true)}>+ Dự án mới</button>
      </div>

      <div className="card flex flex-wrap gap-3 p-4">
        <select className="input w-auto" value={channelId} onChange={(e) => setChannelId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Tất cả kênh</option>
          {channels.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-auto" value={ctype} onChange={(e) => setCtype(e.target.value)}>
          <option value="">Mọi loại nội dung</option>
          {Object.entries(CONTENT_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Mọi trạng thái</option>
          {["draft", "ready", "queued", "rendering", "rendered", "failed"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input className="input w-60" placeholder="Tìm tiêu đề, bối cảnh…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {list.loading && !list.data ? <Loading /> : list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : <ProjectTable items={list.data ?? []} />}

      {channels.data && channels.data.length > 0 && <IdeasPanel channels={channels.data} initial={channelId || channels.data[0].id} onCreated={() => void list.reload()} />}
      {channels.data?.length === 0 && <Empty title="Chưa có kênh">Tạo kênh trước khi tạo nội dung.</Empty>}

      {creating && channels.data && <NewProjectModal channels={channels.data} initialChannel={channelId || channels.data[0].id} onClose={() => setCreating(false)} />}
    </div>
  );
}

function IdeasPanel({ channels, initial, onCreated }: { channels: { id: number; name: string }[]; initial: number; onCreated: () => void }) {
  const [cid, setCid] = useState<number>(initial);
  useEffect(() => setCid(initial), [initial]);
  const ideas = useApi(() => api.ideas(cid, "new"), [cid]);
  const [ctype, setCtype] = useState("");
  const { busy, run } = useAction();
  const nav = useNavigate();
  return (
    <div className="card">
      <div className="flex flex-wrap items-center gap-3 border-b border-brand-50 px-5 py-3">
        <div className="font-semibold">💡 Ý tưởng video</div>
        <select className="input w-auto" value={cid} onChange={(e) => setCid(Number(e.target.value))}>
          {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-auto" value={ctype} onChange={(e) => setCtype(e.target.value)}>
          <option value="">Theo chủ đề kênh</option>
          {Object.entries(CONTENT_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button className="btn-primary ml-auto" disabled={busy} onClick={() => run(() => api.generateIdeas(cid, 6, ctype || undefined), "Đã sinh ý tưởng mới").then(() => ideas.reload())}>✦ Sinh 6 ý tưởng</button>
      </div>
      <div className="px-5 py-2 text-xs text-ink-500">Ý tưởng được ghép từ chủ đề, âm thanh và bối cảnh nhân vật của kênh. Mỗi tổ hợp (loại, bối cảnh, thời điểm, thời tiết, âm thanh, thời lượng) chỉ được đề xuất một lần.</div>
      {ideas.loading && !ideas.data ? <Loading /> : ideas.error ? <div className="p-4"><ErrorBox error={ideas.error} /></div> : !ideas.data?.length ? (
        <div className="muted px-5 pb-5">Chưa có ý tưởng mới cho kênh này.</div>
      ) : (
        <div className="divide-y divide-brand-50">
          {ideas.data.map((i: Idea) => (
            <div key={i.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
              <div className="min-w-0 flex-1">
                <div className="font-medium">{i.title}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  <Badge tone="brand">{CONTENT_TYPES[i.content_type]}</Badge>
                  <Badge>{fmtMinutes(i.attributes.duration_minutes)}</Badge>
                  {(i.attributes.sounds as string[]).map((s) => <Badge key={s} tone="blue">{s}</Badge>)}
                  {(i.attributes.effects as string[]).filter((e) => e !== "vignette").map((e) => <Badge key={e} tone="green">{e}</Badge>)}
                </div>
              </div>
              <button className="btn-ghost" disabled={busy} onClick={() => run(() => api.rejectIdea(cid, i.id)).then(() => ideas.reload())}>Bỏ qua</button>
              <button className="btn-primary" disabled={busy} onClick={async () => {
                const p = await run(() => api.acceptIdea(cid, i.id), "Đã tạo dự án từ ý tưởng");
                if (p) { onCreated(); nav(`/channels/${p.channel_id}/content/${p.id}`); }
              }}>Tạo dự án</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function NewProjectModal({ channels, initialChannel, onClose }: { channels: { id: number; name: string }[]; initialChannel: number; onClose: () => void }) {
  const [cid, setCid] = useState<number>(initialChannel);
  const templates = useApi(() => api.templates(cid), [cid]);
  const characters = useApi(() => api.characters(cid), [cid]);
  const [tpl, setTpl] = useState<number | "">("");
  const [title, setTitle] = useState("");
  const [ctype, setCtype] = useState<ContentType>("study_with_me");
  const [charId, setCharId] = useState<number | "">("");
  const { busy, run } = useAction();
  const nav = useNavigate();

  useEffect(() => {
    const primary = characters.data?.find((c) => c.role === "primary" && !c.archived);
    setCharId(primary ? primary.id : "");
  }, [characters.data]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const p = await run(() => api.createContent(cid, { title, content_type: ctype, template_id: tpl || null, character_id: charId || null }), "Đã tạo dự án");
    if (p) nav(`/channels/${cid}/content/${p.id}`);
  };
  return (
    <Modal title="Dự án nội dung mới" onClose={onClose}>
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Kênh sở hữu">
          <select className="input" value={cid} onChange={(e) => { setCid(Number(e.target.value)); setTpl(""); }}>
            {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Template" hint="Cấu hình sẵn: thời lượng, hiệu ứng, âm thanh, Pomodoro…">
          <select className="input" value={tpl} onChange={(e) => {
            const id = e.target.value ? Number(e.target.value) : "";
            setTpl(id);
            const t = templates.data?.find((x) => x.id === id);
            if (t) setCtype(t.content_type);
          }}>
            <option value="">Không dùng template</option>
            {templates.data?.map((t) => <option key={t.id} value={t.id}>{t.name}{t.channel_id ? " (kênh)" : ""}</option>)}
          </select>
        </Field>
        <Field label="Loại nội dung">
          <select className="input" value={ctype} onChange={(e) => setCtype(e.target.value as ContentType)}>
            {Object.entries(CONTENT_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Tên dự án"><input className="input" required minLength={2} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="VD: Học cùng Momo — đêm mưa gác mái" /></Field>
        <Field label="Nhân vật" hint="Chỉ nhân vật kênh sở hữu hoặc được cấp quyền. Phiên bản hiện tại sẽ được ghim cho dự án.">
          <select className="input" value={charId} onChange={(e) => setCharId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Không dùng nhân vật</option>
            {characters.data?.filter((c) => !c.archived).map((c) => <option key={c.id} value={c.id}>{c.name}{c.role === "primary" ? " (chính)" : ""}{c.is_owner ? "" : " — được cấp quyền"}</option>)}
          </select>
        </Field>
        <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={onClose}>Hủy</button>
          <button className="btn-primary" disabled={busy}>Tạo</button></div>
      </form>
    </Modal>
  );
}
