import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Asset, AudioLayer, Capabilities, ContentInput, ContentProject, ContentType, PomodoroConfig, RenderSettings } from "../api/types";
import {
  AssetPicker, CONTENT_TYPES, fmtMinutes, JobRow, ProdBadge, usePolling, useCapabilities, VideoList,
} from "../components/production";
import { Badge, ErrorBox, Field, ImageUpload, Loading, Modal, Tabs } from "../components/ui";
import { useAction, useApi } from "../lib/hooks";
// three.js is large: load the 3D editor only when the tab is opened
const Scene3DEditor = lazy(() => import("../components/scene3d").then((m) => ({ default: m.Scene3DEditor })));

type Tab = "info" | "visual" | "audio" | "scene3d" | "timer" | "youtube" | "render";

interface Draft {
  title: string; content_type: ContentType; theme: string; setting: string; script: string;
  duration_minutes: number; character_id: number | null; background_asset_id: number | null;
  animation: ContentProject["animation"]; audio_layers: AudioLayer[]; pomodoro: PomodoroConfig | null;
  render_settings: RenderSettings; youtube_title: string; youtube_description: string; youtube_tags: string;
}

const toDraft = (p: ContentProject): Draft => {
  // older/partial JSON from the API is completed with the same defaults as the backend schemas
  const a: Partial<ContentProject["animation"]> = p.animation ?? {};
  const ch: Partial<ContentProject["animation"]["character"]> = a.character ?? {};
  const rs: Partial<RenderSettings> = p.render_settings ?? {};
  const ov: Partial<RenderSettings["overlay"]> = rs.overlay ?? {};
  return {
    title: p.title, content_type: p.content_type, theme: p.theme, setting: p.setting, script: p.script,
    duration_minutes: p.duration_minutes, character_id: p.character_id, background_asset_id: p.background_asset_id,
    animation: {
      background_motion: a.background_motion ?? "slow_zoom", effects: a.effects ?? [],
      character: { position: ch.position ?? "bottom_right", scale: ch.scale ?? 0.42, motion: ch.motion ?? "bob" },
    },
    audio_layers: p.audio_layers ?? [], pomodoro: p.pomodoro,
    render_settings: {
      chime: rs.chime ?? false, chime_volume: rs.chime_volume ?? 0.6, master_volume: rs.master_volume ?? 1,
      resolution: rs.resolution ?? "1920x1080", fps: rs.fps ?? 30, crf: rs.crf ?? null, preset: rs.preset ?? null,
      overlay: {
        mode: ov.mode ?? "none", position: ov.position ?? "top_center", color: ov.color ?? "#FFFFFF",
        box: ov.box ?? true, font_asset_id: ov.font_asset_id ?? null, labels: ov.labels ?? {},
      },
    },
    youtube_title: p.youtube_title, youtube_description: p.youtube_description, youtube_tags: p.youtube_tags.join(", "),
  };
};

function toPayload(d: Draft, p: ContentProject): Partial<ContentInput> {
  return {
    title: d.title, content_type: d.content_type, theme: d.theme, setting: d.setting, script: d.script,
    duration_minutes: d.duration_minutes,
    ...(d.character_id ? { character_id: d.character_id } : p.character_id ? { clear_character: true } : {}),
    ...(d.background_asset_id ? { background_asset_id: d.background_asset_id } : p.background_asset_id ? { clear_background: true } : {}),
    animation: d.animation, audio_layers: d.audio_layers,
    ...(d.pomodoro ? { pomodoro: d.pomodoro } : p.pomodoro ? { clear_pomodoro: true } : {}),
    render_settings: d.render_settings, youtube_title: d.youtube_title, youtube_description: d.youtube_description,
    youtube_tags: d.youtube_tags.split(",").map((t) => t.trim()).filter(Boolean),
  };
}

export default function ContentDetail() {
  const cid = Number(useParams().channelId);
  const pid = Number(useParams().projectId);
  const nav = useNavigate();
  const { data: p, setData, error, loading, reload } = useApi(() => api.content(cid, pid), [cid, pid]);
  const caps = useCapabilities();
  const [tab, setTab] = useState<Tab>("info");
  const [d, setD] = useState<Draft | null>(null);
  const { busy, run } = useAction();

  useEffect(() => { if (p) setD(toDraft(p)); }, [p]);
  const locked = p ? p.status === "queued" || p.status === "rendering" : false;
  usePolling(() => void reload(), locked, 4000);
  const dirty = useMemo(() => !!(p && d && JSON.stringify(toDraft(p)) !== JSON.stringify(d)), [p, d]);

  if (loading && !p) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!p || !d) return null;

  const set = (patch: Partial<Draft>) => setD({ ...d, ...patch });
  const save = async () => {
    const r = await run(() => api.updateContent(cid, pid, toPayload(d, p)), "Đã lưu");
    if (r) setData(r);
    return r;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm text-ink-500"><Link to="/content" className="hover:underline">Content Library</Link> / <Link to={`/channels/${cid}`} className="hover:underline">{p.channel_name}</Link></div>
          <div className="mt-1 flex flex-wrap items-center gap-2"><h1 className="h1">{p.title}</h1><ProdBadge status={p.status} /></div>
          <div className="text-xs text-ink-500">{CONTENT_TYPES[p.content_type]} · {fmtMinutes(p.duration_minutes)} · #{p.id}{p.fingerprint ? ` · vân tay ${p.fingerprint.slice(0, 10)}` : ""}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-primary" disabled={busy || locked || !dirty} onClick={save}>{dirty ? "💾 Lưu thay đổi" : "Đã lưu"}</button>
          <SaveTemplateButton cid={cid} pid={pid} />
          <button className="btn-ghost text-red-700" disabled={busy || locked} onClick={async () => {
            if (!confirm("Xóa dự án này? Video đã render (nếu có) vẫn được giữ lại.")) return;
            const ok = await run(() => api.deleteContent(cid, pid).then(() => true), "Đã xóa dự án");
            if (ok) nav("/content");
          }}>Xóa</button>
        </div>
      </div>
      {locked && <div className="card border-violet-200 bg-violet-50 p-3 text-sm text-violet-800">Dự án đang trong hàng đợi / đang render — chỉ xem. Hủy tác vụ ở tab Render nếu cần sửa.</div>}
      {p.last_error && <div className="card border-red-200 bg-red-50 p-3 text-sm text-red-800">Lỗi render gần nhất: {p.last_error}</div>}

      <Tabs<Tab> value={tab} onChange={setTab} tabs={[
        { key: "info", label: "Thông tin" }, { key: "visual", label: "Hình ảnh & nhân vật" }, { key: "audio", label: "Âm thanh" },
        { key: "scene3d", label: "Cảnh 3D" }, { key: "timer", label: "Pomodoro / đồng hồ" }, { key: "youtube", label: "YouTube" }, { key: "render", label: "Render" },
      ]} />

      <fieldset disabled={locked} className="contents">
        {tab === "info" && <InfoTab d={d} set={set} caps={caps.data} />}
        {tab === "visual" && <VisualTab d={d} set={set} p={p} caps={caps.data} onProject={setData} />}
        {tab === "audio" && <AudioTab d={d} set={set} cid={cid} caps={caps.data} />}
        {tab === "scene3d" && <Suspense fallback={<Loading />}><Scene3DEditor p={p} onProject={setData} /></Suspense>}
        {tab === "timer" && <TimerTab d={d} set={set} caps={caps.data} />}
        {tab === "youtube" && <YoutubeTab d={d} set={set} p={p} dirty={dirty} save={save} onProject={setData} />}
      </fieldset>
      {tab === "render" && <RenderTab p={p} dirty={dirty} save={save} onChanged={reload} />}
      {dirty && tab !== "render" && (
        <div className="sticky bottom-4 flex justify-end"><button className="btn-primary shadow-lg" disabled={busy || locked} onClick={save}>💾 Lưu thay đổi</button></div>
      )}
    </div>
  );
}

function InfoTab({ d, set, caps }: { d: Draft; set: (p: Partial<Draft>) => void; caps: Capabilities | null }) {
  return (
    <div className="card grid gap-4 p-5 md:grid-cols-2">
      <Field label="Tên dự án"><input className="input" value={d.title} onChange={(e) => set({ title: e.target.value })} /></Field>
      <Field label="Loại nội dung">
        <select className="input" value={d.content_type} onChange={(e) => set({ content_type: e.target.value as ContentType })}>
          {Object.entries(CONTENT_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </Field>
      <Field label="Chủ đề / thời điểm" hint="VD: đêm mưa, sáng mùa thu"><input className="input" value={d.theme} onChange={(e) => set({ theme: e.target.value })} /></Field>
      <Field label="Bối cảnh" hint="VD: phòng học gác mái, quán cà phê góc phố"><input className="input" value={d.setting} onChange={(e) => set({ setting: e.target.value })} /></Field>
      <Field label="Thời lượng">
        <select className="input" value={d.duration_minutes} onChange={(e) => set({ duration_minutes: Number(e.target.value) })}>
          {(caps?.durations ?? [30, 60, 120, 240, 360, 480]).map((m) => <option key={m} value={m}>{fmtMinutes(m)}</option>)}
        </select>
      </Field>
      <div className="md:col-span-2">
        <Field label="Kịch bản / ghi chú cảnh" hint="Mô tả diễn biến, cảm xúc, cảnh quay. Có thể đưa vào mô tả YouTube khi tạo metadata.">
          <textarea className="input min-h-[140px]" value={d.script} onChange={(e) => set({ script: e.target.value })} />
        </Field>
      </div>
    </div>
  );
}

function VisualTab({ d, set, p, caps, onProject }: { d: Draft; set: (p: Partial<Draft>) => void; p: ContentProject; caps: Capabilities | null; onProject: (p: ContentProject) => void }) {
  const characters = useApi(() => api.characters(p.channel_id), [p.channel_id]);
  const bgAssets = useApi(() => api.usableAssets(p.channel_id, "image"), [p.channel_id]);
  const [picking, setPicking] = useState(false);
  const { busy, run } = useAction();
  const bg = bgAssets.data?.find((a) => a.id === d.background_asset_id);
  const anim = d.animation;
  const setAnim = (patch: Partial<Draft["animation"]>) => set({ animation: { ...anim, ...patch } });
  const toggleFx = (k: string) => setAnim({ effects: anim.effects.includes(k) ? anim.effects.filter((x) => x !== k) : [...anim.effects, k] });
  const outdated = p.character_id && p.character_version_id !== p.character_current_version_id;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="card space-y-4 p-5">
        <div className="font-semibold">Hình nền & chuyển động</div>
        <div className="aspect-video overflow-hidden rounded-lg bg-brand-50">
          {bg ? <img src={bg.url} alt="" className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-sm text-ink-500">Chưa chọn hình nền</div>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost" onClick={() => setPicking(true)}>Chọn / tạo hình nền</button>
          {d.background_asset_id && <button type="button" className="btn-ghost" onClick={() => set({ background_asset_id: null })}>Bỏ chọn</button>}
          {bg && <span className="self-center text-xs text-ink-500">{bg.name} · {bg.channel_id ? "của kênh" : "dùng chung"}</span>}
        </div>
        <Field label="Chuyển động nền">
          <select className="input" value={anim.background_motion} onChange={(e) => setAnim({ background_motion: e.target.value })}>
            {Object.entries(caps?.background_motions ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <div>
          <span className="label">Hiệu ứng</span>
          <div className="flex flex-wrap gap-2">
            {Object.entries(caps?.effects ?? {}).map(([k, v]) => (
              <label key={k} className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm ${anim.effects.includes(k) ? "border-brand-400 bg-brand-50" : "border-brand-100"}`}>
                <input type="checkbox" checked={anim.effects.includes(k)} onChange={() => toggleFx(k)} />{v}
              </label>
            ))}
          </div>
          <p className="mt-2 text-xs text-ink-500">Mọi chuyển động lặp tuần hoàn khớp với vòng lặp {caps?.loop_seconds ?? 60}s → video dài liền mạch, không giật.</p>
        </div>
      </div>
      <div className="card space-y-4 p-5">
        <div className="font-semibold">Nhân vật</div>
        <Field label="Nhân vật trong video" hint="Chỉ nhân vật của kênh hoặc được cấp quyền. Phiên bản được ghim để giữ ngoại hình nhất quán.">
          <select className="input" value={d.character_id ?? ""} onChange={(e) => set({ character_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Không có nhân vật</option>
            {characters.data?.filter((c) => !c.archived || c.id === d.character_id).map((c) => (
              <option key={c.id} value={c.id}>{c.name}{c.role === "primary" ? " (chính)" : ""}{c.is_owner ? "" : " — được cấp quyền"}</option>
            ))}
          </select>
        </Field>
        {p.character_id && p.character_id === d.character_id && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone="brand">Ghim phiên bản v{p.character_version_no}</Badge>
            {outdated && <>
              <span className="text-xs text-amber-700">Nhân vật đã có phiên bản mới hơn.</span>
              <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={() => run(() => api.syncCharacterVersion(p.channel_id, p.id), "Đã cập nhật phiên bản").then((r) => r && onProject(r))}>Dùng phiên bản mới nhất</button>
            </>}
            <Link className="text-xs text-brand-700 underline" to={`/channels/${p.channel_id}/characters/${p.character_id}`}>Xem nhân vật</Link>
          </div>
        )}
        {d.character_id && (
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Vị trí">
              <select className="input" value={anim.character.position} onChange={(e) => setAnim({ character: { ...anim.character, position: e.target.value } })}>
                {(caps?.character_positions ?? []).map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </Field>
            <Field label={`Kích thước (${Math.round(anim.character.scale * 100)}% chiều cao)`}>
              <input type="range" min={0.15} max={0.9} step={0.01} value={anim.character.scale} className="w-full"
                onChange={(e) => setAnim({ character: { ...anim.character, scale: Number(e.target.value) } })} />
            </Field>
            <Field label="Chuyển động">
              <select className="input" value={anim.character.motion} onChange={(e) => setAnim({ character: { ...anim.character, motion: e.target.value } })}>
                {Object.entries(caps?.character_motions ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
          </div>
        )}
        <p className="text-xs text-ink-500">Video dùng ảnh toàn thân (hoặc ảnh đại diện) của phiên bản đã ghim. Nên dùng PNG nền trong suốt.</p>
      </div>
      {picking && <AssetPicker channelId={p.channel_id} kind="image" onClose={() => setPicking(false)} onPick={(a) => { set({ background_asset_id: a.id }); setPicking(false); void bgAssets.reload(); }} />}
    </div>
  );
}

function AudioTab({ d, set, cid, caps }: { d: Draft; set: (p: Partial<Draft>) => void; cid: number; caps: Capabilities | null }) {
  const audioAssets = useApi(() => api.usableAssets(cid, "audio"), [cid]);
  const [picking, setPicking] = useState(false);
  const [gen, setGen] = useState("rain");
  const names = useMemo(() => Object.fromEntries((audioAssets.data ?? []).map((a: Asset) => [a.id, a.name])), [audioAssets.data]);
  const layers = d.audio_layers;
  const update = (i: number, patch: Partial<AudioLayer>) => set({ audio_layers: layers.map((l, j) => (j === i ? { ...l, ...patch } : l)) });
  return (
    <div className="card space-y-4 p-5">
      <div className="flex flex-wrap items-end gap-2">
        <div className="font-semibold">Các lớp âm thanh ({layers.length}/8)</div>
        <div className="ml-auto flex flex-wrap items-end gap-2">
          <select className="input w-auto" value={gen} onChange={(e) => setGen(e.target.value)}>
            {Object.entries(caps?.generators ?? {}).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <button type="button" className="btn-ghost" disabled={layers.length >= 8} onClick={() => set({ audio_layers: [...layers, { kind: "generator", generator: gen, volume: 0.6 }] })}>+ Âm thanh tổng hợp</button>
          <button type="button" className="btn-ghost" disabled={layers.length >= 8} onClick={() => setPicking(true)}>+ Từ thư viện</button>
        </div>
      </div>
      {layers.length === 0 && <div className="muted">Chưa có lớp âm thanh. Thêm âm thanh tổng hợp (do hệ thống tạo, không cần bản quyền) hoặc file âm thanh có giấy phép.</div>}
      <div className="divide-y divide-brand-50">
        {layers.map((l, i) => (
          <div key={i} className="flex flex-wrap items-center gap-4 py-3">
            <div className="min-w-[200px] flex-1">
              <div className="font-medium">{l.kind === "generator" ? caps?.generators[l.generator ?? ""]?.label ?? l.generator : names[l.asset_id ?? -1] ?? `Asset #${l.asset_id}`}</div>
              <div className="text-xs text-ink-500">{l.kind === "generator" ? `Tổng hợp · ${caps?.generators[l.generator ?? ""]?.description ?? ""}` : "File trong thư viện (lặp liên tục)"}</div>
            </div>
            <label className="flex items-center gap-2 text-sm">Âm lượng
              <input type="range" min={0} max={2} step={0.05} value={l.volume} onChange={(e) => update(i, { volume: Number(e.target.value) })} />
              <span className="w-10 text-right font-mono text-xs">{Math.round(l.volume * 100)}%</span>
            </label>
            <button type="button" className="btn-ghost text-xs" onClick={() => set({ audio_layers: layers.filter((_, j) => j !== i) })}>Gỡ</button>
          </div>
        ))}
      </div>
      <div className="grid gap-4 border-t border-brand-50 pt-4 sm:grid-cols-2">
        <Field label={`Âm lượng tổng (${Math.round(d.render_settings.master_volume * 100)}%)`}>
          <input type="range" min={0.1} max={2} step={0.05} className="w-full" value={d.render_settings.master_volume}
            onChange={(e) => set({ render_settings: { ...d.render_settings, master_volume: Number(e.target.value) } })} />
        </Field>
        <p className="text-xs text-ink-500">Âm thanh được mix 48 kHz stereo, có limiter chống vỡ tiếng, fade in/out. File thư viện nên là đoạn loop liền mạch.</p>
      </div>
      {picking && <AssetPicker channelId={cid} kind="audio" onClose={() => setPicking(false)} onPick={(a) => { set({ audio_layers: [...layers, { kind: "asset", asset_id: a.id, volume: 0.8 }] }); setPicking(false); void audioAssets.reload(); }} />}
    </div>
  );
}

function TimerTab({ d, set, caps }: { d: Draft; set: (p: Partial<Draft>) => void; caps: Capabilities | null }) {
  const rs = d.render_settings;
  const ov = rs.overlay;
  const setOv = (patch: Partial<RenderSettings["overlay"]>) => set({ render_settings: { ...rs, overlay: { ...ov, ...patch } } });
  const pm = d.pomodoro ?? { focus_min: 25, short_break_min: 5, long_break_min: 15, cycles_before_long: 4 };
  const setPm = (patch: Partial<PomodoroConfig>) => set({ pomodoro: { ...pm, ...patch } });
  const phases = useMemo(() => {
    if (!d.pomodoro) return [];
    const out: { kind: string; start: number; end: number }[] = [];
    let t = 0, n = 0;
    const D = d.duration_minutes;
    while (t < D && out.length < 400) {
      n += 1; const e = Math.min(t + pm.focus_min, D); out.push({ kind: `Tập trung ${n}`, start: t, end: e }); t = e;
      if (t >= D) break;
      const long = pm.cycles_before_long > 0 && n % pm.cycles_before_long === 0;
      const b = long ? pm.long_break_min : pm.short_break_min;
      if (b > 0) { const e2 = Math.min(t + b, D); out.push({ kind: long ? "Nghỉ dài" : "Nghỉ", start: t, end: e2 }); t = e2; }
    }
    return out;
  }, [d.pomodoro, d.duration_minutes, pm]);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="card space-y-4 p-5">
        <div className="font-semibold">Đồng hồ trên video</div>
        <Field label="Chế độ">
          <select className="input" value={ov.mode} onChange={(e) => setOv({ mode: e.target.value })}>
            {Object.entries(caps?.overlay_modes ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        {ov.mode !== "none" && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Vị trí">
                <select className="input" value={ov.position} onChange={(e) => setOv({ position: e.target.value })}>
                  {(caps?.overlay_positions ?? []).map((k) => <option key={k} value={k}>{k}</option>)}
                </select>
              </Field>
              <Field label="Màu chữ"><input type="color" className="input h-10 p-1" value={ov.color} onChange={(e) => setOv({ color: e.target.value.toUpperCase() })} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ov.box} onChange={(e) => setOv({ box: e.target.checked })} />Nền mờ phía sau đồng hồ</label>
            <div className="grid gap-3 sm:grid-cols-2">
              {(["focus", "short_break", "long_break", "session"] as const).map((k) => (
                <Field key={k} label={`Nhãn "${k}"`}><input className="input" placeholder="mặc định theo ngôn ngữ kênh" value={ov.labels[k] ?? ""}
                  onChange={(e) => setOv({ labels: { ...ov.labels, [k]: e.target.value } })} /></Field>
              ))}
            </div>
            {caps && (!caps.drawtext || !caps.font_path) && <div className="rounded bg-amber-50 p-2 text-xs text-amber-800">
              {!caps.drawtext ? "FFmpeg hiện tại không có drawtext." : "Chưa tìm thấy font hệ thống — cài fonts-dejavu-core hoặc tải font lên Assets."}</div>}
          </>
        )}
        {ov.mode === "pomodoro" && (
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={rs.chime} onChange={(e) => set({ render_settings: { ...rs, chime: e.target.checked } })} />Chuông nhẹ khi chuyển pha</label>
        )}
      </div>
      <div className="card space-y-4 p-5">
        <div className="flex items-center justify-between">
          <div className="font-semibold">Cấu hình Pomodoro</div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!d.pomodoro} onChange={(e) => set({ pomodoro: e.target.checked ? pm : null })} />Bật</label>
        </div>
        {d.pomodoro ? (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Field label="Tập trung (phút)"><input type="number" min={5} max={120} className="input" value={pm.focus_min} onChange={(e) => setPm({ focus_min: Number(e.target.value) })} /></Field>
              <Field label="Nghỉ ngắn"><input type="number" min={0} max={60} className="input" value={pm.short_break_min} onChange={(e) => setPm({ short_break_min: Number(e.target.value) })} /></Field>
              <Field label="Nghỉ dài"><input type="number" min={0} max={60} className="input" value={pm.long_break_min} onChange={(e) => setPm({ long_break_min: Number(e.target.value) })} /></Field>
              <Field label="Nghỉ dài sau"><input type="number" min={0} max={12} className="input" value={pm.cycles_before_long} onChange={(e) => setPm({ cycles_before_long: Number(e.target.value) })} /></Field>
            </div>
            <div className="max-h-56 overflow-y-auto rounded-lg border border-brand-50 text-xs">
              {phases.map((ph, i) => (
                <div key={i} className={`flex justify-between px-3 py-1 ${ph.kind.startsWith("Tập") ? "" : "bg-brand-50"}`}>
                  <span>{ph.kind}</span><span className="font-mono">{ph.start}′ → {ph.end}′</span>
                </div>
              ))}
            </div>
            <p className="text-xs text-ink-500">{phases.filter((x) => x.kind.startsWith("Tập")).length} phiên tập trung. Mốc thời gian được đưa vào mô tả YouTube (chapters).</p>
          </>
        ) : <p className="muted">Tắt — video không chia phiên tập trung/nghỉ.</p>}
      </div>
    </div>
  );
}

function YoutubeTab({ d, set, p, dirty, save, onProject }: { d: Draft; set: (p: Partial<Draft>) => void; p: ContentProject; dirty: boolean; save: () => Promise<ContentProject | undefined>; onProject: (p: ContentProject) => void }) {
  const { busy, run } = useAction();
  const tagLen = d.youtube_tags.split(",").map((t) => t.trim()).filter(Boolean).reduce((s, t) => s + t.length + (t.includes(" ") ? 2 : 0) + 1, 0);
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="card space-y-4 p-5 lg:col-span-2">
        <div className="flex items-center justify-between">
          <div className="font-semibold">Metadata YouTube</div>
          <button type="button" className="btn-ghost" disabled={busy} onClick={async () => {
            if (dirty && !(await save())) return;
            const m = await run(() => api.generateMetadata(p.channel_id, p.id), "Đã tạo metadata");
            if (m) set({ youtube_title: m.youtube_title, youtube_description: m.youtube_description, youtube_tags: m.youtube_tags.join(", ") });
          }}>✦ Tạo tự động</button>
        </div>
        <Field label={`Tiêu đề (${d.youtube_title.length}/100)`}><input className="input" maxLength={100} value={d.youtube_title} onChange={(e) => set({ youtube_title: e.target.value })} /></Field>
        <Field label={`Mô tả (${d.youtube_description.length}/5000)`} hint="Tự động gồm: Pomodoro, âm thanh, chapters, ghi công giấy phép CC BY">
          <textarea className="input min-h-[260px] font-mono text-xs" maxLength={5000} value={d.youtube_description} onChange={(e) => set({ youtube_description: e.target.value })} />
        </Field>
        <Field label={`Tags (~${tagLen}/500 ký tự)`} hint="phân tách bằng dấu phẩy"><input className="input" value={d.youtube_tags} onChange={(e) => set({ youtube_tags: e.target.value })} /></Field>
        <p className="text-xs text-ink-500">Đăng video (mặc định Private), playlist và lịch công khai: Phase 3.</p>
      </div>
      <div className="card space-y-3 p-5">
        <div className="font-semibold">Thumbnail</div>
        <ImageUpload label="1280x720, ≤ 2 MB" url={p.thumbnail_url} busy={busy} aspect="aspect-video"
          onFile={(f) => run(() => api.uploadThumbnail(p.channel_id, p.id, f), "Đã tải thumbnail").then((r) => r && onProject(r))} />
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost" disabled={busy} onClick={async () => {
            if (dirty && !(await save())) return;
            const r = await run(() => api.generateThumbnail(p.channel_id, p.id), "Đã tạo thumbnail");
            if (r) onProject(r);
          }}>✦ Tạo từ hình nền + nhân vật</button>
          {p.thumbnail_url && <button type="button" className="btn-ghost" disabled={busy} onClick={() => run(() => api.removeThumbnail(p.channel_id, p.id)).then((r) => r && onProject(r))}>Gỡ</button>}
        </div>
        <p className="text-xs text-ink-500">Nếu không có thumbnail, hệ thống tự tạo khi render video.</p>
      </div>
    </div>
  );
}

function RenderTab({ p, dirty, save, onChanged }: { p: ContentProject; dirty: boolean; save: () => Promise<ContentProject | undefined>; onChanged: () => void }) {
  const report = useApi(() => api.validateContent(p.channel_id, p.id), [p.id, p.updated_at]);
  const jobs = useApi(() => api.projectJobs(p.channel_id, p.id), [p.id]);
  const videos = useApi(() => api.videos({ project_id: p.id }), [p.id, p.status]);
  const [seconds, setSeconds] = useState(30);
  const { busy, run } = useAction();
  const active = (jobs.data ?? []).some((j) => j.status === "queued" || j.status === "running");
  usePolling(() => { void jobs.reload(); }, active, 3000);
  const prevActive = useState({ v: active })[0];
  useEffect(() => { if (prevActive.v && !active) { onChanged(); void videos.reload(); } prevActive.v = active; }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async (job_type: "full" | "preview") => {
    if (dirty && !(await save())) return;
    const j = await run(() => api.render(p.channel_id, p.id, { job_type, preview_seconds: seconds }),
      job_type === "full" ? "Đã đưa vào hàng đợi render" : "Đang render bản xem thử");
    if (j) { void jobs.reload(); onChanged(); }
  };
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card space-y-3 p-5">
          <div className="flex items-center justify-between"><div className="font-semibold">Kiểm tra trước khi render</div>
            <button className="btn-ghost text-xs" onClick={report.reload}>↻</button></div>
          {report.loading && !report.data ? <Loading /> : report.error ? <ErrorBox error={report.error} /> : report.data && (
            <div className="space-y-1 text-sm">
              {report.data.ok && <div className="text-emerald-700">✔ Đủ điều kiện render</div>}
              {report.data.errors.map((e) => <div key={e} className="text-red-700">✖ {e}</div>)}
              {report.data.warnings.map((w) => <div key={w} className="text-amber-700">! {w}</div>)}
            </div>
          )}
          {p.status !== "ready" && report.data?.ok && p.status !== "queued" && p.status !== "rendering" && (
            <button className="btn-ghost" disabled={busy} onClick={() => run(() => api.markReady(p.channel_id, p.id), "Đã đánh dấu sẵn sàng").then(onChanged)}>Đánh dấu “Sẵn sàng”</button>
          )}
        </div>
        <div className="card space-y-4 p-5">
          <div className="font-semibold">Render</div>
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Bản xem thử (giây)"><input type="number" min={10} max={300} className="input w-28" value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} /></Field>
            <button className="btn-ghost" disabled={busy || active || !report.data?.ok} onClick={() => start("preview")}>▶ Render xem thử</button>
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-brand-50 pt-4">
            <button className="btn-primary" disabled={busy || active || !report.data?.ok} onClick={() => start("full")}>🎬 Render video {fmtMinutes(p.duration_minutes)}</button>
            <span className="text-xs text-ink-500">H.264 · AAC 48 kHz · {p.render_settings.resolution ?? "1920x1080"} · {p.render_settings.fps ?? 30} fps · MP4</span>
          </div>
          <p className="text-xs text-ink-500">Hàng đợi chỉ chạy 1 tác vụ nặng một lúc (máy 8 GB RAM). Video không có đồng hồ được ghép bằng stream copy nên rất nhanh; video Pomodoro cần mã hóa lại một lượt.</p>
        </div>
      </div>
      <div className="card divide-y divide-brand-50">
        <div className="px-4 py-3 font-semibold">Tác vụ render của dự án</div>
        {jobs.data?.length ? jobs.data.map((j) => <JobRow key={j.id} j={j} compact onChanged={() => { void jobs.reload(); onChanged(); }} />) : <div className="muted p-4">Chưa có tác vụ.</div>}
      </div>
      <div className="space-y-3">
        <div className="font-semibold">Video đã render</div>
        <VideoList items={videos.data ?? []} onChanged={() => { void videos.reload(); onChanged(); }} />
      </div>
    </div>
  );
}

function SaveTemplateButton({ cid, pid }: { cid: number; pid: number }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const { busy, run } = useAction();
  return (
    <>
      <button className="btn-ghost" onClick={() => setOpen(true)}>Lưu thành template</button>
      {open && (
        <Modal title="Lưu cấu hình thành template của kênh" onClose={() => setOpen(false)}>
          <div className="space-y-3">
            <p className="muted">Lưu thời lượng, hiệu ứng, âm thanh tổng hợp, Pomodoro và cài đặt đồng hồ để tái sử dụng cho dự án mới của kênh.</p>
            <Field label="Tên template"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <div className="flex justify-end gap-2"><button className="btn-ghost" onClick={() => setOpen(false)}>Hủy</button>
              <button className="btn-primary" disabled={busy || name.trim().length < 2} onClick={async () => {
                const t = await run(() => api.saveAsTemplate(cid, pid, name.trim()), "Đã lưu template");
                if (t) setOpen(false);
              }}>Lưu</button></div>
          </div>
        </Modal>
      )}
    </>
  );
}
