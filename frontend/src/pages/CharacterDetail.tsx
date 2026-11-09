import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Character, CharacterRole } from "../api/types";
import { draftFromVersion, draftToFields, VersionFieldsEditor } from "../components/CharacterForms";
import { Badge, ColorChips, ErrorBox, Field, ImageUpload, Loading, Modal, Tabs } from "../components/ui";
import { fmtDate, useAction, useApi } from "../lib/hooks";

type Tab = "identity" | "images" | "versions" | "sharing";

export default function CharacterDetail() {
  const p = useParams();
  const cid = Number(p.channelId), id = Number(p.characterId);
  const nav = useNavigate();
  const { data: c, setData, error, loading, reload } = useApi(() => api.character(cid, id), [cid, id]);
  const [tab, setTab] = useState<Tab>("identity");
  const [editing, setEditing] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const { busy, run } = useAction();

  if (loading && !c) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!c) return null;
  const v = c.current_version;
  const set = (x?: Character) => { if (x) setData(x); };
  const ro = !c.is_owner;

  return (
    <div className="space-y-6">
      <div className="text-sm text-ink-500"><Link className="hover:underline" to={`/channels/${cid}`}>← Kênh</Link> / Nhân vật</div>
      <div className="card flex flex-wrap items-center gap-5 p-5">
        <div className="h-24 w-24 overflow-hidden rounded-2xl bg-brand-100">
          {v?.avatar_url ? <img src={v.avatar_url} alt="" className="h-full w-full object-cover" /> :
            <div className="flex h-full items-center justify-center text-3xl font-bold text-brand-700">{c.name[0]}</div>}
        </div>
        <div className="flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="h1">{c.name}</h1>
            <Badge tone={c.role === "primary" ? "brand" : "slate"}>{c.role === "primary" ? "Nhân vật chính" : "Nhân vật phụ"}</Badge>
            {ro && <Badge tone="blue">Được cấp quyền từ {c.owner_channel_name}</Badge>}
            {c.archived && <Badge>Lưu trữ</Badge>}
          </div>
          <div className="text-sm text-ink-500">{c.species || "—"} · Phiên bản hiện tại v{v?.version_no} / {c.version_count} · Kênh sở hữu: {c.owner_channel_name}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <select className="input w-40" value={c.role} disabled={busy}
            onChange={(e) => run(() => api.setRole(cid, id, e.target.value as CharacterRole), "Đã đổi vai trò").then(set)}>
            <option value="primary">Nhân vật chính</option><option value="secondary">Nhân vật phụ</option>
          </select>
          {!ro && <>
            <button className="btn-ghost" onClick={() => setRenaming(true)}>Sửa tên</button>
            <button className="btn-ghost" disabled={busy} onClick={() => run(() => api.updateCharacter(cid, id, { archived: !c.archived }), c.archived ? "Đã khôi phục" : "Đã lưu trữ").then(set)}>
              {c.archived ? "Khôi phục" : "Lưu trữ"}</button>
            <button className="btn-ghost text-red-700" disabled={busy} onClick={async () => {
              if (!window.confirm(`Xóa nhân vật "${c.name}" và toàn bộ phiên bản?`)) return;
              const ok = await run(() => api.deleteCharacter(cid, id).then(() => true), "Đã xóa nhân vật");
              if (ok) nav(`/channels/${cid}`);
            }}>Xóa</button>
          </>}
        </div>
      </div>

      {ro && <div className="card border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">Kênh này chỉ được <b>sử dụng</b> nhân vật. Mọi chỉnh sửa ngoại hình phải thực hiện từ kênh sở hữu.</div>}

      <Tabs<Tab> value={tab} onChange={setTab} tabs={[
        { key: "identity", label: "Nhận diện" }, { key: "images", label: "Hình ảnh & biểu cảm" },
        { key: "versions", label: `Phiên bản (${c.version_count})` },
        ...(ro ? [] : [{ key: "sharing" as Tab, label: "Cấp quyền" }]),
      ]} />

      {tab === "identity" && v && (
        <div className="card space-y-4 p-5">
          <div className="flex items-center justify-between">
            <div className="font-semibold">Phiên bản v{v.version_no} <span className="muted">· {v.change_note} · {fmtDate(v.created_at)}</span></div>
            {!ro && <button className="btn-primary" onClick={() => setEditing(true)}>Tạo phiên bản mới</button>}
          </div>
          <Row label="Ngoại hình" value={v.appearance} />
          <Row label="Phong cách hoạt hình" value={v.art_style} />
          <div><span className="label">Màu chủ đạo</span><ColorChips colors={v.primary_colors} /></div>
          <Row label="Trang phục" value={v.outfit} />
          <Row label="Tính cách" value={v.personality} />
          <Row label="Bối cảnh thường xuất hiện" value={v.usual_settings.join(", ")} />
          <Row label="Animation được phép" value={v.allowed_animations.join(", ")} />
        </div>
      )}

      {tab === "images" && v && <ImagesTab c={c} cid={cid} ro={ro} onChange={set} />}
      {tab === "versions" && <VersionsTab c={c} cid={cid} ro={ro} onChange={set} />}
      {tab === "sharing" && !ro && <SharingTab c={c} cid={cid} onChange={set} />}

      {editing && v && <EditVersionModal c={c} cid={cid} onClose={() => setEditing(false)} onDone={(x) => { set(x); setEditing(false); }} />}
      {renaming && (
        <Modal title="Sửa thông tin" onClose={() => setRenaming(false)}>
          <RenameForm c={c} onSubmit={async (name, species) => {
            const x = await run(() => api.updateCharacter(cid, id, { name, species }), "Đã lưu");
            if (x) { set(x); setRenaming(false); }
          }} />
        </Modal>
      )}
    </div>
  );
}

const Row = ({ label, value }: { label: string; value: string }) => (
  <div><span className="label">{label}</span><div className="whitespace-pre-wrap text-sm">{value || <span className="text-ink-300">—</span>}</div></div>
);

function RenameForm({ c, onSubmit }: { c: Character; onSubmit: (n: string, s: string) => void }) {
  const [n, setN] = useState(c.name), [s, setS] = useState(c.species);
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); onSubmit(n, s); }}>
      <Field label="Tên"><input className="input" required value={n} onChange={(e) => setN(e.target.value)} /></Field>
      <Field label="Loài / kiểu"><input className="input" value={s} onChange={(e) => setS(e.target.value)} /></Field>
      <p className="muted">Đổi tên không tạo phiên bản mới (không ảnh hưởng ngoại hình).</p>
      <div className="flex justify-end"><button className="btn-primary">Lưu</button></div>
    </form>
  );
}

function EditVersionModal({ c, cid, onClose, onDone }: { c: Character; cid: number; onClose: () => void; onDone: (c: Character) => void }) {
  const [d, setD] = useState(draftFromVersion(c.current_version));
  const [note, setNote] = useState("");
  const { busy, run } = useAction();
  return (
    <Modal title={`Phiên bản mới cho ${c.name}`} wide onClose={onClose}>
      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault();
        const x = await run(() => api.createVersion(cid, c.id, { ...draftToFields(d), change_note: note }), "Đã tạo phiên bản mới");
        if (x) onDone(x);
      }}>
        <div className="rounded-lg bg-brand-50 p-3 text-sm">Phiên bản cũ được giữ nguyên. Video đã gắn với phiên bản cũ vẫn dùng đúng ngoại hình cũ.</div>
        <VersionFieldsEditor d={d} set={setD} />
        <Field label="Ghi chú thay đổi"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="VD: Trang phục mùa đông" /></Field>
        <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={onClose}>Hủy</button>
          <button className="btn-primary" disabled={busy}>Tạo phiên bản</button></div>
      </form>
    </Modal>
  );
}

function ImagesTab({ c, cid, ro, onChange }: { c: Character; cid: number; ro: boolean; onChange: (c?: Character) => void }) {
  const v = c.current_version!;
  const { busy, run } = useAction();
  const [exprName, setExprName] = useState("");
  const up = (slot: string, f: File, name?: string) =>
    run(() => api.uploadCharacterImage(cid, c.id, slot, f, name), "Đã tải lên — tạo phiên bản mới").then(onChange);
  const rm = (slot: string, key: string) =>
    run(() => api.removeCharacterImage(cid, c.id, slot, key), "Đã gỡ — tạo phiên bản mới").then(onChange);

  return (
    <div className="space-y-6">
      {!ro && <p className="muted">Mỗi lần tải lên hoặc gỡ ảnh sẽ tạo một phiên bản mới để đảm bảo tính nhất quán.</p>}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {ro ? <>
          <Img label="Ảnh đại diện" url={v.avatar_url} /><Img label="Ảnh toàn thân" url={v.full_body_url} />
        </> : <>
          <ImageUpload label="Ảnh đại diện" url={v.avatar_url} busy={busy} onFile={(f) => up("avatar", f)} />
          <ImageUpload label="Ảnh toàn thân" url={v.full_body_url} busy={busy} aspect="aspect-[3/4]" onFile={(f) => up("full_body", f)} />
        </>}
      </div>

      <div className="card space-y-3 p-5">
        <div className="font-semibold">Bộ biểu cảm</div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
          {v.expressions.map((e) => (
            <div key={e.name} className="space-y-1">
              <img src={e.image_url} alt={e.name} className="aspect-square w-full rounded-lg object-cover" />
              <div className="flex items-center justify-between text-xs"><span>{e.name}</span>
                {!ro && <button className="text-red-700" disabled={busy} onClick={() => rm("expression", e.name)}>Gỡ</button>}</div>
            </div>
          ))}
          {v.expressions.length === 0 && <div className="muted col-span-full">Chưa có biểu cảm.</div>}
        </div>
        {!ro && (
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Tên biểu cảm"><input className="input w-48" value={exprName} onChange={(e) => setExprName(e.target.value)} placeholder="happy, sleepy, focused" /></Field>
            <label className={`btn-ghost cursor-pointer ${!exprName.trim() || busy ? "pointer-events-none opacity-50" : ""}`}>Chọn ảnh biểu cảm
              <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) { void up("expression", f, exprName).then(() => setExprName("")); } e.target.value = ""; }} />
            </label>
          </div>
        )}
      </div>

      <div className="card space-y-3 p-5">
        <div className="font-semibold">Thư viện ảnh tham chiếu ({v.reference_images.length})</div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
          {v.reference_images.map((r) => (
            <div key={r.path} className="space-y-1">
              <a href={r.url} target="_blank" rel="noreferrer"><img src={r.url} alt="" className="aspect-square w-full rounded-lg object-cover" /></a>
              {!ro && <button className="text-xs text-red-700" disabled={busy} onClick={() => rm("reference", r.path)}>Gỡ</button>}
            </div>
          ))}
          {!ro && <ImageUpload label="Thêm ảnh" url={null} busy={busy} onFile={(f) => up("reference", f)} />}
        </div>
      </div>
    </div>
  );
}

const Img = ({ label, url }: { label: string; url: string | null }) => (
  <div><span className="label">{label}</span>{url ? <img src={url} alt={label} className="w-full rounded-lg" /> : <div className="muted">—</div>}</div>
);

function VersionsTab({ c, cid, ro, onChange }: { c: Character; cid: number; ro: boolean; onChange: (c?: Character) => void }) {
  const { data, error, loading, reload } = useApi(() => api.versions(cid, c.id), [cid, c.id, c.current_version?.id]);
  const { busy, run } = useAction();
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  return (
    <div className="card divide-y divide-brand-50">
      {data?.map((v) => (
        <div key={v.id} className="flex flex-wrap items-center gap-4 px-5 py-3">
          <div className="h-12 w-12 overflow-hidden rounded-lg bg-brand-100">{v.avatar_url && <img src={v.avatar_url} alt="" className="h-full w-full object-cover" />}</div>
          <div className="flex-1 text-sm">
            <div className="font-semibold">v{v.version_no} {v.is_current && <Badge tone="green">Đang dùng</Badge>}</div>
            <div className="text-ink-500">{v.change_note || "—"} · {fmtDate(v.created_at)}</div>
          </div>
          <ColorChips colors={v.primary_colors} />
          {!ro && !v.is_current && <button className="btn-ghost" disabled={busy}
            onClick={() => run(() => api.activateVersion(cid, c.id, v.id), `Đã dùng lại v${v.version_no}`).then(onChange)}>Dùng phiên bản này</button>}
        </div>
      ))}
    </div>
  );
}

function SharingTab({ c, cid, onChange }: { c: Character; cid: number; onChange: (c?: Character) => void }) {
  const channels = useApi(api.channels);
  const [target, setTarget] = useState<string>("");
  const [role, setRole] = useState<CharacterRole>("secondary");
  const { busy, run } = useAction();
  const shared = new Set(c.shared_with.map((s) => s.channel_id));
  const options = (channels.data ?? []).filter((x) => x.id !== cid && !shared.has(x.id));
  return (
    <div className="space-y-4">
      <p className="muted">Mặc định nhân vật chỉ dùng được trong kênh sở hữu. Cấp quyền để kênh khác được sử dụng (không được chỉnh sửa).</p>
      <div className="card flex flex-wrap items-end gap-3 p-5">
        <Field label="Kênh nhận quyền">
          <select className="input w-56" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">— Chọn kênh —</option>
            {options.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        </Field>
        <Field label="Vai trò tại kênh đó">
          <select className="input w-40" value={role} onChange={(e) => setRole(e.target.value as CharacterRole)}>
            <option value="secondary">Phụ</option><option value="primary">Chính</option>
          </select>
        </Field>
        <button className="btn-primary" disabled={!target || busy}
          onClick={() => run(() => api.grant(cid, c.id, +target, role), "Đã cấp quyền").then((x) => { onChange(x); setTarget(""); })}>Cấp quyền</button>
      </div>
      <div className="card divide-y divide-brand-50">
        {c.shared_with.map((s) => (
          <div key={s.channel_id} className="flex items-center justify-between px-5 py-3 text-sm">
            <span><b>{s.channel_name}</b> · {s.role === "primary" ? "Chính" : "Phụ"} · từ {fmtDate(s.granted_at)}</span>
            <button className="btn-ghost text-red-700" disabled={busy} onClick={() => run(() => api.revoke(cid, c.id, s.channel_id), "Đã thu hồi").then(onChange)}>Thu hồi</button>
          </div>
        ))}
        {c.shared_with.length === 0 && <div className="muted p-5">Chưa cấp quyền cho kênh nào.</div>}
      </div>
    </div>
  );
}
