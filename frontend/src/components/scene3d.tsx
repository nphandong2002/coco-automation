import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Asset, ContentProject } from "../api/types";
import { SceneEngine } from "../scene3d/engine";
import { defaultScene, PRESETS, TIMES, TRIGGERS } from "../scene3d/types";
import type { Environment3D, PickTarget, ReactionTrigger, Scene3D, TimeOfDay } from "../scene3d/types";
import { useAction } from "../lib/hooks";
import { AssetPicker, useCapabilities } from "./production";
import { Field } from "./ui";

const PICK_LABEL: Record<PickTarget, string> = {
  window: "Cửa sổ — bấm để bật/tắt mưa", fireplace: "Lò sưởi — bấm để bật/tắt lửa", lamp: "Đèn — bấm để bật/tắt", character: "Nhân vật — bấm để tương tác",
};

/** Live three.js view of a scene. Rebuilds only when preset/character/model change; environment edits are applied live. */
export function Scene3DViewer({ scene, modelUrl, onEnvChange, engineRef, onReady }: {
  scene: Scene3D; modelUrl: string | null; onEnvChange: (e: Environment3D) => void;
  engineRef?: React.MutableRefObject<SceneEngine | null>; onReady?: (i: { clips: string[]; placeholder: boolean }) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const eng = useRef<SceneEngine | null>(null);
  const [hover, setHover] = useState<PickTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cb = useRef({ onEnvChange, onReady });
  cb.current = { onEnvChange, onReady };

  useEffect(() => {
    let engine: SceneEngine;
    try {
      engine = new SceneEngine(canvas.current!, {
        interactive: true, onHover: setHover,
        onEnvChange: (e) => cb.current.onEnvChange(e), onReady: (i) => cb.current.onReady?.(i),
      });
    } catch (e) {
      setError("Trình duyệt không hỗ trợ WebGL nên không hiển thị được cảnh 3D.");
      return;
    }
    eng.current = engine;
    if (engineRef) engineRef.current = engine;
    const ro = new ResizeObserver(() => { const r = wrap.current!.getBoundingClientRect(); engine.resize(r.width, r.height); });
    ro.observe(wrap.current!);
    engine.start();
    return () => { ro.disconnect(); engine.dispose(); eng.current = null; if (engineRef) engineRef.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const structural = JSON.stringify([scene.preset, scene.character, modelUrl]);
  useEffect(() => { void eng.current?.setScene(scene, modelUrl); }, [structural]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { eng.current?.setEnvironment(scene.environment); }, [JSON.stringify(scene.environment)]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={wrap} className="relative aspect-video w-full overflow-hidden rounded-xl bg-ink-900">
      <canvas ref={canvas} className="h-full w-full cursor-grab touch-none" />
      {error && <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-white">{error}</div>}
      {hover && <div className="pointer-events-none absolute left-3 top-3 rounded bg-black/70 px-2 py-1 text-xs text-white">{PICK_LABEL[hover]}</div>}
      <div className="pointer-events-none absolute bottom-2 right-3 text-[11px] text-white/70">Kéo để xoay · cuộn để zoom · bấm vào vật để tương tác</div>
    </div>
  );
}

const Slider = ({ label, value, onChange, min = 0, max = 1, step = 0.05 }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number }) => (
  <label className="block text-sm">
    <div className="flex justify-between"><span>{label}</span><span className="text-ink-500">{value}</span></div>
    <input type="range" className="w-full" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} />
  </label>
);

export function Scene3DEditor({ p, onProject }: { p: ContentProject; onProject: (p: ContentProject) => void }) {
  const initial = useMemo(() => p.scene3d ?? defaultScene(), [p.id, p.scene3d]);
  const [scene, setScene] = useState<Scene3D>(initial);
  const [modelUrl, setModelUrl] = useState<string | null>(p.scene3d_model_url);
  const [modelName, setModelName] = useState<string | null>(null);
  const [clips, setClips] = useState<string[]>([]);
  const [placeholder, setPlaceholder] = useState(true);
  const [picker, setPicker] = useState(false);
  const engine = useRef<SceneEngine | null>(null);
  const caps = useCapabilities();
  const { busy, run } = useAction();

  useEffect(() => { setScene(initial); setModelUrl(p.scene3d_model_url); }, [initial]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(scene) !== JSON.stringify(initial);
  const env = scene.environment, ch = scene.character;
  const setEnv = (patch: Partial<Environment3D>) => setScene((s) => ({ ...s, environment: { ...s.environment, ...patch } }));
  const setChar = (patch: Partial<Scene3D["character"]>) => setScene((s) => ({ ...s, character: { ...s.character, ...patch } }));

  const save = async () => {
    const r = await run(() => api.updateContent(p.channel_id, p.id, { scene3d: scene }), "Đã lưu cảnh 3D");
    if (r) onProject(r);
  };
  const pickModel = (a: Asset) => { setChar({ asset_id: a.id, idle_animation: null, reactions: {} }); setModelUrl(a.url); setModelName(a.name); setPicker(false); };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-3">
        <Scene3DViewer scene={scene} modelUrl={modelUrl} engineRef={engine}
          onEnvChange={(e) => setEnv(e)} onReady={(i) => { setClips(i.clips); setPlaceholder(i.placeholder); }} />
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-primary" disabled={busy || !dirty} onClick={save}>{dirty ? "💾 Lưu cảnh 3D" : "Đã lưu"}</button>
          <button className="btn-ghost" disabled={!engine.current} onClick={() => { const c = engine.current!.currentCamera(); setScene((s) => ({ ...s, camera: c })); }}>📷 Dùng góc nhìn hiện tại làm camera</button>
          <button className="btn-ghost" disabled={!dirty} onClick={() => { setScene(initial); setModelUrl(p.scene3d_model_url); }}>Hoàn tác</button>
          {p.scene3d && <button className="btn-ghost text-red-700" disabled={busy} onClick={async () => {
            if (!confirm("Xóa cấu hình cảnh 3D của dự án này?")) return;
            const r = await run(() => api.updateContent(p.channel_id, p.id, { clear_scene3d: true }), "Đã xóa cảnh 3D");
            if (r) { onProject(r); setScene(defaultScene()); setModelUrl(null); }
          }}>Xóa cảnh</button>}
        </div>
        {caps.data && !caps.data.scene3d?.available && (
          <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            Máy này chưa render được cảnh 3D ra video: {caps.data.scene3d?.reason ?? "không rõ nguyên nhân"}. Bạn vẫn xem và dàn dựng cảnh bình thường.
          </div>
        )}
        <p className="muted">
          Khi render, cảnh 3D <b>thay thế</b> hình nền 2D, animation 2D và ảnh nhân vật 2D. Âm thanh, đồng hồ Pomodoro và thumbnail dùng như cũ.
          Cảnh được chụp thành một vòng lặp ngắn liền mạch rồi lặp lại đến độ dài video — hãy render thử bản xem trước ở tab Render.
        </p>
      </div>

      <div className="space-y-4">
        <div className="card space-y-3 p-4">
          <h3 className="font-semibold">Môi trường</h3>
          <Field label="Bối cảnh">
            <select className="input" value={scene.preset} onChange={(e) => setScene((s) => ({ ...s, preset: e.target.value as Scene3D["preset"] }))}>
              {Object.entries(PRESETS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Thời điểm">
            <select className="input" value={env.time_of_day} onChange={(e) => setEnv({ time_of_day: e.target.value as TimeOfDay })}>
              {Object.entries(TIMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Slider label="Mưa" value={env.rain} onChange={(v) => setEnv({ rain: v })} />
          <Slider label="Gió" value={env.wind} onChange={(v) => setEnv({ wind: v })} />
          <Slider label="Sương mù" value={env.fog} onChange={(v) => setEnv({ fog: v })} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={env.fireplace} onChange={(e) => setEnv({ fireplace: e.target.checked })} /> Lò sưởi</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={env.lamp} onChange={(e) => setEnv({ lamp: e.target.checked })} /> Đèn bàn</label>
        </div>

        <div className="card space-y-3 p-4">
          <h3 className="font-semibold">Nhân vật 3D</h3>
          <div className="text-sm">
            {ch.asset_id ? <>Model: <b>{modelName ?? `tài nguyên #${ch.asset_id}`}</b></> : <>Đang dùng <b>nhân vật tạm</b> (chưa có model .glb)</>}
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost text-xs" onClick={() => setPicker(true)}>Chọn model .glb</button>
            {ch.asset_id && <button className="btn-ghost text-xs" onClick={() => { setChar({ asset_id: null, idle_animation: null, reactions: {} }); setModelUrl(null); setModelName(null); }}>Dùng nhân vật tạm</button>}
          </div>
          {!ch.asset_id && <p className="muted">Nhân vật tạm chỉ để thử cảnh. Tải model .glb của bạn (hoặc có giấy phép) ở mục Assets rồi chọn ở đây.</p>}
          <Slider label="Kích thước" value={ch.scale} min={0.3} max={3} step={0.05} onChange={(v) => setChar({ scale: v })} />
          <Slider label="Hướng xoay (độ)" value={ch.rotation_y} min={-180} max={180} step={5} onChange={(v) => setChar({ rotation_y: v })} />
          <Slider label="Vị trí ngang (x)" value={ch.position[0]} min={-1.8} max={1.8} step={0.05} onChange={(v) => setChar({ position: [v, ch.position[1], ch.position[2]] })} />
          <Slider label="Vị trí sâu (z)" value={ch.position[2]} min={-1.6} max={2} step={0.05} onChange={(v) => setChar({ position: [ch.position[0], ch.position[1], v] })} />
          <div className="space-y-2 rounded-lg bg-brand-50 p-3">
            <div className="text-xs font-semibold uppercase text-ink-500">Xem thử phản ứng</div>
            <div className="flex flex-wrap gap-2">
              <button className="btn-ghost text-xs" onClick={() => engine.current?.trigger("click")}>Bấm vào nhân vật</button>
              <button className="btn-ghost text-xs" onClick={() => engine.current?.trigger("break_time")}>Giờ nghỉ</button>
              <button className="btn-ghost text-xs" onClick={() => setEnv({ rain: env.rain >= 0.7 ? 0.3 : 0.9 })}>{env.rain >= 0.7 ? "Giảm mưa" : "Mưa lớn"}</button>
              <button className="btn-ghost text-xs" onClick={() => setEnv({ fireplace: !env.fireplace })}>{env.fireplace ? "Tắt lò sưởi" : "Bật lò sưởi"}</button>
            </div>
            <p className="text-xs text-ink-500">
              <b>Trong video:</b> mưa lớn / lò sưởi tắt là <i>trạng thái</i> giữ nguyên cả video (nhân vật nhìn ra cửa sổ, co ro — animation được lặp lại).
              Giờ nghỉ là <i>sự kiện</i>: nhân vật phản ứng một lần ở đầu mỗi giờ nghỉ Pomodoro (cần bật đồng hồ Pomodoro ở tab Pomodoro).
              Nhân vật tạm có sẵn mọi phản ứng; model .glb cần gán animation bên dưới.
            </p>
          </div>
          {!placeholder && clips.length > 0 && (
            <>
              <Field label="Animation đứng yên (idle)">
                <select className="input" value={ch.idle_animation ?? ""} onChange={(e) => setChar({ idle_animation: e.target.value || null })}>
                  <option value="">Tự chọn</option>{clips.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
              {(Object.keys(TRIGGERS) as ReactionTrigger[]).map((t) => (
                <Field key={t} label={TRIGGERS[t]}>
                  <select className="input" value={ch.reactions[t] ?? ""} onChange={(e) => setChar({ reactions: { ...ch.reactions, [t]: e.target.value || undefined } })}>
                    <option value="">Không phản ứng</option>{clips.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </Field>
              ))}
            </>
          )}
          {!placeholder && clips.length === 0 && <p className="muted">Model này không có animation, nên nhân vật đứng yên.</p>}
        </div>
      </div>
      {picker && <AssetPicker channelId={p.channel_id} kind="model" onPick={pickModel} onClose={() => setPicker(false)} />}
    </div>
  );
}
