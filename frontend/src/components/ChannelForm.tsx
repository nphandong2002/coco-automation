import { FormEvent, useState } from "react";
import type { Channel, ChannelInput, ScheduleSlot } from "../api/types";
import { joinList, splitList } from "../lib/hooks";
import { Field } from "./ui";

const WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"];

export function emptyChannelInput(): ChannelInput {
  return {
    code: "", name: "", description: "", language: "en", target_country: "US", topics: [],
    visual_style: { theme: "", mood: "", palette: [], keywords: [] },
    audio_style: { ambience: [], music: "", notes: "" },
    publish_schedule: { timezone: "Asia/Bangkok", slots: [] },
  };
}

export function channelToInput(c: Channel): ChannelInput {
  return {
    name: c.name, description: c.description, language: c.language, target_country: c.target_country, topics: c.topics,
    visual_style: { theme: "", mood: "", palette: [], keywords: [], ...c.visual_style },
    audio_style: { ambience: [], music: "", notes: "", ...c.audio_style },
    publish_schedule: { timezone: "Asia/Bangkok", slots: [], ...c.publish_schedule },
  };
}

const slugify = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d")
  .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);

export default function ChannelForm({ initial, isCreate, busy, onSubmit, onCancel }: {
  initial: ChannelInput; isCreate?: boolean; busy?: boolean;
  onSubmit: (v: ChannelInput) => void; onCancel?: () => void;
}) {
  const [v, setV] = useState<ChannelInput>(initial);
  const [codeTouched, setCodeTouched] = useState(!isCreate);
  // text buffers for comma lists so typing commas feels natural
  const [topics, setTopics] = useState(joinList(initial.topics));
  const [palette, setPalette] = useState(joinList(initial.visual_style.palette));
  const [keywords, setKeywords] = useState(joinList(initial.visual_style.keywords));
  const [ambience, setAmbience] = useState(joinList(initial.audio_style.ambience));

  const set = <K extends keyof ChannelInput>(k: K, val: ChannelInput[K]) => setV((x) => ({ ...x, [k]: val }));
  const setSlots = (slots: ScheduleSlot[]) => set("publish_schedule", { ...v.publish_schedule, slots });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({
      ...v,
      topics: splitList(topics),
      visual_style: { ...v.visual_style, palette: splitList(palette), keywords: splitList(keywords) },
      audio_style: { ...v.audio_style, ambience: splitList(ambience) },
    });
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Tên kênh *">
          <input className="input" required minLength={2} value={v.name}
            onChange={(e) => { set("name", e.target.value); if (!codeTouched) set("code", slugify(e.target.value)); }} />
        </Field>
        {isCreate && (
          <Field label="Mã kênh *" hint="a-z, 0-9, dấu '-'. Không đổi được sau khi tạo.">
            <input className="input font-mono" required pattern="[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]" value={v.code}
              onChange={(e) => { setCodeTouched(true); set("code", e.target.value); }} />
          </Field>
        )}
        <Field label="Ngôn ngữ"><input className="input" value={v.language} onChange={(e) => set("language", e.target.value)} placeholder="en, vi, ja…" /></Field>
        <Field label="Quốc gia mục tiêu"><input className="input" value={v.target_country} onChange={(e) => set("target_country", e.target.value.toUpperCase())} placeholder="US, VN, JP…" /></Field>
      </div>
      <Field label="Mô tả"><textarea className="input min-h-[80px]" value={v.description} onChange={(e) => set("description", e.target.value)} /></Field>
      <Field label="Chủ đề nội dung" hint="Phân tách bằng dấu phẩy. VD: study with me, pomodoro, rain">
        <input className="input" value={topics} onChange={(e) => setTopics(e.target.value)} />
      </Field>

      <fieldset className="rounded-lg border border-brand-100 p-4">
        <legend className="px-1 text-sm font-semibold">Phong cách hình ảnh</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Theme"><input className="input" value={v.visual_style.theme} placeholder="Cozy pastel, anime cinematic…"
            onChange={(e) => set("visual_style", { ...v.visual_style, theme: e.target.value })} /></Field>
          <Field label="Mood"><input className="input" value={v.visual_style.mood} placeholder="calm, warm…"
            onChange={(e) => set("visual_style", { ...v.visual_style, mood: e.target.value })} /></Field>
          <Field label="Bảng màu" hint="Mã HEX, phân tách bằng dấu phẩy"><input className="input font-mono" value={palette} onChange={(e) => setPalette(e.target.value)} placeholder="#F6D6C8, #A7C4BC" /></Field>
          <Field label="Từ khóa hình ảnh"><input className="input" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="library, window, lamp" /></Field>
        </div>
      </fieldset>

      <fieldset className="rounded-lg border border-brand-100 p-4">
        <legend className="px-1 text-sm font-semibold">Phong cách âm thanh</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Ambience"><input className="input" value={ambience} onChange={(e) => setAmbience(e.target.value)} placeholder="rain, fireplace, keyboard" /></Field>
          <Field label="Nhạc nền"><input className="input" value={v.audio_style.music} placeholder="lo-fi piano…"
            onChange={(e) => set("audio_style", { ...v.audio_style, music: e.target.value })} /></Field>
        </div>
        <div className="mt-4"><Field label="Ghi chú"><input className="input" value={v.audio_style.notes}
          onChange={(e) => set("audio_style", { ...v.audio_style, notes: e.target.value })} /></Field></div>
      </fieldset>

      <fieldset className="rounded-lg border border-brand-100 p-4">
        <legend className="px-1 text-sm font-semibold">Lịch đăng video</legend>
        <Field label="Múi giờ" hint="Tên IANA, VD: Asia/Bangkok, America/New_York">
          <input className="input" value={v.publish_schedule.timezone}
            onChange={(e) => set("publish_schedule", { ...v.publish_schedule, timezone: e.target.value })} />
        </Field>
        <div className="mt-3 space-y-2">
          {v.publish_schedule.slots.map((s, i) => (
            <div key={i} className="flex items-center gap-2">
              <select className="input w-32" value={s.weekday}
                onChange={(e) => setSlots(v.publish_schedule.slots.map((x, j) => j === i ? { ...x, weekday: +e.target.value } : x))}>
                {WEEKDAYS.map((d, j) => <option key={j} value={j}>{d}</option>)}
              </select>
              <input type="time" className="input w-32" required value={s.time}
                onChange={(e) => setSlots(v.publish_schedule.slots.map((x, j) => j === i ? { ...x, time: e.target.value } : x))} />
              <button type="button" className="btn-ghost" onClick={() => setSlots(v.publish_schedule.slots.filter((_, j) => j !== i))}>Xóa</button>
            </div>
          ))}
          <button type="button" className="btn-ghost" onClick={() => setSlots([...v.publish_schedule.slots, { weekday: 0, time: "19:00" }])}>+ Thêm khung giờ</button>
        </div>
      </fieldset>

      <div className="flex justify-end gap-2">
        {onCancel && <button type="button" className="btn-ghost" onClick={onCancel}>Hủy</button>}
        <button className="btn-primary" disabled={busy}>{busy ? "Đang lưu…" : isCreate ? "Tạo kênh" : "Lưu thay đổi"}</button>
      </div>
    </form>
  );
}

export { WEEKDAYS };
