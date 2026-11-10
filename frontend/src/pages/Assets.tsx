import { FormEvent, useState } from "react";
import { api } from "../api/client";
import type { Asset, AssetKind, LicenseType } from "../api/types";
import { AssetThumb, fmtBytes, fmtDuration, KINDS, LICENSES, useCapabilities } from "../components/production";
import { Badge, Empty, ErrorBox, Field, Loading, Modal } from "../components/ui";
import { fmtDate, useAction, useApi } from "../lib/hooks";

export default function Assets() {
  const channels = useApi(api.channels);
  const [scope, setScope] = useState<string>("all");          // all | shared | <channel id>
  const [kind, setKind] = useState<AssetKind | "">("");
  const [q, setQ] = useState("");
  const params = scope === "all" ? { kind, q } : scope === "shared" ? { scope: "shared", kind, q } : { scope: "channel", channel_id: Number(scope), kind, q };
  const { data, error, loading, reload } = useApi(() => api.assets(params), [scope, kind, q]);
  const [modal, setModal] = useState<"upload" | "generate" | null>(null);
  const [open, setOpen] = useState<Asset | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="h1">Assets</h1>
          <p className="muted">Thư viện hình ảnh, âm thanh, video, font. Mọi tài nguyên phải có nguồn hợp pháp hoặc do bạn sở hữu.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => setModal("generate")}>✦ Tạo ảnh nền</button>
          <button className="btn-primary" onClick={() => setModal("upload")}>↑ Tải lên</button>
        </div>
      </div>

      <div className="card flex flex-wrap gap-3 p-4">
        <select className="input w-auto" value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="all">Tất cả phạm vi</option>
          <option value="shared">Thư viện dùng chung</option>
          {channels.data?.map((c) => <option key={c.id} value={c.id}>Kênh: {c.name}</option>)}
        </select>
        <select className="input w-auto" value={kind} onChange={(e) => setKind(e.target.value as AssetKind | "")}>
          <option value="">Mọi loại</option>
          {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input className="input w-60" placeholder="Tìm theo tên…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {loading && !data ? <Loading /> : error ? <ErrorBox error={error} onRetry={reload} /> : !data?.length ? (
        <Empty title="Chưa có tài nguyên">Tải lên hình nền, âm thanh nền, font… hoặc tạo ảnh nền tự động từ bảng màu của kênh.</Empty>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
          {data.map((a) => (
            <button key={a.id} className="card overflow-hidden text-left transition hover:shadow-md" onClick={() => setOpen(a)}>
              <div className="aspect-video"><AssetThumb a={a} /></div>
              <div className="space-y-1 p-3">
                <div className="truncate text-sm font-medium">{a.name}</div>
                <div className="flex flex-wrap gap-1">
                  <Badge tone={a.channel_id ? "brand" : "blue"}>{a.channel_name ?? "Dùng chung"}</Badge>
                  <Badge tone={a.license_type === "owned" ? "green" : "slate"}>{LICENSES[a.license_type]}</Badge>
                  {a.source === "generated" && <Badge>Tự tạo</Badge>}
                </div>
                <div className="text-xs text-ink-500">{KINDS[a.kind]} · {fmtBytes(a.size_bytes)}{a.duration_sec ? ` · ${fmtDuration(a.duration_sec)}` : ""}{a.width ? ` · ${a.width}x${a.height}` : ""}</div>
              </div>
            </button>
          ))}
        </div>
      )}

      {modal === "upload" && <UploadModal channels={channels.data ?? []} defaultScope={scope} onClose={() => setModal(null)} onDone={() => { setModal(null); void reload(); }} />}
      {modal === "generate" && <GenerateModal channels={channels.data ?? []} defaultScope={scope} onClose={() => setModal(null)} onDone={() => { setModal(null); void reload(); }} />}
      {open && <AssetModal a={open} onClose={() => setOpen(null)} onChanged={() => { setOpen(null); void reload(); }} />}
    </div>
  );
}

type Ch = { id: number; name: string };

function ScopeSelect({ channels, value, onChange }: { channels: Ch[]; value: string; onChange: (v: string) => void }) {
  return (
    <Field label="Phạm vi" hint="Tài nguyên của kênh chỉ kênh đó dùng được; thư viện dùng chung thì mọi kênh dùng được">
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="shared">Thư viện dùng chung</option>
        {channels.map((c) => <option key={c.id} value={c.id}>Kênh: {c.name}</option>)}
      </select>
    </Field>
  );
}

function UploadModal({ channels, defaultScope, onClose, onDone }: { channels: Ch[]; defaultScope: string; onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [scope, setScope] = useState(defaultScope === "all" ? "shared" : defaultScope);
  const [name, setName] = useState("");
  const [lic, setLic] = useState<LicenseType>("owned");
  const [source, setSource] = useState("");
  const [attr, setAttr] = useState("");
  const [tags, setTags] = useState("");
  const { busy, run } = useAction();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    const a = await run(() => api.uploadAsset(file, { channel_id: scope === "shared" ? null : Number(scope), name, license_type: lic, license_source: source, attribution: attr, tags }), "Đã tải lên");
    if (a) onDone();
  };
  return (
    <Modal title="Tải tài nguyên lên" onClose={onClose}>
      <form className="space-y-4" onSubmit={submit}>
        <Field label="File" hint="Ảnh PNG/JPG/WEBP · Âm thanh MP3/WAV/FLAC/OGG/M4A · Video MP4/MOV/WEBM · Font TTF/OTF">
          <input type="file" className="input" required onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            accept=".png,.jpg,.jpeg,.webp,.mp3,.wav,.flac,.ogg,.opus,.m4a,.aac,.mp4,.mov,.webm,.mkv,.ttf,.otf,.glb" />
        </Field>
        <ScopeSelect channels={channels} value={scope} onChange={setScope} />
        <Field label="Tên hiển thị"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Để trống = tên file" /></Field>
        <Field label="Giấy phép (bắt buộc)">
          <select className="input" value={lic} onChange={(e) => setLic(e.target.value as LicenseType)}>
            {Object.entries(LICENSES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        {lic !== "owned" && (
          <Field label="Nguồn giấy phép" hint="URL trang tải / số hóa đơn / tên gói license — để chứng minh quyền sử dụng">
            <input className="input" required value={source} onChange={(e) => setSource(e.target.value)} />
          </Field>
        )}
        {lic === "cc_by" && (
          <Field label="Ghi công (attribution)" hint="Sẽ được tự động thêm vào mô tả YouTube của video dùng tài nguyên này">
            <input className="input" required value={attr} onChange={(e) => setAttr(e.target.value)} placeholder="Rain loop by NAME (CC BY 4.0)" />
          </Field>
        )}
        <Field label="Tags" hint="phân tách bằng dấu phẩy — dùng để tự chọn hình nền khi nhận ý tưởng"><input className="input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="rain, night, library" /></Field>
        <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={onClose}>Hủy</button>
          <button className="btn-primary" disabled={busy || !file}>{busy ? "Đang tải…" : "Tải lên"}</button></div>
      </form>
    </Modal>
  );
}

function GenerateModal({ channels, defaultScope, onClose, onDone }: { channels: Ch[]; defaultScope: string; onClose: () => void; onDone: () => void }) {
  const caps = useCapabilities();
  const [scope, setScope] = useState(defaultScope === "all" ? (channels[0] ? String(channels[0].id) : "shared") : defaultScope);
  const [style, setStyle] = useState("bokeh");
  const [palette, setPalette] = useState("");
  const [name, setName] = useState("");
  const { busy, run } = useAction();
  return (
    <Modal title="Tạo ảnh nền tự động" onClose={onClose}>
      <div className="space-y-4">
        <p className="muted">Ảnh nền trừu tượng 1920x1080 được tạo bằng thuật toán từ bảng màu (của kênh nếu không nhập) — bạn sở hữu hoàn toàn.
          Với minh họa phong cách riêng của kênh, hãy tải ảnh bạn sở hữu / có giấy phép.</p>
        <ScopeSelect channels={channels} value={scope} onChange={setScope} />
        <Field label="Kiểu">
          <select className="input" value={style} onChange={(e) => setStyle(e.target.value)}>
            {Object.entries(caps.data?.background_styles ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Bảng màu (tuỳ chọn)" hint="#RRGGBB, phân tách bằng dấu phẩy. Để trống = bảng màu kênh hoặc mặc định">
          <input className="input font-mono" value={palette} onChange={(e) => setPalette(e.target.value)} placeholder="#141C2B, #2E4057, #F2C14E" />
        </Field>
        <Field label="Tên"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <div className="flex justify-end gap-2"><button className="btn-ghost" onClick={onClose}>Hủy</button>
          <button className="btn-primary" disabled={busy} onClick={async () => {
            const pal = palette.split(",").map((x) => x.trim()).filter(Boolean);
            const a = await run(() => api.generateBackground({ channel_id: scope === "shared" ? null : Number(scope), style, palette: pal.length ? pal : null, name }), "Đã tạo ảnh nền");
            if (a) onDone();
          }}>{busy ? "Đang tạo…" : "Tạo"}</button></div>
      </div>
    </Modal>
  );
}

function AssetModal({ a, onClose, onChanged }: { a: Asset; onClose: () => void; onChanged: () => void }) {
  const [name, setName] = useState(a.name);
  const [tags, setTags] = useState(a.tags.join(", "));
  const [lic, setLic] = useState<LicenseType>(a.license_type);
  const [source, setSource] = useState(a.license_source);
  const [attr, setAttr] = useState(a.attribution);
  const { busy, run } = useAction();
  return (
    <Modal title={a.name} wide onClose={onClose}>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-3">
          <div className="overflow-hidden rounded-lg bg-brand-50">
            {a.kind === "image" && <img src={a.url} alt="" className="w-full" />}
            {a.kind === "video" && <video src={a.url} controls className="w-full" />}
            {a.kind === "audio" && <div className="p-6"><audio src={a.url} controls className="w-full" /></div>}
            {a.kind === "font" && <div className="p-6 text-sm">Font: {String((a.meta as { family?: string }).family ?? a.name)}</div>}
          </div>
          <div className="space-y-0.5 text-xs text-ink-500">
            <div>{KINDS[a.kind]} · {a.mime_type} · {fmtBytes(a.size_bytes)}{a.duration_sec ? ` · ${fmtDuration(a.duration_sec)}` : ""}</div>
            <div>Phạm vi: {a.channel_name ?? "Thư viện dùng chung"} · Nguồn: {a.source === "generated" ? "Hệ thống tạo" : "Tải lên"}</div>
            <div className="break-all">SHA-256: {a.sha256}</div>
            <div>Tạo lúc {fmtDate(a.created_at)}</div>
          </div>
        </div>
        <div className="space-y-3">
          <Field label="Tên"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Tags"><input className="input" value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
          <Field label="Giấy phép">
            <select className="input" value={lic} disabled={a.source === "generated"} onChange={(e) => setLic(e.target.value as LicenseType)}>
              {Object.entries(LICENSES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Nguồn giấy phép"><input className="input" value={source} onChange={(e) => setSource(e.target.value)} /></Field>
          <Field label="Ghi công"><input className="input" value={attr} onChange={(e) => setAttr(e.target.value)} /></Field>
          <div className="flex justify-between gap-2 pt-2">
            <button className="btn-ghost text-red-700" disabled={busy} onClick={async () => {
              if (!confirm(`Xóa tài nguyên "${a.name}"? File sẽ bị xóa khỏi ổ đĩa.`)) return;
              const ok = await run(() => api.deleteAsset(a.id).then(() => true), "Đã xóa");
              if (ok) onChanged();
            }}>Xóa</button>
            <button className="btn-primary" disabled={busy} onClick={async () => {
              const r = await run(() => api.updateAsset(a.id, { name, tags: tags.split(",").map((t) => t.trim()).filter(Boolean), license_type: lic, license_source: source, attribution: attr }), "Đã lưu");
              if (r) onChanged();
            }}>Lưu</button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
