import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import type { Character, CharacterRole, CharacterVersion, VersionFields } from "../api/types";
import { joinList, splitList } from "../lib/hooks";
import { Badge, ColorChips, Field } from "./ui";

export interface VersionDraft {
  appearance: string; art_style: string; primary_colors: string; outfit: string;
  personality: string; usual_settings: string; allowed_animations: string;
}

export const draftFromVersion = (v?: CharacterVersion | null): VersionDraft => ({
  appearance: v?.appearance ?? "", art_style: v?.art_style ?? "", primary_colors: joinList(v?.primary_colors),
  outfit: v?.outfit ?? "", personality: v?.personality ?? "", usual_settings: joinList(v?.usual_settings),
  allowed_animations: joinList(v?.allowed_animations),
});

export const draftToFields = (d: VersionDraft): Required<VersionFields> => ({
  appearance: d.appearance, art_style: d.art_style, primary_colors: splitList(d.primary_colors),
  outfit: d.outfit, personality: d.personality, usual_settings: splitList(d.usual_settings),
  allowed_animations: splitList(d.allowed_animations),
});

export function VersionFieldsEditor({ d, set }: { d: VersionDraft; set: (d: VersionDraft) => void }) {
  const u = (k: keyof VersionDraft) => (e: { target: { value: string } }) => set({ ...d, [k]: e.target.value });
  return (
    <div className="space-y-4">
      <Field label="Mô tả ngoại hình" hint="Mô tả chi tiết, cố định — dùng để giữ nhất quán giữa các video">
        <textarea className="input min-h-[90px]" value={d.appearance} onChange={u("appearance")} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Phong cách hoạt hình"><input className="input" value={d.art_style} onChange={u("art_style")} placeholder="2D pastel, chibi, anime…" /></Field>
        <Field label="Màu chủ đạo" hint="#RRGGBB, phân tách bằng dấu phẩy"><input className="input font-mono" value={d.primary_colors} onChange={u("primary_colors")} placeholder="#FFFFFF, #F4B6C2" /></Field>
        <Field label="Trang phục"><input className="input" value={d.outfit} onChange={u("outfit")} /></Field>
        <Field label="Tính cách"><input className="input" value={d.personality} onChange={u("personality")} /></Field>
        <Field label="Bối cảnh thường xuất hiện"><input className="input" value={d.usual_settings} onChange={u("usual_settings")} placeholder="study room, library, café" /></Field>
        <Field label="Animation được phép"><input className="input" value={d.allowed_animations} onChange={u("allowed_animations")} placeholder="blink, write, sip tea, tail wag" /></Field>
      </div>
    </div>
  );
}

export function CreateCharacterForm({ busy, onSubmit, onCancel }: {
  busy?: boolean; onCancel: () => void;
  onSubmit: (v: Required<VersionFields> & { name: string; species: string; role: CharacterRole }) => void;
}) {
  const [name, setName] = useState("");
  const [species, setSpecies] = useState("");
  const [role, setRole] = useState<CharacterRole>("secondary");
  const [d, setD] = useState<VersionDraft>(draftFromVersion());
  const submit = (e: FormEvent) => { e.preventDefault(); onSubmit({ name, species, role, ...draftToFields(d) }); };
  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Tên nhân vật *"><input className="input" required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Loài / kiểu"><input className="input" value={species} onChange={(e) => setSpecies(e.target.value)} placeholder="cat, rabbit, bear…" /></Field>
        <Field label="Vai trò trong kênh">
          <select className="input" value={role} onChange={(e) => setRole(e.target.value as CharacterRole)}>
            <option value="primary">Nhân vật chính</option><option value="secondary">Nhân vật phụ</option>
          </select>
        </Field>
      </div>
      <VersionFieldsEditor d={d} set={setD} />
      <p className="muted">Ảnh đại diện, toàn thân, biểu cảm và ảnh tham chiếu được tải lên ở trang chi tiết nhân vật sau khi tạo.</p>
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onCancel}>Hủy</button>
        <button className="btn-primary" disabled={busy}>{busy ? "Đang tạo…" : "Tạo nhân vật"}</button>
      </div>
    </form>
  );
}

export function CharacterCard({ c, showOwner }: { c: Character; showOwner?: boolean }) {
  const v = c.current_version;
  return (
    <Link to={`/channels/${c.channel_id}/characters/${c.id}`} className={`card flex gap-4 p-4 transition hover:shadow-md ${c.archived ? "opacity-60" : ""}`}>
      <div className="h-20 w-20 shrink-0 overflow-hidden rounded-xl bg-brand-100">
        {v?.avatar_url ? <img src={v.avatar_url} alt={c.name} className="h-full w-full object-cover" /> :
          <div className="flex h-full items-center justify-center text-2xl font-bold text-brand-700">{c.name[0]}</div>}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-semibold">{c.name}</span>
          <Badge tone={c.role === "primary" ? "brand" : "slate"}>{c.role === "primary" ? "Chính" : "Phụ"}</Badge>
          {!c.is_owner && <Badge tone="blue">Được cấp quyền</Badge>}
          {c.archived && <Badge>Lưu trữ</Badge>}
        </div>
        <div className="text-xs text-ink-500">{c.species || "—"} · v{v?.version_no ?? 0} · {c.version_count} phiên bản{showOwner ? ` · ${c.owner_channel_name}` : ""}</div>
        <div className="line-clamp-2 text-sm text-ink-700">{v?.appearance || <span className="text-ink-300">Chưa có mô tả ngoại hình</span>}</div>
        {v && v.primary_colors.length > 0 && <ColorChips colors={v.primary_colors} />}
      </div>
    </Link>
  );
}
