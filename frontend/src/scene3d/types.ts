/** Mirrors backend/app/schemas/scene3d.py. */
export type Vec3 = [number, number, number];
export type Preset = "cozy_room" | "rainy_window" | "forest_cabin" | "cafe";
export type TimeOfDay = "day" | "dusk" | "night";
export type ReactionTrigger = "click" | "rain_heavy" | "fire_out" | "break_time";
export type PickTarget = "window" | "fireplace" | "lamp" | "character";

export interface Environment3D { time_of_day: TimeOfDay; rain: number; wind: number; fog: number; fireplace: boolean; lamp: boolean }
export interface Character3D {
  asset_id: number | null; position: Vec3; rotation_y: number; scale: number;
  idle_animation: string | null; reactions: Partial<Record<ReactionTrigger, string>>;
}
export interface Camera3D { position: Vec3; target: Vec3; fov: number }
export interface Scene3D { version: 1; preset: Preset; environment: Environment3D; character: Character3D; camera: Camera3D }

export const PRESETS: Record<Preset, string> = {
  cozy_room: "Phòng học ấm cúng", rainy_window: "Cửa sổ ngày mưa", forest_cabin: "Nhà gỗ trong rừng", cafe: "Quán cà phê",
};
export const TIMES: Record<TimeOfDay, string> = { day: "Ban ngày", dusk: "Hoàng hôn", night: "Ban đêm" };
export const TRIGGERS: Record<ReactionTrigger, string> = {
  click: "Khi bấm vào nhân vật", rain_heavy: "Khi mưa lớn", fire_out: "Khi lò sưởi tắt", break_time: "Khi đến giờ nghỉ",
};

export const defaultScene = (): Scene3D => ({
  version: 1, preset: "cozy_room",
  environment: { time_of_day: "night", rain: 0.5, wind: 0.2, fog: 0.1, fireplace: true, lamp: true },
  character: { asset_id: null, position: [0.9, 0, -0.2], rotation_y: -25, scale: 1, idle_animation: null, reactions: {} },
  camera: { position: [0, 1.5, 3.6], target: [0, 0.9, 0], fov: 45 },
});
